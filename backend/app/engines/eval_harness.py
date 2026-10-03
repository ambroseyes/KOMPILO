"""Evaluation harness — measure a compiled prompt over a set of cases (V1.5 #1).

The harness is the shared measurement primitive behind both the version comparator and the
auto-improvement loop. For each case it:

1. compiles the case task once (Kompilo Core) to obtain the case's CanonicalAITask (the
   shared yardstick) and a concrete execution plan;
2. executes a *given compiled prompt* against the case input through the Executor/Gateway
   (real provider, or the offline Echo STUB when no key);
3. verifies the output's format and measures it with the Evaluator (``rules-v1``).

It never invents a verdict: it returns per-case measurements and deterministic aggregates.
The ``provider_is_real`` flag propagates so callers can flag a ranking produced over stub
outputs as not meaningful.
"""

from __future__ import annotations

from app.core.config import settings
from app.engines.evaluator import Evaluator
from app.engines.executor import Executor
from app.engines.kompilo_core import KompiloCore
from app.engines.verifier import verify_output
from app.schemas.benchmark import AggregateScore, CaseScore, EvalCase
from app.schemas.catr import CanonicalAITask
from app.schemas.compile import CostEstimate, ExecutionPlan, ExecutionStep

_EXCERPT_CHARS = 280

# Shown whenever a measurement ran over the offline Echo STUB (no real provider key).
STUB_NOTE = (
    "Sorties produites par le STUB Echo hors-ligne (aucune clé LLM) : le classement n'est "
    "PAS significatif. Configure OPENAI_API_KEY pour une comparaison réelle."
)


def _fallback_plan() -> ExecutionPlan:
    """A single-step generate plan when a case compiles to ASK (no plan). Uses the
    gateway's default model so the Executor always has a model to call."""
    return ExecutionPlan(
        strategy="single",
        target_model=settings.execution_llm_model,
        fallback_models=[],
        steps=[ExecutionStep(order=1, action="generate", detail="Generate the answer.")],
        cost=CostEstimate(input_tokens_est=0, output_tokens_est=0, cost_usd_est=0.0),
    )


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def aggregate(label: str, cases: list[CaseScore]) -> AggregateScore:
    """Deterministically aggregate per-case measurements (mean score, pass rate, and the
    mean of each criterion across cases)."""
    mean_score = _mean([c.score for c in cases])
    pass_rate = round(sum(1 for c in cases if c.passed) / len(cases), 3) if cases else 0.0
    by_name: dict[str, list[float]] = {}
    for case in cases:
        for crit in case.criteria:
            by_name.setdefault(crit.name, []).append(crit.score)
    per_criterion = {name: _mean(scores) for name, scores in sorted(by_name.items())}
    return AggregateScore(
        label=label,
        mean_score=mean_score,
        pass_rate=pass_rate,
        per_criterion=per_criterion,
        cases=cases,
    )


class EvalHarness:
    def __init__(self, core: KompiloCore | None = None, executor: Executor | None = None) -> None:
        self._core = core or KompiloCore()
        self._executor = executor or Executor()
        self._evaluator = Evaluator()

    async def prepare_case(self, case: EvalCase) -> tuple[CanonicalAITask, ExecutionPlan]:
        """Compile the case once to get its CATR (the shared yardstick) and a plan."""
        response, catr = await self._core.compile_with_catr(
            case.task, mode="professional", output_format=case.output_format
        )
        plan = response.execution_plan or _fallback_plan()
        return catr, plan

    async def measure(
        self,
        *,
        compiled_prompt: str,
        case: EvalCase,
        case_catr: CanonicalAITask,
        plan: ExecutionPlan,
        tenant_id: str,
    ) -> CaseScore:
        """Execute ``compiled_prompt`` against the case input and measure the output.

        The case task is appended as a delimited input so the same prompt (instruction) is
        applied to the case, then the output is verified and scored against the case's CATR.
        """
        combined = f"{compiled_prompt}\n\n<input>\n{case.task}\n</input>"
        json_mode = case.output_format.lower() == "json"
        outcome = await self._executor.run(
            plan=plan, compiled_prompt=combined, tenant_id=tenant_id, json_mode=json_mode
        )
        verification = verify_output(outcome.output, output_format=case.output_format)
        evaluation = self._evaluator.evaluate(
            outcome.output, catr=case_catr, verification=verification
        )
        return CaseScore(
            case=case.name,
            score=evaluation.score,
            passed=evaluation.passed,
            criteria=evaluation.criteria,
            provider_is_real=outcome.provider_is_real,
            output_excerpt=outcome.output[:_EXCERPT_CHARS],
        )
