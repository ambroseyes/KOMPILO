"""LLM client package: the port, implementations, and a factory.

Stages depend only on the :class:`LLMClient` protocol, never on a vendor SDK, so
they stay unit-testable without a network or an API key. The real Anthropic
implementation is wired in a later change; until then the factory returns the
:class:`FakeLLMClient`.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.engines.llm.base import (
    LLMBadOutput,
    LLMClient,
    LLMError,
    LLMTimeout,
    LLMToolCall,
)
from app.engines.llm.fake import FakeLLMClient
from app.telemetry.logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "LLMClient",
    "LLMToolCall",
    "LLMError",
    "LLMTimeout",
    "LLMBadOutput",
    "FakeLLMClient",
    "get_llm_client",
]


def get_llm_client(settings: Settings | None = None) -> LLMClient | None:
    """Return the configured LLM client, or ``None`` when none is available.

    - A configured Anthropic key: the real :class:`AnthropicClient` (``claude-v1``).
    - No key: ``None`` — the caller (``understand``) then uses the deterministic
      heuristic analyzer. No client ever stands in for a real analysis, so the
      ``Catr.method`` marker is always truthful.
    """
    cfg = settings or default_settings
    if cfg.anthropic_api_key:
        # Lazy import so the vendor SDK is only loaded when a key is configured.
        from app.engines.llm.anthropic_client import AnthropicClient

        return AnthropicClient(cfg.anthropic_api_key, timeout_s=cfg.llm_timeout_s)
    return None
