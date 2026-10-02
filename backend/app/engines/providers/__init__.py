"""LLM provider adapters — the seed of the future Kompilo Gateway.

For now a single OpenAI-compatible adapter, selected only when a key is configured.
``get_default_provider()`` returns ``None`` when no key is set, which is how the Intent
Engine stays free/offline unless the caller has opted into an LLM.
"""

from __future__ import annotations

from app.core.config import settings
from app.engines.providers.base import LLMProvider, ProviderError
from app.engines.providers.openai_compatible import OpenAICompatibleProvider

__all__ = ["LLMProvider", "ProviderError", "OpenAICompatibleProvider", "get_default_provider"]


def get_default_provider() -> LLMProvider | None:
    """Return the configured provider, or ``None`` when no API key is set.

    MARKED: this is the minimal base of the future Gateway (routing, budgets,
    fallbacks, caching). Today it only wires the OpenAI-compatible adapter.
    """
    if not settings.openai_api_key:
        return None
    return OpenAICompatibleProvider(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.intent_llm_model,
    )
