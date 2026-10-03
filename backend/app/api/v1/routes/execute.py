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
from app.core.errors import KompiloError
from app.core.redis import get_redis
from app.engines.orchestrator import KompiloPipeline
from app.models.execution import Execution
from app.models.execution_step import ExecutionStep
from app.models.prompt import PromptVersion
from app.schemas.evaluate import EvaluationReport
from app.schemas.execute import (
    ExecuteMetadata,
    ExecuteRequest,
    ExecuteResponse,
    ExecuteStepResult,
)
from app.schemas.improve import ImprovementReport
from app.schemas.verify import VerificationReport
from app.services.execution_store import persist_success

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
            repaired=bool(r.input.get("repaired")) if isinstance(r.input, dict) else False,
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
    eval_raw = out.get("evaluation")
    evaluation = EvaluationReport.model_validate(eval_raw) if eval_raw else None
    impr_raw = out.get("improvements")
    improvements = ImprovementReport.model_validate(impr_raw) if impr_raw else None
    trace_raw = out.get("trace")
    trace = trace_raw if isinstance(trace_raw, list) else []
    return ExecuteResponse(
        execution_id=execution.id,
        status=execution.status,
        output=str(out.get("text", "")),
        steps=await _steps_response(db, execution.id),
        questions=[],
        metadata=metadata,
        verification=verification,
        evaluation=evaluation,
        improvements=improvements,
        trace=trace,
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

    exec_input = {"task": task, "mode": payload.mode, "output_format": payload.output_format}

    # ── Run the SINGLE pipeline: understand → … → execute → verify → evaluate → improve.
    try:
        result = await KompiloPipeline().run(
            task=task,
            tenant_id=str(user.tenant_id),
            mode=payload.mode,
            output_format=payload.output_format,
            target_model=payload.target_model,
            quality_contract=payload.quality_contract,
            output_schema=payload.output_schema,
        )
    except KompiloError as exc:
        # Classified failure (model / timeout / rate-limit / policy / …): persist a failed
        # execution, return the USER-friendly message + category (no internals/secrets).
        execution = Execution(
            tenant_id=user.tenant_id,
            created_by=user.id,
            prompt_version_id=version_id,
            status="failed",
            input=exec_input,
            error=f"{exc.category}: {exc.detail}",
            started_at=func.now(),
            finished_at=func.now(),
        )
        db.add(execution)
        await db.flush()
        status_code, body = exc.to_http()
        raise HTTPException(status_code, detail=body) from exc

    # ── ASK: clarification needed — no execution row, return the questions. ─────────
    if result.status == "needs_clarification":
        return ExecuteResponse(
            execution_id=None,
            status="needs_clarification",
            output="",
            steps=[],
            questions=result.questions,
            metadata=None,
            trace=result.trace,
        )

    outcome = result.outcome
    assert outcome is not None  # PROCEED

    # ── Persist the execution via the SHARED store (journal + metadata + output). ────
    execution = Execution(
        tenant_id=user.tenant_id,
        created_by=user.id,
        prompt_version_id=version_id,
        status="running",
        input=exec_input,
        started_at=func.now(),
    )
    db.add(execution)
    await db.flush()
    await db.refresh(execution)

    metadata = await persist_success(db, execution, result)
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
        verification=result.verification,
        evaluation=result.evaluation,
        improvements=result.improvements,
        trace=result.trace,
    )
