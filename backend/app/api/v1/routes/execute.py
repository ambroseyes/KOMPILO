"""POST /v1/execute — compile a task then run the plan through the Gateway.

Authenticated + tenant-scoped (it persists an execution and its steps). Deterministic
up to the provider: with no API key the offline Echo STUB runs (flagged in metadata).
Idempotent via an optional ``Idempotency-Key`` header. Cost is REAL (from token usage ×
registry prices), 0 on a Gateway cache hit — distinct from the compile-time estimate.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, TenantSession, get_current_user
from app.core.redis import get_redis
from app.engines.executor import Executor
from app.engines.gateway import GatewayError
from app.engines.kompilo_core import KompiloCore
from app.engines.verifier import verify_output
from app.models.execution import Execution
from app.models.execution_step import ExecutionStep
from app.models.prompt import PromptVersion
from app.schemas.execute import (
    ExecuteMetadata,
    ExecuteRequest,
    ExecuteResponse,
    ExecuteStepResult,
    RealCost,
)
from app.schemas.verify import VerificationReport

router = APIRouter(dependencies=[Depends(get_current_user)])

_IDEM_TTL_SECONDS = 24 * 3600


def _idem_key(tenant_id: uuid.UUID, key: str) -> str:
    return f"komp:idem:{tenant_id}:{key}"


async def _steps_response(db: AsyncSession, execution_id: uuid.UUID) -> list[ExecuteStepResult]:
    stmt = (
        select(ExecutionStep)
        .where(ExecutionStep.execution_id == execution_id)
        .order_by(ExecutionStep.step_order)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        ExecuteStepResult(
            order=r.step_order,
            action=r.action,
            output=r.output or "",
            model=r.model or "-",
            input_tokens=r.input_tokens,
            output_tokens=r.output_tokens,
            cost_usd=r.cost_usd,
            cached=r.cached,
            latency_ms=r.latency_ms,
        )
        for r in rows
    ]


async def _replay(db: AsyncSession, execution_id: uuid.UUID) -> ExecuteResponse | None:
    execution = await db.get(Execution, execution_id)
    if execution is None or not isinstance(execution.output, dict):
        return None
    out: dict[str, Any] = execution.output
    meta_raw = out.get("metadata")
    metadata = (
        ExecuteMetadata.model_validate({**meta_raw, "idempotent_replay": True})
        if meta_raw
        else None
    )
    verif_raw = out.get("verification")
    verification = VerificationReport.model_validate(verif_raw) if verif_raw else None
    return ExecuteResponse(
        execution_id=execution.id,
        status=execution.status,
        output=str(out.get("text", "")),
        steps=await _steps_response(db, execution.id),
        questions=[],
        metadata=metadata,
        verification=verification,
    )


@router.post("/execute", response_model=ExecuteResponse, summary="Compile and execute a task")
async def execute_task(
    payload: ExecuteRequest,
    user: CurrentUser,
    db: TenantSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ExecuteResponse:
    redis = get_redis()

    # ── Idempotent replay ───────────────────────────────────────────────────────
    if idempotency_key:
        try:
            prior = await redis.get(_idem_key(user.tenant_id, idempotency_key))
        except Exception:  # noqa: BLE001 — idempotency store is best-effort
            prior = None
        if prior is not None:
            replayed = await _replay(db, uuid.UUID(prior.decode()))
            if replayed is not None:
                return replayed

    # ── Resolve the task (from a prompt version or a raw task) ──────────────────
    version_id: uuid.UUID | None = None
    if payload.prompt_version_id is not None:
        version = await db.get(PromptVersion, payload.prompt_version_id)
        if version is None or version.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Prompt version not found")
        if not (version.source_intent or "").strip():
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Prompt version has no source_intent to execute",
            )
        task = version.source_intent or ""
        version_id = version.id
    else:
        task = payload.task or ""

    # ── Compile; stop on ambiguity ──────────────────────────────────────────────
    compiled = await KompiloCore().compile(
        task,
        mode=payload.mode,
        output_format=payload.output_format,
        quality_contract=payload.quality_contract,
        target_model=payload.target_model,
    )
    if compiled.questions or compiled.execution_plan is None or compiled.compiled_prompt is None:
        return ExecuteResponse(
            execution_id=None,
            status="needs_clarification",
            output="",
            steps=[],
            questions=compiled.questions,
            metadata=None,
        )

    # ── Create the execution row, then run the plan ─────────────────────────────
    execution = Execution(
        tenant_id=user.tenant_id,
        created_by=user.id,
        prompt_version_id=version_id,
        status="running",
        input={"task": task, "mode": payload.mode, "output_format": payload.output_format},
        started_at=func.now(),
    )
    db.add(execution)
    await db.flush()
    await db.refresh(execution)

    json_mode = payload.output_format.lower() == "json"
    try:
        outcome = await Executor().run(
            plan=compiled.execution_plan,
            compiled_prompt=compiled.compiled_prompt.text,
            tenant_id=str(user.tenant_id),
            json_mode=json_mode,
        )
    except GatewayError as exc:
        execution.status = "failed"
        execution.error = str(exc)
        execution.finished_at = func.now()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail="Execution failed: all models errored"
        ) from exc

    # ── Journal each step + finalize the execution ──────────────────────────────
    for step in outcome.steps:
        db.add(
            ExecutionStep(
                tenant_id=user.tenant_id,
                execution_id=execution.id,
                step_order=step.order,
                action=step.action,
                input={"prompt": step.input_prompt},
                output=step.output,
                input_tokens=step.input_tokens,
                output_tokens=step.output_tokens,
                cost_usd=step.cost_usd,
                model=step.model,
                cached=step.cached,
                latency_ms=step.latency_ms,
            )
        )

    note = (
        None
        if outcome.provider_is_real
        else "Offline STUB provider — output is not from a real model."
    )
    metadata = ExecuteMetadata(
        provider=outcome.provider,
        provider_is_real=outcome.provider_is_real,
        model=compiled.execution_plan.target_model,
        actual_cost=RealCost(
            input_tokens=outcome.total_input_tokens,
            output_tokens=outcome.total_output_tokens,
            cost_usd=outcome.total_cost_usd,
        ),
        latency_ms=outcome.total_latency_ms,
        cached=outcome.cached_any,
        note=note,
    )
    verification = verify_output(
        outcome.output,
        output_format=payload.output_format,
        output_schema=payload.output_schema,
    )
    execution.status = "succeeded"
    execution.output = {
        "text": outcome.output,
        "metadata": metadata.model_dump(),
        "verification": verification.model_dump(),
    }
    execution.finished_at = func.now()
    await db.flush()

    if idempotency_key:
        try:
            await redis.set(
                _idem_key(user.tenant_id, idempotency_key), str(execution.id), ex=_IDEM_TTL_SECONDS
            )
        except Exception:  # noqa: BLE001 — best-effort
            pass

    return ExecuteResponse(
        execution_id=execution.id,
        status="succeeded",
        output=outcome.output,
        steps=await _steps_response(db, execution.id),
        questions=[],
        metadata=metadata,
        verification=verification,
    )
