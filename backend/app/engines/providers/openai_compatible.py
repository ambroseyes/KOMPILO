"""OpenAI-compatible chat-completions adapter.

Works against any endpoint exposing ``POST {base_url}/chat/completions`` with the
OpenAI schema — OpenAI, Azure OpenAI, **Ollama** (``http://localhost:11434/v1``),
**LM Studio** (``http://localhost:1234/v1``), and most gateways. The API key and base
URL come from the environment via ``providers.get_execution_provider``; local servers
that need no key accept any placeholder.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.engines.providers.base import CompletionResult, ProviderCapabilities, ProviderError
from app.telemetry.logging import get_logger

logger = get_logger(__name__)


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(self, *, api_key: str, base_url: str, model: str, timeout_seconds: float = 30.0):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._default_model = model
        self._timeout = timeout_seconds

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            supports_streaming=True,
            is_real=True,
            note=f"OpenAI-compatible endpoint at {self._base_url}",
        )

    async def complete(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> CompletionResult:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions", json=payload, headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            # Never leak the key or raw provider internals upward.
            raise ProviderError(f"{self.name} request failed: {type(exc).__name__}") from exc
        if not isinstance(content, str):
            raise ProviderError(f"{self.name} returned a non-text completion")
        return CompletionResult(
            text=content,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            model=str(payload["model"]),
            provider=self.name,
        )
