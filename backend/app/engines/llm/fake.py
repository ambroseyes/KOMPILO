"""In-memory LLM client for tests and key-less environments.

Returns pre-seeded tool calls (or raises pre-seeded exceptions) in order, and
records every call so tests can assert on the prompts sent and the call count.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.engines.llm.base import LLMBadOutput, LLMToolCall


@dataclass
class RecordedCall:
    """What a single ``emit_tool`` invocation was asked to do."""

    system: str
    user: str
    tool_name: str
    model: str


class FakeLLMClient:
    """A scripted :class:`~app.engines.llm.base.LLMClient`.

    Each ``emit_tool`` pops the next queued response: an :class:`LLMToolCall` is
    returned, an :class:`Exception` is raised. With nothing queued, it raises
    :class:`LLMBadOutput` (so a test that forgets to queue fails loudly).
    """

    def __init__(self, responses: list[LLMToolCall | Exception] | None = None) -> None:
        self._responses: list[LLMToolCall | Exception] = list(responses or [])
        self.calls: list[RecordedCall] = []

    def queue(self, response: LLMToolCall | Exception) -> None:
        self._responses.append(response)

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
        self.calls.append(RecordedCall(system=system, user=user, tool_name=tool_name, model=model))
        if not self._responses:
            raise LLMBadOutput("FakeLLMClient has no queued response")
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    @property
    def call_count(self) -> int:
        return len(self.calls)
