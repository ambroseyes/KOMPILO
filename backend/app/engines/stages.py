"""Pipeline stages.

STUB / PLACEHOLDER: every stage below returns deterministic placeholder output
so the end-to-end pipeline is runnable and testable. NONE of this is real AI
reasoning yet — each stage is explicitly marked and MUST be replaced with the
real implementation.
"""

from __future__ import annotations

from typing import Any

from app.engines.ambiguity import AmbiguityEngine
from app.engines.base import PipelineContext, Stage, StageResult
from app.engines.complexity import ComplexityEngine
from app.engines.intent import IntentEngine
from app.engines.router import ModelRouter
from app.engines.strategy import StrategyEngine
from app.schemas.catr import CanonicalAITask
from app.schemas.strategize import StrategizeResult

_STUB_NOTE = "STUB — placeholder output, not real reasoning."


class UnderstandStage(Stage):
    """REAL — turns the intent into a CATR via the Intent Engine (heuristics + optional LLM)."""

    name = "understand"

    async def run(self, ctx: PipelineContext) -> StageResult:
        catr = await IntentEngine().run(ctx.intent)
        output = catr.model_dump()
        ctx.artifacts[self.name] = output
        note = (
            "Intent Engine v1 (heuristics + LLM refinement)."
            if catr.meta.enriched_by_llm
            else "Intent Engine v1 (deterministic heuristics; no LLM called)."
        )
        return StageResult(self.name, "ok", note, output)


class StrategizeStage(Stage):
    """REAL — consumes the CATR and runs ambiguity → complexity → strategy → routing."""

    name = "strategize"

    async def run(self, ctx: PipelineContext) -> StageResult:
        raw = ctx.artifacts.get("understand")
        if not isinstance(raw, dict):
            return StageResult(self.name, "error", "No CATR available from the understand stage.")
        catr = CanonicalAITask.model_validate(raw)

        ambiguity = AmbiguityEngine().analyze(catr)
        complexity = ComplexityEngine().assess(catr)
        strategy = StrategyEngine().decide(catr, complexity)
        route = ModelRouter().route(catr, strategy, complexity)
        result = StrategizeResult(
            ambiguity=ambiguity, complexity=complexity, strategy=strategy, route=route
        )
        output = result.model_dump()
        ctx.artifacts[self.name] = output

        note = (
            f"decision={ambiguity.decision}; complexity={complexity.level}; "
            f"strategy={strategy.kind}; model={route.primary}"
        )
        if ambiguity.decision == "ASK":
            note = "Clarification recommended before execution — " + note
        return StageResult(self.name, "ok", note, output)


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
