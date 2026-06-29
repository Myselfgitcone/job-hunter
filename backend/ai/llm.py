"""
Single LLM call function. Supports direct provider APIs (no service fees)
and OpenRouter as fallback.

Direct API routing (preferred — avoids OpenRouter 5.5% service fee):
  claude-*  → Anthropic API  (console.anthropic.com)
  gemini-*  → Google AI      (aistudio.google.com)
  gpt-*/o*  → OpenAI API     (platform.openai.com)

Fallback (OpenRouter):
  Any model without a matching direct key → OpenRouter

Usage:
    from ai.llm import chat, ModelKeys
    keys = ModelKeys(anthropic="sk-ant-...", google="AI...", openai="sk-...")
    result = await chat(system=..., user=..., model="claude-sonnet-4-5", keys=keys)
"""
import asyncio
import time
import httpx
import contextvars
from dataclasses import dataclass, field


# ── Direct provider URLs ──────────────────────────────────────────────────────
PROVIDER_URLS = {
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "groq":       "https://api.groq.com/openai/v1/chat/completions",
    "nvidia":     "https://integrate.api.nvidia.com/v1/chat/completions",
    "openai":     "https://api.openai.com/v1/chat/completions",
}

RECOMMENDED_MODELS = {
    "openrouter": [
        "google/gemini-flash-1.5",
        "google/gemini-2.0-flash-001",
        "meta-llama/llama-3.3-70b-instruct",
        "anthropic/claude-3.5-sonnet",
        "anthropic/claude-3-haiku",
        "mistralai/mistral-7b-instruct:free",
        "meta-llama/llama-3.1-8b-instruct:free",
    ],
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
    ],
    "nvidia": [
        "nvidia/llama-3.1-nemotron-70b-instruct",
        "meta/llama-3.1-70b-instruct",
        "mistralai/mistral-large",
    ],
    "anthropic": [
        "claude-sonnet-4-5",
        "claude-opus-4-5",
        "claude-haiku-4-5",
    ],
    "google": [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-pro",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "o3-mini",
    ],
}


# ── Multi-provider key container ──────────────────────────────────────────────
@dataclass
class ModelKeys:
    """
    Holds direct API keys for each provider.
    When set, the system uses direct APIs and avoids OpenRouter's 5.5% fee.
    Leave a field empty ("") to fall back to OpenRouter for that model family.
    """
    anthropic: str = ""    # console.anthropic.com — for claude-* models
    google: str    = ""    # aistudio.google.com   — for gemini-* models
    openai: str    = ""    # platform.openai.com   — for gpt-*/o* models
    openrouter: str = ""   # openrouter.ai/keys    — fallback for all models


_HAIKU_FALLBACK = "claude-haiku-4-5"


# ── Per-run token/cost accounting ─────────────────────────────────────────────
# A contextvar sink lets chat() record token usage without changing its return
# signature (which would ripple through every caller). Usage: reset_usage()
# before a run, then get_run_usage() after. Rates are USD per 1M tokens (in, out).
_MODEL_RATES = {
    "claude-opus-4-8":       (5.0, 25.0),
    "claude-opus-4-7":       (5.0, 25.0),
    "claude-opus-4-5":       (5.0, 25.0),
    "claude-sonnet-4-6":     (3.0, 15.0),
    "claude-sonnet-4-5":     (3.0, 15.0),
    "claude-haiku-4-5":      (1.0, 5.0),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash":      (0.30, 2.50),
}
_DEFAULT_RATE = (3.0, 15.0)   # unknown model → assume Sonnet-tier (never undercount)

_usage_sink: contextvars.ContextVar = contextvars.ContextVar("_usage_sink", default=None)

# Prompt caching is opt-in per request: ONLY the checkbox batch-tailor flow turns
# it on (many calls close together → cache pays). A single/manual tailor leaves
# it off → always baseline cost, never the 1.25x write premium.
_cache_ok: contextvars.ContextVar = contextvars.ContextVar("_cache_ok", default=False)


def set_cache_enabled(on: bool) -> None:
    """Enable Anthropic prompt caching for the current request context (batch)."""
    _cache_ok.set(bool(on))


