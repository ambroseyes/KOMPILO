"""Compile endpoint: turn an intent into an execution strategy.

The ``understand`` stage is real (it calls an LLM with tenant data), so the
endpoint is authenticated: every request requires a member (``get_current_user``),
which also pins the tenant for RLS. The remaining stages are still STUB — each
trace entry carries its own ``is_stub`` flag, and the top-level ``is_stub`` is
true while any stage is a placeholder.

Every run is persisted as an ``Execution`` row (tenant-scoped, RLS-isolated).
``prompt_version_id`` is NULL here: ``/compile`` runs on an ad-hoc intent, not a
stored prompt version. The tenant is taken from the authenticated user, never the
client — RLS's ``WITH CHECK`` is the backstop, not the gate.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.deps import CurrentUser, TenantId, TenantSession
from app.engines.pipeline import pipeline
from app.models.execution import Execution
from app.schemas.compile import CompileRequest, CompileResponse, StageTrace

router = APIRouter()


@router.post("/compile", response_model=CompileResponse, summary="Compile an intent")
async def compile_intent(
    payload: CompileRequest,
    user: CurrentUser,
    tenant_id: TenantId,
    db: TenantSession,
) -> CompileResponse:
    """Run the Kompilo pipeline and persist the run as an ``Execution``.

    ``understand`` is real; later stages are STUB. ``is_stub`` reflects whether any
    stage in the trace is still a placeholder.
    """
    execution = Execution(
        tenant_id=tenant_id,  # from auth, NEVER the client (RLS backstop)
        prompt_version_id=None,  # ad-hoc intent, not a stored version
        status="running",
        input={"intent": payload.intent, "context": payload.context},
        created_by=user.id,
        started_at=datetime.now(UTC),
    )
    db.add(execution)
    await db.flush()  # assign the id inside the tenant-scoped transaction

    try:
        ctx = await pipeline.run(payload.intent, payload.context)
    except Exception as exc:  # noqa: BLE001 — record the failure, then surface it
        execution.status = "failed"
        execution.error = str(exc)
        execution.finished_at = datetime.now(UTC)
        await db.flush()
        await db.commit()  # persist the failed run before propagating
        raise

    trace = [
        StageTrace(stage=r.stage, status=r.status, note=r.note, is_stub=r.is_stub)
        for r in ctx.trace
    ]
    failed = any(t.status == "error" for t in trace)
    execution.status = "failed" if failed else "succeeded"
    if failed:
        execution.error = next((t.note for t in trace if t.status == "error"), None)
    execution.output = {
        "strategy": ctx.artifacts,
        "trace": [t.model_dump() for t in trace],
    }
    execution.finished_at = datetime.now(UTC)
    await db.flush()

    return CompileResponse(
        execution_id=execution.id,
        intent=ctx.intent,
        strategy=ctx.artifacts,
        trace=trace,
        is_stub=any(t.is_stub for t in trace),
    )
