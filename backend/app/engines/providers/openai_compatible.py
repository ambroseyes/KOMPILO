"""Minimal OpenAI-compatible chat-completions adapter.

Works against any endpoint exposing ``POST {base_url}/chat/completions`` with the
OpenAI schema (OpenAI, Azure OpenAI, many gateways, local servers). The API key is
read from the environment (never hardcoded) by ``providers.get_default_provider``.

MARKED: base of the future Kompilo Gateway. Intentionally tiny — no retries, routing
or budgets yet; it just makes one JSON-mode call and surfaces failures as
``ProviderError`` so the Intent Engine can fall back to its heuristics.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.engines.providers.base import ProviderError
from app.telemetry.logging import get_logger

logger = get_logger(__name__)


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(self, *, api_key: str, base_url: str, model: str, timeout_seconds: float = 20.0):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds

    async def complete_json(self, *, system: str, user: str, max_tokens: int = 400) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,  # deterministic extraction
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions", json=payload, headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
            content = data["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            # Never leak the key or raw provider internals upward.
            raise ProviderError(f"{self.name} request failed: {type(exc).__name__}") from exc
        if not isinstance(content, str):
            raise ProviderError(f"{self.name} returned a non-text completion")
        return content
