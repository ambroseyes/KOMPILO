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


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    """Return the configured LLM client.

    With no Anthropic API key configured, returns a :class:`FakeLLMClient` so dev
    and CI run key-less. The real ``AnthropicClient`` is introduced in a
    subsequent change; a configured key logs a warning until then.
    """
    cfg = settings or default_settings
    if cfg.anthropic_api_key:
        logger.warning(
            "ANTHROPIC_API_KEY is set but the real LLM client is not wired yet; "
            "using FakeLLMClient."
        )
    return FakeLLMClient()
