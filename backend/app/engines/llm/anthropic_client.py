"""Anthropic implementation of the :class:`~app.engines.llm.base.LLMClient` port.

Calls the Messages API asking the model to return structured JSON through a tool
whose ``input_schema`` is ``UnderstandCore``'s JSON Schema. ``tool_choice`` stays
``auto`` (portable across models that reject forced tool use) with ``strict`` on
the tool for schema-valid arguments; the stage re-validates the payload and
retries when no conforming tool call comes back.
"""

from __future__ import annotations

from typing import Any

from anthropic import APIError, APITimeoutError, AsyncAnthropic

from app.engines.llm.base import LLMBadOutput, LLMError, LLMTimeout, LLMToolCall


class AnthropicClient:
    """Thin adapter over the async Anthropic SDK that emits one tool call."""

    def __init__(self, api_key: str, *, timeout_s: float = 30.0) -> None:
        self._client = AsyncAnthropic(api_key=api_key, timeout=timeout_s)

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
        tool: dict[str, Any] = {
            "name": tool_name,
            "description": tool_description,
            "input_schema": input_schema,
            "strict": True,
        }
        messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
        try:
            # ``temperature`` is intentionally not forwarded: it is not part of the
            # SDK's typed create() signature here and several current models reject
            # non-default sampling. It stays in the port for the fake/other clients.
            response = await self._client.messages.create(  # type: ignore[call-overload]
                model=model,
                max_tokens=max_tokens,
                system=system,
                tools=[tool],
                tool_choice={"type": "auto"},
                messages=messages,
            )
        except APITimeoutError as exc:
            raise LLMTimeout(str(exc)) from exc
        except APIError as exc:
            raise LLMError(str(exc)) from exc

        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                arguments = block.input
                if not isinstance(arguments, dict):
                    raise LLMBadOutput("tool_use.input was not a JSON object")
                usage = {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                }
                return LLMToolCall(
                    name=tool_name,
                    arguments=arguments,
                    model=response.model,
                    usage=usage,
                )

        raise LLMBadOutput(f"model did not call the {tool_name} tool")
