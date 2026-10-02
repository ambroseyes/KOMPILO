"""Pipeline stages.

STUB / PLACEHOLDER: every stage below returns deterministic placeholder output
so the end-to-end pipeline is runnable and testable. NONE of this is real AI
reasoning yet — each stage is explicitly marked and MUST be replaced with the
real implementation.
"""

from __future__ import annotations

from typing import Any

from app.engines.base import PipelineContext, Stage, StageResult

_STUB_NOTE = "STUB — placeholder output, not real reasoning."


class UnderstandStage(Stage):
    name = "understand"

    async def run(self, ctx: PipelineContext) -> StageResult:
        output = {"normalized_intent": ctx.intent.strip(), "entities": []}  # STUB
        ctx.artifacts[self.name] = output
        return StageResult(self.name, "ok", _STUB_NOTE, output)


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


# Canonical ordered pipeline.
DEFAULT_STAGES: list[Stage] = [
    UnderstandStage(),
    StrategizeStage(),
    CompileStage(),
    RouteStage(),
    ExecuteStage(),
    VerifyStage(),
    EvaluateStage(),
    ImproveStage(),
]
