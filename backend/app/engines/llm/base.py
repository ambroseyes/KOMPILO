"""LLM client port: the narrow interface the pipeline depends on.

Keeping this a ``Protocol`` means stages never import a vendor SDK directly and
stay unit-testable without a network or API key. Two implementations satisfy it:
``AnthropicClient`` (real, added later) and :class:`~app.engines.llm.fake.FakeLLMClient`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMError(Exception):
    """Base class for LLM call failures."""


class LLMTimeout(LLMError):
    """The provider did not respond within the configured timeout."""


class LLMBadOutput(LLMError):
    """The model returned no tool call, or an unparseable payload."""


@dataclass(frozen=True)
class LLMToolCall:
    """A single forced tool call returned by the model."""

    name: str
    arguments: dict[str, Any]
    model: str
    usage: dict[str, int] = field(default_factory=dict)


class LLMClient(Protocol):
    """A minimal async port: force one tool call and return its parsed payload."""

    async def emit_tool(
        self,
        *,
        system: str,
        user: str,
        tool_name: str,
        tool_description: str,
        input_schema: dict[str, Any],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMToolCall:
        """Call the model forcing ``tool_name`` and return the parsed tool call.

        Raises :class:`LLMTimeout`, :class:`LLMBadOutput`, or :class:`LLMError`.
        """
        ...
