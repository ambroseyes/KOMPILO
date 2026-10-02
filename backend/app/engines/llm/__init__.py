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
from app.engines.llm.fake import EchoLLMClient, FakeLLMClient
from app.telemetry.logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "LLMClient",
    "LLMToolCall",
    "LLMError",
    "LLMTimeout",
    "LLMBadOutput",
    "FakeLLMClient",
    "EchoLLMClient",
    "get_llm_client",
]


def get_llm_client(settings: Settings | None = None) -> LLMClient | None:
    """Return the configured LLM client, or ``None`` when none is available.

    - A configured Anthropic key: the real client (wired in a later change; until
      then the :class:`EchoLLMClient` stands in, logging a warning).
    - No key, non-production: the :class:`EchoLLMClient`, so dev and CI run
      key-less end-to-end without faking a real analysis.
    - No key, production: ``None`` — the understand stage then errors explicitly
      rather than returning an invented understanding.
    """
    cfg = settings or default_settings
    if cfg.anthropic_api_key:
        logger.warning(
            "ANTHROPIC_API_KEY is set but the real LLM client is not wired yet; "
            "using EchoLLMClient."
        )
        return EchoLLMClient()
    if cfg.is_production:
        logger.error("No LLM provider configured in production; understand will error.")
        return None
    return EchoLLMClient()
