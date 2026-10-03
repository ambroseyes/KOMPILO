"""Auto-improvement loop — rewrite from grounded signals, re-measure, converge (V1.5 #1).

Each iteration compiles the current task (Kompilo Core), measures the compiled prompt over
the case set via the :class:`EvalHarness` (Evaluator ``rules-v1``), and asks the Improver
for GROUNDED suggestions (derived from the iteration's diagnostics + its weakest measured
case — never invented). The suggestions are folded deterministically into the quality
contract — the "rewrite" — which changes the next compilation's prompt. The loop stops when
the measured score reaches the target, stops improving (converged), has nothing left to
fold, or hits ``max_iterations``.

Honest throughout: with the offline Echo STUB the measured scores won't move, so the loop
converges immediately and the result is flagged ``provider_is_real=false``.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.engines.eval_harness import STUB_NOTE, EvalHarness, aggregate
from app.engines.improver import Improver
from app.engines.kompilo_core import KompiloCore
from app.schemas.benchmark import (
    EvalCase,
    ImprovementLoopResult,
    LoopIteration,
)
from app.schemas.compile import CompileMode
from app.schemas.evaluate import EvaluationReport

# A gain at or below this is "no real improvement" → the loop has converged.
_CONVERGENCE_EPS = 0.01


@dataclass(frozen=True, slots=True)
class _IterationState:
    quality_contract: list[str]
    compiled_prompt: str
    mean_score: float


class ImproveLoop:
    def __init__(self, core: KompiloCore | None = None, harness: EvalHarness | None = None) -> None:
        self._core = core or KompiloCore()
        self._harness = harness or EvalHarness(core=self._core)
        self._improver = Improver()

    async def run(
        self,
        *,
        task: str,
        cases: list[EvalCase],
        mode: CompileMode = "professional",
        output_format: str = "markdown",
        target_model: str | None = None,
        quality_contract: list[str] | None = None,
        max_iterations: int = 3,
        target_score: float = 0.9,
        tenant_id: str,
    ) -> ImprovementLoopResult:
        current_contract = list(quality_contract or [])
        effective_cases = cases or [EvalCase(name="task", task=task, output_format=output_format)]

        iterations: list[LoopIteration] = []
        states: list[_IterationState] = []
        provider_real = False
        stop_reason = "max_iterations"

        for i in range(1, max_iterations + 1):
            response, catr = await self._core.compile_with_catr(
                task,
                target_model=target_model,
                mode=mode,
                output_format=output_format,
                quality_contract=current_contract,
            )
            if response.compiled_prompt is None:  # ASK — cannot execute/measure
                stop_reason = "needs_clarification"
                break
            compiled = response.compiled_prompt.text

            # Measure the compiled prompt over every case (shared yardstick per case).
            case_scores = []
            for case in effective_cases:
                case_catr, plan = await self._harness.prepare_case(case)
                case_scores.append(
                    await self._harness.measure(
                        compiled_prompt=compiled,
                        case=case,
                        case_catr=case_catr,
                        plan=plan,
                        tenant_id=tenant_id,
                    )
                )
            agg = aggregate(f"iteration {i}", case_scores)
            provider_real = provider_real or any(s.provider_is_real for s in case_scores)

            # Grounded improvements: driven by the diagnostics + the weakest measured case.
            worst = min(case_scores, key=lambda s: s.score)
            weak_eval = EvaluationReport(
                score=worst.score,
                passed=worst.passed,
                criteria=worst.criteria,
                summary=f"cas le plus faible : {worst.case}",
            )
            report = self._improver.suggest(
                catr=catr, diagnostics=response.diagnostics, evaluation=weak_eval
            )
            # Fold the grounded suggestions into the quality contract (dedup) — the rewrite.
            existing = {c.strip().casefold() for c in current_contract}
            added = [
                imp.suggestion
                for imp in report.improvements
                if imp.suggestion.strip().casefold() not in existing
            ]

            iterations.append(
                LoopIteration(
                    iteration=i,
                    mean_score=agg.mean_score,
                    pass_rate=agg.pass_rate,
                    n_improvements=len(report.improvements),
                    added_contract=added,
                )
            )
            states.append(
                _IterationState(
                    quality_contract=list(current_contract),
                    compiled_prompt=compiled,
                    mean_score=agg.mean_score,
                )
            )

            if agg.mean_score >= target_score:
                stop_reason = "target_reached"
                break
            if not added:
                stop_reason = "no_improvements"
                break
            if i > 1 and agg.mean_score - iterations[-2].mean_score <= _CONVERGENCE_EPS:
                stop_reason = "converged"
                break

            current_contract = [*current_contract, *added]

        if not states:  # only reachable via needs_clarification on the first compile
            return ImprovementLoopResult(
                status="needs_clarification",
                iterations=iterations,
                best_iteration=0,
                best_score=0.0,
                best_quality_contract=current_contract,
                best_compiled_prompt=None,
                stop_reason=stop_reason,
                provider_is_real=False,
                summary="Tâche trop ambiguë pour être compilée/exécutée ; clarification requise.",
                note="Aucune mesure : le pipeline s'arrête avant exécution sur une tâche ambiguë.",
            )

        best_idx = max(range(len(states)), key=lambda k: states[k].mean_score)
        best = states[best_idx]
        note = (
            STUB_NOTE
            if not provider_real
            else "Mesure reproductible rules-v1 (proxy heuristique, pas un juge LLM)."
        )
        summary = (
            f"{len(iterations)} itération(s) ; meilleur score {best.mean_score:.2f} "
            f"(itération {best_idx + 1}) ; arrêt : {stop_reason}"
        )
        return ImprovementLoopResult(
            status="succeeded",
            iterations=iterations,
            best_iteration=best_idx + 1,
            best_score=best.mean_score,
            best_quality_contract=best.quality_contract,
            best_compiled_prompt=best.compiled_prompt,
            stop_reason=stop_reason,
            provider_is_real=provider_real,
            summary=summary,
            note=note,
        )