def _rate_for(model: str) -> tuple[float, float]:
    # Match by model FAMILY so dots/dashes/version drift don't matter
    # ("gemini-2.5-flash-lite", "claude-sonnet-4.6", etc.).
    m = (_strip_provider_prefix(model) or "").lower()
    if "opus" in m:
        return _MODEL_RATES["claude-opus-4-8"]
    if "sonnet" in m:
        return _MODEL_RATES["claude-sonnet-4-6"]
    if "haiku" in m:
        return _MODEL_RATES["claude-haiku-4-5"]
    if "flash-lite" in m or "flash lite" in m:
        return _MODEL_RATES["gemini-2.5-flash-lite"]
    if "gemini" in m or "flash" in m:
        return _MODEL_RATES["gemini-2.5-flash"]
    return _DEFAULT_RATE


def reset_usage() -> None:
    """Start a fresh per-run usage accumulator (call before a tailor run)."""
    _usage_sink.set([])


def _record_usage(model: str, pass_name: str, in_tok, out_tok) -> None:
    sink = _usage_sink.get()
    if sink is None:
        return
    sink.append({"model": model or "", "pass": pass_name or "",
                 "in": int(in_tok or 0), "out": int(out_tok or 0)})


def get_run_usage() -> dict:
    """{cost, tokens_in, tokens_out, calls:[...]} for the current run's sink."""
    sink = _usage_sink.get() or []
    cost = 0.0
    ti = to = 0
    for c in sink:
        ri, ro = _rate_for(c["model"])
        cost += c["in"] / 1e6 * ri + c["out"] / 1e6 * ro
        ti += c["in"]; to += c["out"]
    return {"cost": round(cost, 4), "tokens_in": ti, "tokens_out": to, "calls": list(sink)}


def _resolve_provider(model: str, keys: ModelKeys) -> tuple[str, str]:
    """
    Given a model name and a ModelKeys object, return (api_key, provider).
    Routes to direct APIs only — no OpenRouter.
    If no matching direct key, falls back to Claude Haiku via Anthropic.
    """
    m = model.lower()
    if "/" in m:
        m = m.split("/", 1)[1]

    if m.startswith("claude") and keys.anthropic:
        print(f"[LLM ROUTE] {model} → ANTHROPIC direct")
        return keys.anthropic, "anthropic"
    if m.startswith("gemini") and keys.google:
        print(f"[LLM ROUTE] {model} → GOOGLE AI direct")
        return keys.google, "google"
    if (m.startswith("gpt-") or m.startswith("o1") or
            m.startswith("o3") or m.startswith("o4")) and keys.openai:
        print(f"[LLM ROUTE] {model} → OPENAI direct")
        return keys.openai, "openai"

    # No matching direct key — fall back to Haiku via Anthropic
    if keys.anthropic:
        print(f"[LLM ROUTE] {model} → no direct key, using Haiku fallback via Anthropic")
        return keys.anthropic, "anthropic"

    raise ValueError(f"No API key available for model '{model}'. Set anthropic_api_key, google_api_key, or openai_api_key in Settings.")


def _strip_provider_prefix(model: str) -> str:
    """Strip 'anthropic/', 'google/', 'openai/' prefix for direct API calls."""
    return model.split("/", 1)[-1] if "/" in model else model


# ── Optional hook: Telegram fallback alerts ───────────────────────────────────
_fallback_notify = None

def set_fallback_notifier(fn):
    global _fallback_notify
    _fallback_notify = fn


