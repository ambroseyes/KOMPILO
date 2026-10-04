"""Shared persistence for a completed pipeline run.

Both the synchronous ``/v1/execute`` route and the async ``/v1/executions`` worker run the
SAME ``KompiloPipeline`` and then persist the result the SAME way through this helper:
journal each step, build the REAL-cost metadata, and store the output blob (text +
metadata + verification + evaluation + improvements + trace + CATR). One pipeline, one
persistence path.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.orchestrator import PipelineOutcome
from app.models.execution import Execution
from app.models.execution_step import ExecutionStep
from app.schemas.execute import ExecuteMetadata, RealCost
from app.services.budget import record_usage


def build_metadata(result: PipelineOutcome) -> ExecuteMetadata:
    """REAL-cost + provider metadata for a succeeded run (``result.outcome`` set)."""
    outcome = result.outcome
    assert outcome is not None
    plan = result.compile.execution_plan
    note = (
        None
        if outcome.provider_is_real
        else "Offline STUB provider — output is not from a real model."
    )
    return ExecuteMetadata(
        provider=outcome.provider,
        provider_is_real=outcome.provider_is_real,
        model=plan.target_model if plan is not None else None,
        actual_cost=RealCost(
            input_tokens=outcome.total_input_tokens,
            output_tokens=outcome.total_output_tokens,
            cost_usd=outcome.total_cost_usd,
        ),
        latency_ms=outcome.total_latency_ms,
        cached=outcome.cached_any,
        note=note,
    )


async def persist_success(
    db: AsyncSession, execution: Execution, result: PipelineOutcome
) -> ExecuteMetadata:
    """Journal steps + finalize a succeeded execution. Returns its metadata."""
    outcome = result.outcome
    assert outcome is not None and result.verification is not None
    assert result.evaluation is not None and result.improvements is not None

    for step in outcome.steps:
        db.add(
            ExecutionStep(
                tenant_id=execution.tenant_id,
                execution_id=execution.id,
                step_order=step.order,
                action=step.action,
                input={"prompt": step.input_prompt, "repaired": step.repaired},
                output=step.output,
                input_tokens=step.input_tokens,
                output_tokens=step.output_tokens,
                cost_usd=step.cost_usd,
                model=step.model,
                cached=step.cached,
                latency_ms=step.latency_ms,
            )
        )

    metadata = build_metadata(result)
    execution.status = "succeeded"
    execution.output = {
        "text": outcome.output,
        "metadata": metadata.model_dump(),
        "verification": result.verification.model_dump(),
        "evaluation": result.evaluation.model_dump(),
        "improvements": result.improvements.model_dump(),
        "trace": result.trace,
        "catr": result.catr.model_dump(mode="json"),
    }
    execution.finished_at = func.now()

    # Meter this run (append-only) so per-tenant budgets/quotas can be enforced.
    await record_usage(
        db,
        tenant_id=execution.tenant_id,
        execution_id=execution.id,
        created_by=execution.created_by,
        cost_usd=metadata.actual_cost.cost_usd,
        input_tokens=metadata.actual_cost.input_tokens,
        output_tokens=metadata.actual_cost.output_tokens,
        provider_is_real=metadata.provider_is_real,
    )
    return metadata
