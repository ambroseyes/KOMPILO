"""Pipeline stages.

``understand`` is REAL: it turns the raw intent into a validated ``Catr`` via
``app.engines.understand.understand`` — a Claude-backed analysis when a provider is
configured (``claude-v1``), otherwise a deterministic heuristic (``heuristic-v1``).
The remaining stages are still STUB placeholders (clearly marked) so the end-to-end
pipeline stays runnable and testable until each is implemented for real.
"""

from __future__ import annotations

from typing import Any

from app.engines.base import PipelineContext, Stage, StageResult
from app.engines.understand import understand
from app.telemetry.logging import get_logger

logger = get_logger(__name__)

_STUB_NOTE = "STUB — placeholder output, not real reasoning."
_METHOD_NOTE = {
    "heuristic-v1": "Deterministic heuristic analysis (heuristic-v1); not an LLM.",
    "claude-v1": "Claude-backed analysis (claude-v1).",
}


class UnderstandStage(Stage):
    """REAL — turns the intent into a CATR via ``understand`` (LLM or heuristic)."""

    name = "understand"

    async def run(self, ctx: PipelineContext) -> StageResult:
        intent = ctx.intent.strip()
        if not intent:
            return StageResult(self.name, "error", "empty intent", is_stub=False)
        catr = await understand(intent, ctx.context)
        output = catr.model_dump()
        ctx.artifacts[self.name] = output
        note = _METHOD_NOTE.get(catr.method, f"understand ({catr.method})")
        return StageResult(self.name, "ok", note, output, is_stub=False)


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


def build_default_stages() -> list[Stage]:
    """Canonical ordered pipeline."""
    return [
        UnderstandStage(),
        StrategizeStage(),
        CompileStage(),
        RouteStage(),
        ExecuteStage(),
        VerifyStage(),
        EvaluateStage(),
        ImproveStage(),
    ]