# ── Main chat function ────────────────────────────────────────────────────────
async def chat(
    system: str,
    user: str,
    api_key: str = "",
    provider: str = "openrouter",
    model: str = "anthropic/claude-sonnet-4-5",
    max_tokens: int = 4096,
    pass_name: str = "",
    allow_fallback: bool = True,
    retry_on_ratelimit: int = 0,
    keys: ModelKeys | None = None,
    timeout: int = 90,
) -> str:
    """
    Call an LLM and return the response text.

    If `keys` is provided (ModelKeys object), the provider is auto-selected
    based on the model name prefix — using direct APIs to avoid OpenRouter fees.
    Otherwise, uses the legacy api_key + provider arguments.
    """
    # ── Resolve provider from ModelKeys (direct API routing) ─────────────────
    if keys is not None:
        api_key, provider = _resolve_provider(model, keys)

    provider = (provider or "openrouter").lower().strip()

    # ── Direct Anthropic (SDK) ────────────────────────────────────────────────
    if provider == "anthropic":
        clean_model = _strip_provider_prefix(model)
        return await _call_anthropic(system, user, api_key, clean_model, max_tokens, pass_name, timeout=timeout)

    # ── Direct Google AI Studio (REST) ───────────────────────────────────────
    if provider == "google":
        try:
            return await _call_google(system, user, api_key, model, max_tokens, timeout=timeout, pass_name=pass_name)
        except ValueError as e:
            ant_key = keys.anthropic if keys else ""
            if ant_key:
                print(f"[Google AI] direct failed ({e}) — falling back to Haiku via Anthropic")
                return await _call_anthropic(system, user, ant_key, _HAIKU_FALLBACK, max_tokens, pass_name, timeout=timeout)
            raise

    # ── Direct OpenAI (REST) ─────────────────────────────────────────────────
    if provider == "openai":
        return await _call_openai_direct(system, user, api_key, model, max_tokens, timeout=timeout)

    # ── OpenRouter / Groq / Nvidia (existing logic) ───────────────────────────
    url = PROVIDER_URLS.get(provider)
    if not url:
        raise ValueError(f"Unknown provider: {provider}. "
                         "Use openrouter / groq / nvidia / anthropic / google / openai")

    models_to_try = [model]
    if allow_fallback and provider == "openrouter":
        fallback_models = [
            "google/gemini-2.5-flash",
            "google/gemini-2.5-flash-lite",
            "anthropic/claude-haiku-4.5",
        ]
        for fm in fallback_models:
            if fm not in models_to_try:
                models_to_try.append(fm)

    label = f"[{pass_name}]" if pass_name else "[chat]"
    last_error = None

    for idx, current_model in enumerate(models_to_try):
        is_fallback = idx > 0
        try:
            if is_fallback:
                msg = f"[FALLBACK] {label} primary={model} failed — using fallback: {current_model}"
                print(msg)
                _silent_passes = {"exp-sweep", "qualify"}
                if _fallback_notify and pass_name not in _silent_passes:
                    try:
                        asyncio.create_task(_fallback_notify(
                            f"⚠️ Model fallback fired\nPass: {pass_name or 'unknown'}\n"
                            f"Primary: {model}\nFallback: {current_model}\n"
                            f"Error: {str(last_error)[:200]}"
                        ))
                    except Exception:
                        pass

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            if provider == "openrouter":
                headers["HTTP-Referer"] = "https://job-hunter-sigma.vercel.app"
                headers["X-Title"] = "Job Hunter"

            payload = {
                "model": current_model,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }

            for rate_attempt in range(retry_on_ratelimit + 1):
                try:
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        resp = await client.post(url, headers=headers, json=payload)

                    if resp.status_code == 429:
                        if rate_attempt < retry_on_ratelimit:
                            wait = 5 * (rate_attempt + 1)
                            notify_msg = (
                                f"⚠️ Rate limit (429)\nPass: {pass_name or 'unknown'}\n"
                                f"Model: {current_model}\nRetrying in {wait}s "
                                f"(attempt {rate_attempt + 1}/{retry_on_ratelimit})"
                            )
                            print(f"[RATE LIMIT] {label} got 429 on {current_model}. Waiting {wait}s...")
                            if _fallback_notify:
                                try:
                                    asyncio.create_task(_fallback_notify(notify_msg))
                                except Exception:
                                    pass
                            await asyncio.sleep(wait)
                            continue
                        raise ValueError(f"HTTP 429 rate limit on {current_model} after {retry_on_ratelimit} retries")

                    if not resp.is_success:
                        body = resp.text[:400]
                        raise ValueError(f"HTTP {resp.status_code} from {provider} using {current_model}: {body}")

                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    _u = data.get("usage") or {}
                    out_tokens = _u.get("completion_tokens", 0)
                    _record_usage(current_model, pass_name, _u.get("prompt_tokens", 0), out_tokens)
                    if out_tokens:
                        print(f"{label} output tokens: {out_tokens}")
                        if out_tokens > 4500:
                            print(f"[WARN OVERSIZED OUTPUT] {label} produced {out_tokens} tokens — "
                                  "expected ≤4500. Plan block may not be stripped.")
                    return content

                except ValueError:
                    raise
                except Exception as e:
                    raise e
        except Exception as e:
            last_error = e
            continue

    if last_error:
        raise last_error


# ── Direct provider callers ───────────────────────────────────────────────────

