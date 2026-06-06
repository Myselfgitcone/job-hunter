"""
Single LLM call function. Works with any OpenAI-compatible endpoint:
  - OpenRouter  (openrouter.ai)
  - Groq        (api.groq.com)
  - Nvidia NIM  (integrate.api.nvidia.com)
  - Anthropic direct (via anthropic SDK)
"""
import httpx

PROVIDER_URLS = {
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "groq":       "https://api.groq.com/openai/v1/chat/completions",
    "nvidia":     "https://integrate.api.nvidia.com/v1/chat/completions",
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
}


async def chat(
    system: str,
    user: str,
    api_key: str,
    provider: str = "openrouter",
    model: str = "anthropic/claude-sonnet-4-5",
    max_tokens: int = 4096,
) -> str:
    if provider == "anthropic":
        return await _call_anthropic(system, user, api_key, model, max_tokens)

    url = PROVIDER_URLS.get(provider)
    if not url:
        raise ValueError(f"Unknown provider: {provider}. Use openrouter / groq / nvidia / anthropic")

    models_to_try = [model]
    if provider == "openrouter":
        if "lite" in model or "flash" in model:
            fallback_models = [
                "google/gemini-2.5-flash",
                "google/gemini-2.5-flash-lite",
                "anthropic/claude-haiku-4.5",
                "openai/gpt-5"
            ]
        else:
            fallback_models = [
                "anthropic/claude-opus-4-8",
                "anthropic/claude-haiku-4.5",
                "google/gemini-2.5-flash",
                "google/gemini-2.5-flash-lite",
                "openai/gpt-5"
            ]
        
        for fm in fallback_models:
            if fm not in models_to_try:
                models_to_try.append(fm)

    last_error = None
    for current_model in models_to_try:
        try:
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

            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if not resp.is_success:
                    body = resp.text[:400]
                    raise ValueError(f"HTTP {resp.status_code} from {provider} using {current_model}: {body}")
                return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            last_error = e
            continue

    if last_error:
        raise last_error



async def _call_anthropic(system: str, user: str, api_key: str, model: str, max_tokens: int) -> str:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=api_key)
    msg = await client.messages.create(
        model=model or "claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text
