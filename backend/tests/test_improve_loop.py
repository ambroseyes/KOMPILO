"""No-DB unit tests for the auto-improvement loop (V1.5 #1).

Deterministic and offline: Kompilo Core compiles without a key; the Executor is faked so
the loop's control flow (measure → ground-rewrite → re-measure → stop) is exercised with
no network or database.
"""

from __future__ import annotations

from app.engines.eval_harness import EvalHarness
from app.engines.executor import ExecutionOutcome, StepOutcome
from app.engines.improve_loop import ImproveLoop


class _FixedExecutor:
    """Returns a fixed, substantive output (never satisfies a high target) so the loop
    iterates and folds grounded suggestions rather than stopping on the first round."""

    def __init__(self, *, output: str = "Une réponse correcte mais imparfaite.", real: bool = True):
        self._output = output
        self._real = real

    async def run(
        self, *, plan: object, compiled_prompt: str, tenant_id: str, json_mode: bool = False
    ) -> ExecutionOutcome:
        step = StepOutcome(
            order=1,
            action="generate",
            input_prompt=compiled_prompt,
            output=self._output,
            input_tokens=10,
            output_tokens=10,
            cost_usd=0.0,
            model="fake",
            cached=False,
            latency_ms=1,
        )
        return ExecutionOutcome(
            output=self._output, steps=[step], provider="fake", provider_is_real=self._real
        )


def _loop(*, real: bool = True) -> ImproveLoop:
    return ImproveLoop(harness=EvalHarness(executor=_FixedExecutor(real=real)))  # type: ignore[arg-type]


_TASK = "Rédige un article clair sur la photosynthèse avec des exemples"
_STOP_REASONS = {"target_reached", "converged", "no_improvements", "max_iterations"}


async def test_loop_runs_and_reports_a_bounded_trajectory() -> None:
    result = await _loop().run(task=_TASK, cases=[], max_iterations=3, tenant_id="t1")
    assert result.status == "succeeded"
    assert 1 <= len(result.iterations) <= 3
    assert [it.iteration for it in result.iterations] == list(range(1, len(result.iterations) + 1))
    assert 1 <= result.best_iteration <= len(result.iterations)
    assert result.stop_reason in _STOP_REASONS
    assert result.best_compiled_prompt


async def test_loop_folds_grounded_suggestions_into_the_contract() -> None:
    # A weak, generic output leaves measured criteria failing → the Improver yields
    # grounded suggestions that the loop folds into the quality contract for the next run.
    result = await _loop().run(task=_TASK, cases=[], max_iterations=3, tenant_id="t1")
    folded_any = any(it.added_contract for it in result.iterations)
    improved_any = any(it.n_improvements for it in result.iterations)
    assert improved_any
    # Either it folded suggestions, or it stopped because there was nothing new to fold.
    assert folded_any or result.stop_reason == "no_improvements"


async def test_loop_stub_provider_is_flagged() -> None:
    result = await _loop(real=False).run(task=_TASK, cases=[], max_iterations=2, tenant_id="t1")
    assert result.provider_is_real is False
    assert "STUB" in result.note


async def test_loop_stops_on_ambiguous_task_needing_clarification() -> None:
    result = await _loop().run(task="truc", cases=[], max_iterations=3, tenant_id="t1")
    assert result.status == "needs_clarification"
    assert result.stop_reason == "needs_clarification"
    assert result.best_compiled_prompt is None


async def test_loop_respects_max_iterations_upper_bound() -> None:
    result = await _loop().run(task=_TASK, cases=[], max_iterations=1, tenant_id="t1")
    assert len(result.iterations) == 1
