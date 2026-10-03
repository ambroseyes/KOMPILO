"""Kompilo Pipeline — the SINGLE full-lifecycle orchestrator.

One place runs the whole pipeline:

    understand → strategize → compile → (ASK ⇒ stop) → execute → verify → evaluate → improve

It is PURE (no database, no HTTP): the synchronous ``/v1/execute`` route and the async
``/v1/executions`` worker both call it and add their own persistence around it, so there
is exactly one pipeline. Compilation is deterministic (Kompilo Core); execution goes
through the Gateway (real provider, or the offline Echo STUB when no key). On an ambiguous
task it stops after compile and returns the clarifying questions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.engines.evaluator import Evaluator
from app.engines.executor import ExecutionOutcome, Executor
from app.engines.improver import Improver
from app.engines.kompilo_core import KompiloCore
from app.engines.verifier import verify_output
from app.schemas.catr import CanonicalAITask
from app.schemas.compile import CompileMode, CompileResponse
from app.schemas.evaluate import EvaluationReport
from app.schemas.improve import ImprovementReport
from app.schemas.verify import VerificationReport


@dataclass
class PipelineOutcome:
    """Everything a single full run produced (consumed by the route/worker wrappers)."""

    status: str  # "succeeded" | "needs_clarification"
    compile: CompileResponse
    catr: CanonicalAITask
    questions: list[str]
    outcome: ExecutionOutcome | None = None
    verification: VerificationReport | None = None
    evaluation: EvaluationReport | None = None
    improvements: ImprovementReport | None = None
    trace: list[dict[str, str]] = field(default_factory=list)


class KompiloPipeline:
    def __init__(self, core: KompiloCore | None = None, executor: Executor | None = None) -> None:
        self._core = core or KompiloCore()
        self._executor = executor  # injected in tests; built lazily otherwise

    def _make_executor(self) -> Executor:
        return self._executor if self._executor is not None else Executor()

    async def run(
        self,
        *,
        task: str,
        tenant_id: str,
        mode: CompileMode = "professional",
        output_format: str = "markdown",
        target_model: str | None = None,
        quality_contract: list[str] | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> PipelineOutcome:
        quality_contract = quality_contract or []
        trace: list[dict[str, str]] = []

        response, catr = await self._core.compile_with_catr(
            task,
            target_model=target_model,
            mode=mode,
            output_format=output_format,
            quality_contract=quality_contract,
        )
        trace.append({"stage": "understand", "status": "ok"})

        # ── ASK: stop after compile, surface the questions. ─────────────────────────
        if (
            response.questions
            or response.execution_plan is None
            or response.compiled_prompt is None
        ):
            trace.append({"stage": "strategize", "status": "ask"})
            return PipelineOutcome(
                status="needs_clarification",
                compile=response,
                catr=catr,
                questions=response.questions,
                trace=trace,
            )

        trace.append({"stage": "strategize", "status": "ok"})
        trace.append({"stage": "compile", "status": "ok"})

        json_mode = output_format.lower() == "json"
        outcome = await self._make_executor().run(
            plan=response.execution_plan,
            compiled_prompt=response.compiled_prompt.text,
            tenant_id=tenant_id,
            json_mode=json_mode,
        )
        trace.append({"stage": "execute", "status": "ok"})

        verification = verify_output(
            outcome.output, output_format=output_format, output_schema=output_schema
        )
        trace.append({"stage": "verify", "status": "ok" if verification.valid else "warn"})

        evaluation = Evaluator().evaluate(
            outcome.output,
            catr=catr,
            verification=verification,
            quality_contract=quality_contract,
        )
        trace.append({"stage": "evaluate", "status": "ok" if evaluation.passed else "warn"})

        improvements = Improver().suggest(
            catr=catr, diagnostics=response.diagnostics, evaluation=evaluation
        )
        trace.append({"stage": "improve", "status": "ok"})

        return PipelineOutcome(
            status="succeeded",
            compile=response,
            catr=catr,
            questions=[],
            outcome=outcome,
            verification=verification,
            evaluation=evaluation,
            improvements=improvements,
            trace=trace,
        )
