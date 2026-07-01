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
import httpx
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
        return await _call_anthropic(system, user, api_key, clean_model, max_tokens)

    # ── Direct Google AI Studio (REST) ───────────────────────────────────────
    if provider == "google":
        try:
            return await _call_google(system, user, api_key, model, max_tokens)
        except ValueError as e:
            ant_key = keys.anthropic if keys else ""
            if ant_key:
                print(f"[Google AI] direct failed ({e}) — falling back to Haiku via Anthropic")
                return await _call_anthropic(system, user, ant_key, _HAIKU_FALLBACK, max_tokens)
            raise

    # ── Direct OpenAI (REST) ─────────────────────────────────────────────────
    if provider == "openai":
        return await _call_openai_direct(system, user, api_key, model, max_tokens)

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
                    async with httpx.AsyncClient(timeout=90) as client:
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
                    out_tokens = (data.get("usage") or {}).get("completion_tokens", 0)
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
                           model: str, max_tokens: int) -> str:
    """Anthropic SDK — direct API, no service fees."""
    import anthropic
    # Anthropic API requires dashes not dots: claude-sonnet-4-6, not claude-sonnet-4.6
    model = model.replace(".", "-")
    client = anthropic.AsyncAnthropic(api_key=api_key)
    msg = await client.messages.create(
        model=model or "claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text


async def _call_google(system: str, user: str, api_key: str,
                        model: str, max_tokens: int) -> str:
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
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}

    _TRANSIENT = {429, 500, 502, 503, 504}
    resp = None
    async with httpx.AsyncClient(timeout=90) as client:
        for attempt in range(3):
            resp = await client.post(
                url, json=payload,
                params={"key": api_key},
                headers={"Content-Type": "application/json"},
            )
            if resp.is_success or resp.status_code not in _TRANSIENT:
                break
            wait = 2 ** attempt  # 1s, 2s, 4s
            print(f"[Google AI] {resp.status_code} transient — retry {attempt+1}/3 in {wait}s")
            await asyncio.sleep(wait)

    if not resp.is_success:
        raise ValueError(f"Google AI HTTP {resp.status_code}: {resp.text[:400]}")

    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ValueError(f"Unexpected Google AI response structure: {data}") from e


async def _call_openai_direct(system: str, user: str, api_key: str,
                               model: str, max_tokens: int) -> str:
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

    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers, json=payload,
        )

    if not resp.is_success:
        raise ValueError(f"OpenAI HTTP {resp.status_code}: {resp.text[:400]}")

    data = resp.json()
    return data["choices"][0]["message"]["content"]
