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
        "anthropic/claude-sonnet-4-5",
        "anthropic/claude-3-haiku",
        "google/gemini-flash-1.5",
        "meta-llama/llama-3.3-70b-instruct",
        "mistralai/mistral-7b-instruct:free",
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

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = "http://localhost:5173"
        headers["X-Title"] = "Job Hunter"

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }

    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


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
