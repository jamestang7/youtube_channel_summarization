from __future__ import annotations

import os

from ..core import config
from ..core.http_utils import post_json_with_retry


def active_model(provider: str) -> str:
    if provider == config.PROVIDER_OPENAI:
        return config.OPENAI_MODEL
    if provider == config.PROVIDER_GROQ:
        return config.GROQ_MODEL
    if provider == config.PROVIDER_OLLAMA:
        return config.OLLAMA_MODEL
    raise RuntimeError(f"Unknown provider: {provider}")


def llm_generate(provider: str, system: str, user: str, temperature: float = 0.2) -> str:
    provider = provider.lower()
    if provider in (config.PROVIDER_OPENAI, config.PROVIDER_GROQ):
        return _openai_compat(provider, system, user, temperature)
    if provider == config.PROVIDER_OLLAMA:
        return _ollama(system, user)
    raise RuntimeError(f"Unknown provider: {provider}")


def _openai_compat(provider: str, system: str, user: str, temperature: float) -> str:
    api_key = os.getenv("OPENAI_API_KEY" if provider == config.PROVIDER_OPENAI else "GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(f"[{provider}] API key missing")
    base_url = config.OPENAI_BASE_URL if provider == config.PROVIDER_OPENAI else config.GROQ_BASE_URL
    data = post_json_with_retry(
        url=f"{base_url.rstrip('/')}/chat/completions",
        payload={
            "model": active_model(provider),
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "youtube-rag/0.1 (+local dev)",},
        provider=provider,
    )
    return data["choices"][0]["message"]["content"].strip()


def _ollama(system: str, user: str) -> str:
    data = post_json_with_retry(
        url=f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/chat",
        payload={
            "model": active_model(config.PROVIDER_OLLAMA),
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        headers={"Content-Type": "application/json"},
        provider=config.PROVIDER_OLLAMA,
    )
    return data["message"]["content"].strip()