async def _call_anthropic(system: str, user: str, api_key: str,
                           model: str, max_tokens: int, pass_name: str = "",
                           timeout: int = 120) -> str:
    """Anthropic SDK — direct API, no service fees."""
    import anthropic
    # Anthropic API requires dashes not dots: claude-sonnet-4-6, not claude-sonnet-4.6
    model = model.replace(".", "-")
    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=1)
    label = f"[{pass_name}]" if pass_name else "[anthropic]"
    start = time.perf_counter()
    # Cache the big static system prompt ONLY when the batch flow opted in
    # (_cache_ok). Single/manual tailors never cache → always baseline cost,
    # no 1.25x write premium. Batches save (prime warms, rest read at 0.1x).
    _system_param: object = system
    if system and len(system) > 4000 and _cache_ok.get():
        _system_param = [{"type": "text", "text": system,
                          "cache_control": {"type": "ephemeral"}}]
    try:
        msg = await client.messages.create(
            model=model or "claude-sonnet-4-6",
            max_tokens=max_tokens,
            system=_system_param,
            messages=[{"role": "user", "content": user}],
        )
    finally:
        print(f"{label} anthropic call took {time.perf_counter() - start:.1f}s")
    try:
        u = getattr(msg, "usage", None)
        # Fold cached tokens into an effective input count so the recorded cost
        # reflects real billing: cache reads bill at 0.1x the input rate, cache
        # writes at 1.25x. usage.input_tokens already excludes cached tokens.
        _in = getattr(u, "input_tokens", 0) or 0
        _cread = getattr(u, "cache_read_input_tokens", 0) or 0
        _cwrite = getattr(u, "cache_creation_input_tokens", 0) or 0
        _eff_in = int(_in + _cread * 0.1 + _cwrite * 1.25)
        _record_usage(model or "claude-sonnet-4-6", pass_name,
                      _eff_in, getattr(u, "output_tokens", 0) or 0)
    except Exception:  # noqa: BLE001 — accounting must never break the call
        pass
    return msg.content[0].text


async def _call_google(system: str, user: str, api_key: str,
                        model: str, max_tokens: int, timeout: int = 90,
                        pass_name: str = "") -> str:
    """
    Google AI Studio REST API — direct, no service fees.
    Get key at: aistudio.google.com/apikey
    Docs: https://ai.google.dev/api/generate-content
    """
    clean_model = _strip_provider_prefix(model)
    url = (f"https://generativelanguage.googleapis.com/v1beta/"
           f"models/{clean_model}:generateContent")

    payload: dict = {
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        # thinkingBudget 0 disables Gemini 2.5 internal reasoning tokens.
        # Thinking tokens count against maxOutputTokens — with thinking on,
        # long prompts made Gemini spend the budget on thinking and truncate
        # the visible output mid-resume (retry/reviewer passes).
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}

    _TRANSIENT = {429, 500, 502, 503, 504}
    # A 429 for depleted billing / exhausted quota is PERMANENT — it will not
    # recover inside a 7s backoff. Retrying it 3× just burns wall-clock and
    # floods logs before the caller's Haiku fallback fires. Detect it and bail
    # immediately so the fallback kicks in <1s instead of ~7s later.
    _PERMANENT_429 = ("depleted", "billing", "prepay", "quota exceeded",
                       "exceeded your current quota")
    resp = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(3):
            resp = await client.post(
                url, json=payload,
                params={"key": api_key},
                headers={"Content-Type": "application/json"},
            )
            if resp.is_success or resp.status_code not in _TRANSIENT:
                break
            if resp.status_code == 429 and any(
                p in resp.text.lower() for p in _PERMANENT_429
            ):
                print("[Google AI] 429 billing/quota exhausted — permanent, "
                      "skipping retries, failing over now")
                break
            wait = 2 ** attempt  # 1s, 2s, 4s
            print(f"[Google AI] {resp.status_code} transient — retry {attempt+1}/3 in {wait}s")
            await asyncio.sleep(wait)

    if not resp.is_success:
        raise ValueError(f"Google AI HTTP {resp.status_code}: {resp.text[:400]}")

    data = resp.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ValueError(f"Unexpected Google AI response structure: {data}") from e
    try:
        um = data.get("usageMetadata") or {}
        _record_usage(model, pass_name, um.get("promptTokenCount", 0), um.get("candidatesTokenCount", 0))
    except Exception:  # noqa: BLE001
        pass
    return text


async def _call_openai_direct(system: str, user: str, api_key: str,
                               model: str, max_tokens: int, timeout: int = 90) -> str:
    """
    OpenAI direct REST API — no service fees.
    Get key at: platform.openai.com/api-keys
    """
    clean_model = _strip_provider_prefix(model)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    payload = {
        "model": clean_model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers, json=payload,
        )

    if not resp.is_success:
        raise ValueError(f"OpenAI HTTP {resp.status_code}: {resp.text[:400]}")

    data = resp.json()
    return data["choices"][0]["message"]["content"]
