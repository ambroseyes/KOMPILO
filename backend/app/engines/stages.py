"""Pipeline stages.

``understand`` is a real implementation: it turns the raw intent into a validated
``UnderstandResult`` via a forced-tool LLM call. The remaining stages are still
STUB placeholders (clearly marked) so the end-to-end pipeline stays runnable and
testable until each is implemented for real.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import ValidationError

from app.core.config import settings
from app.engines.base import PipelineContext, Stage, StageResult
from app.engines.llm.base import LLMClient, LLMError
from app.engines.prompts.understand import (
    TOOL_DESCRIPTION,
    TOOL_NAME,
    build_system_prompt,
    build_user_message,
)
from app.schemas.understand import AmbiguitySeverity, UnderstandCore, UnderstandResult
from app.telemetry.logging import get_logger

logger = get_logger(__name__)

_STUB_NOTE = "STUB — placeholder output, not real reasoning."

# Base for the exponential backoff between retries (seconds); small so tests stay fast.
_BACKOFF_BASE_S = 0.1


class UnderstandStage(Stage):
    """Analyse the intent into a validated understanding via a forced tool call."""

    name = "understand"

    def __init__(self, llm: LLMClient | None) -> None:
        self._llm = llm

    async def run(self, ctx: PipelineContext) -> StageResult:
        intent = ctx.intent.strip()
        if not intent:
            return StageResult(self.name, "error", "empty intent")
        if self._llm is None:
            return StageResult(self.name, "error", "no LLM provider configured")

        system = build_system_prompt()
        user = build_user_message(intent, ctx.context)
        schema = UnderstandCore.model_json_schema()
        attempts = settings.llm_max_retries + 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                call = await self._llm.emit_tool(
                    system=system,
                    user=user,
                    tool_name=TOOL_NAME,
                    tool_description=TOOL_DESCRIPTION,
                    input_schema=schema,
                    model=settings.understand_model,
                    max_tokens=settings.llm_max_tokens,
                    temperature=0.0,
                )
                core = UnderstandCore.model_validate(call.arguments)
            except (LLMError, ValidationError) as exc:
                last_error = exc
                logger.warning("understand attempt %d/%d failed: %s", attempt + 1, attempts, exc)
                if attempt + 1 < attempts:
                    await asyncio.sleep(_BACKOFF_BASE_S * (2**attempt))
                continue

            result = self._finalize(core, model=call.model, usage=call.usage)
            output = result.model_dump(mode="json")
            ctx.artifacts[self.name] = output
            return StageResult(self.name, "ok", "understanding produced", output)

        return StageResult(
            self.name, "error", f"understand failed after {attempts} attempts: {last_error}"
        )

    def _finalize(
        self, core: UnderstandCore, *, model: str, usage: dict[str, int]
    ) -> UnderstandResult:
        """Derive needs_clarification deterministically and attach provenance."""
        needs_clarification = (
            any(a.severity is AmbiguitySeverity.HIGH for a in core.ambiguities)
            or core.confidence < settings.understand_confidence_threshold
        )
        return UnderstandResult.model_validate(
            {
                **core.model_dump(),
                "needs_clarification": needs_clarification,
                "model": model,
                "usage": usage,
            }
        )


class StrategizeStage(Stage):
    name = "strategize"

    async def run(self, ctx: PipelineContext) -> StageResult:
        output = {"approach": "single-step", "candidates": 1}  # STUB
        ctx.artifacts[self.name] = output
        return StageResult(self.name, "ok", _STUB_NOTE, output)


class CompileStage(Stage):
    name = "compile"

    async def run(self, ctx: PipelineContext) -> StageResult:
        output = {"plan": [{"step": 1, "action": "noop"}]}  # STUB
        ctx.artifacts[self.name] = output
        return StageResult(self.name, "ok", _STUB_NOTE, output)


class RouteStage(Stage):
    name = "route"

    async def run(self, ctx: PipelineContext) -> StageResult:
        output = {"target": "default-executor"}  # STUB
        ctx.artifacts[self.name] = output
        return StageResult(self.name, "ok", _STUB_NOTE, output)


class ExecuteStage(Stage):
    name = "execute"

    async def run(self, ctx: PipelineContext) -> StageResult:
        output = {"executed": False}  # STUB — no real execution
        ctx.artifacts[self.name] = output
        return StageResult(self.name, "skipped", _STUB_NOTE, output)


class VerifyStage(Stage):
    name = "verify"

    async def run(self, ctx: PipelineContext) -> StageResult:
        output = {"checks_passed": None}  # STUB
        ctx.artifacts[self.name] = output
        return StageResult(self.name, "skipped", _STUB_NOTE, output)


class EvaluateStage(Stage):
    name = "evaluate"

    async def run(self, ctx: PipelineContext) -> StageResult:
        output = {"score": None}  # STUB
        ctx.artifacts[self.name] = output
        return StageResult(self.name, "skipped", _STUB_NOTE, output)


class ImproveStage(Stage):
    name = "improve"

    async def run(self, ctx: PipelineContext) -> StageResult:
        output: dict[str, Any] = {"suggestions": []}  # STUB
        ctx.artifacts[self.name] = output
        return StageResult(self.name, "skipped", _STUB_NOTE, output)


def build_default_stages(llm: LLMClient | None) -> list[Stage]:
    """Canonical ordered pipeline, with the LLM client injected into understand."""
    return [
        UnderstandStage(llm),
        StrategizeStage(),
        CompileStage(),
        RouteStage(),
        ExecuteStage(),
        VerifyStage(),
        EvaluateStage(),
        ImproveStage(),
    ]
