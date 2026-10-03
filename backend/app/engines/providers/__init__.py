"""LLM provider adapters — the Model Abstraction Layer behind the Gateway.

Two factories, two policies:
- ``get_default_provider()`` → the real provider, or ``None`` when no key is set. The
  Intent Engine uses this so it stays on heuristics unless a real LLM is configured.
- ``get_execution_provider()`` → the real provider, or the deterministic offline
  ``EchoProvider`` (a STUB) when no key is set, so ``/v1/execute`` is runnable offline.
"""

from __future__ import annotations

from app.core.config import settings
from app.engines.providers.base import (
    CompletionResult,
    LLMProvider,
    ProviderCapabilities,
    ProviderError,
)
from app.engines.providers.echo import EchoProvider
from app.engines.providers.embeddings import (
    Embedder,
    EmbeddingResult,
    OfflineHashEmbedder,
    OpenAICompatibleEmbedder,
)
from app.engines.providers.openai_compatible import OpenAICompatibleProvider

__all__ = [
    "LLMProvider",
    "ProviderError",
    "CompletionResult",
    "ProviderCapabilities",
    "OpenAICompatibleProvider",
    "EchoProvider",
    "Embedder",
    "EmbeddingResult",
    "OfflineHashEmbedder",
    "OpenAICompatibleEmbedder",
    "get_default_provider",
    "get_execution_provider",
    "get_embedder",
]


def _real_provider() -> OpenAICompatibleProvider | None:
    if not settings.openai_api_key:
        return None
    return OpenAICompatibleProvider(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.intent_llm_model,
    )


def get_default_provider() -> LLMProvider | None:
    """Real provider, or None when no key is set (Intent Engine stays on heuristics)."""
    return _real_provider()


def get_execution_provider() -> LLMProvider:
    """Real provider, or the offline Echo STUB when no key is set (execution is runnable)."""
    return _real_provider() or EchoProvider()


def get_embedder() -> Embedder:
    """Real OpenAI-compatible embedder, or the offline hash STUB when no key is set."""
    if not settings.openai_api_key:
        return OfflineHashEmbedder()
    return OpenAICompatibleEmbedder(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.embedding_model,
    )
