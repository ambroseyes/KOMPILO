"""Unit test for the single KompiloPipeline orchestrator (no DB, mocked execution)."""

from __future__ import annotations

import pytest

from app.engines.executor import ExecutionOutcome, StepOutcome
from app.engines.orchestrator import KompiloPipeline


class _FakeExecutor:
    """Deterministic stand-in for the real Executor/Gateway (no network, no model)."""

    async def run(
        self,
        *,
        plan: object,
        compiled_prompt: str,
        tenant_id: str,
        json_mode: bool = False,
        retrieval_query: str | None = None,
    ) -> ExecutionOutcome:
        step = StepOutcome(
            order=1,
            action="generate",
            input_prompt=compiled_prompt,
            output="Bienvenue chaleureux chez nous, cher nouveau client !",
            input_tokens=12,
            output_tokens=8,
            cost_usd=0.00001,
            model="fake-model",
            cached=False,
            latency_ms=3,
        )
        return ExecutionOutcome(
            output=step.output,
            steps=[step],
            total_input_tokens=12,
            total_output_tokens=8,
            total_cost_usd=0.00001,
            total_latency_ms=3,
            provider="fake",
            provider_is_real=True,
            cached_any=False,
        )


@pytest.mark.asyncio
async def test_full_pipeline_proceeds_through_all_stages() -> None:
    pipe = KompiloPipeline(executor=_FakeExecutor())  # type: ignore[arg-type]
    result = await pipe.run(
        task="Rédige un message de bienvenue chaleureux pour un nouveau client",
        tenant_id="t1",
    )
    assert result.status == "succeeded"
    assert result.outcome is not None and result.outcome.output
    assert result.verification is not None and result.verification.valid is True
    # Evaluate + improve are now REAL stages.
    assert result.evaluation is not None and result.evaluation.measured is True
    assert result.improvements is not None
    stages = [t["stage"] for t in result.trace]
    assert stages == [
        "understand",
        "strategize",
        "compile",
        "execute",
        "verify",
        "evaluate",
        "improve",
    ]


@pytest.mark.asyncio
async def test_ambiguous_task_stops_at_strategize() -> None:
    pipe = KompiloPipeline(executor=_FakeExecutor())  # type: ignore[arg-type]
    result = await pipe.run(task="truc", tenant_id="t1")
    assert result.status == "needs_clarification"
    assert result.questions  # at least one clarifying question
    assert result.outcome is None and result.evaluation is None
    stages = [t["stage"] for t in result.trace]
    assert stages[-1] == "strategize" and "execute" not in stages
