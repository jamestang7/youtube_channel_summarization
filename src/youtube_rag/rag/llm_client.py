from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from ..core import config
from ..core.http_utils import post_json_with_retry


@dataclass
class LLMChatClient:
    provider: str

    def __post_init__(self) -> None:
        self.provider = self.provider.lower()

    def active_model(self) -> str:
        if self.provider == config.PROVIDER_OPENAI:
            return config.OPENAI_MODEL
        if self.provider == config.PROVIDER_GROQ:
            return config.GROQ_MODEL
        if self.provider == config.PROVIDER_OLLAMA:
            return config.OLLAMA_MODEL
        raise RuntimeError(f"Unsupported LLM provider: {self.provider}")

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        if self.provider in {config.PROVIDER_OPENAI, config.PROVIDER_GROQ}:
            return self._generate_openai_compatible(system_prompt, user_prompt, temperature)
        if self.provider == config.PROVIDER_OLLAMA:
            return self._generate_ollama(system_prompt, user_prompt)
        raise RuntimeError(f"Unsupported LLM provider: {self.provider}")

    def _generate_openai_compatible(self, system_prompt: str, user_prompt: str, temperature: float) -> str:
        if self.provider == config.PROVIDER_OPENAI:
            api_key = os.getenv("OPENAI_API_KEY")
            base_url = config.OPENAI_BASE_URL
        else:
            api_key = os.getenv("GROQ_API_KEY")
            base_url = config.GROQ_BASE_URL

        if not api_key:
            raise RuntimeError(f"[{self.provider}] API key is required")

        url = f"{base_url.rstrip('/')}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.active_model(),
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        data = post_json_with_retry(
            url=url,
            payload=payload,
            headers=headers,
            provider=self.provider,
        )
        return data["choices"][0]["message"]["content"].strip()

    def _generate_ollama(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/chat"
        payload: dict[str, Any] = {
            "model": self.active_model(),
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {"Content-Type": "application/json"}

        data = post_json_with_retry(
            url=url,
            payload=payload,
            headers=headers,
            provider=self.provider,
        )
        return data["message"]["content"].strip()
