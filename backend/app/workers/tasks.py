"""Background tasks executed by ARQ workers."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func

from app.core.tenancy import apply_tenant_guc
from app.db.session import session_scope
from app.engines.intent import IntentEngine
from app.engines.pipeline import pipeline
from app.models.execution import Execution
from app.models.prompt import PromptVersion
from app.telemetry.logging import get_logger

logger = get_logger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    logger.info("ARQ worker starting up")


async def shutdown(ctx: dict[str, Any]) -> None:
    logger.info("ARQ worker shutting down")


async def compile_intent_task(
    ctx: dict[str, Any],
    intent: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the full compile pipeline off the request path (understand is real; the
    later stages are still STUB)."""
    result = await pipeline.run(intent, context or {})
    return {
        "intent": result.intent,
        "artifacts": result.artifacts,
        "trace": [{"stage": r.stage, "status": r.status} for r in result.trace],
    }


async def _record_failure(execution_id: uuid.UUID, tenant_id: uuid.UUID, error: str) -> None:
    """Mark an execution failed in its own transaction (after a rollback)."""
    try:
        async with session_scope() as s:
            await apply_tenant_guc(s, tenant_id)
            execution = await s.get(Execution, execution_id)
            if execution is not None:
                execution.status = "failed"
                execution.error = error
                execution.finished_at = func.now()
    except Exception:  # noqa: BLE001 — best-effort failure recording
        logger.exception("understand: could not record failure for execution %s", execution_id)


async def run_understand_task(
    ctx: dict[str, Any],
    execution_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """Run the `understand` stage for a pending execution.

    Tenant-scoped: the GUC is pinned from the (trusted, API-supplied) ``tenant_id``
    so RLS confines every read/write to that tenant. Reads the prompt version's
    ``source_intent``, analyzes it into a CATR, and writes the result onto both the
    execution (``output``) and the prompt version (``catr``). Idempotent-ish: a
    missing/invisible execution is a no-op.
    """
    exec_uuid = uuid.UUID(execution_id)
    tid = uuid.UUID(tenant_id)
    try:
        async with session_scope() as s:
            await apply_tenant_guc(s, tid)
            execution = await s.get(Execution, exec_uuid)
            if execution is None:
                logger.warning(
                    "understand: execution %s not visible to tenant %s", execution_id, tenant_id
                )
                return {"status": "missing", "execution_id": execution_id}

            version = await s.get(PromptVersion, execution.prompt_version_id)
            if version is None or version.deleted_at is not None:
                execution.status = "failed"
                execution.error = "prompt version not found"
                execution.started_at = func.now()
                execution.finished_at = func.now()
                return {"status": "failed", "execution_id": execution_id}

            intent = (version.source_intent or "").strip()
            if not intent:
                execution.status = "failed"
                execution.error = "prompt version has no source_intent to understand"
                execution.started_at = func.now()
                execution.finished_at = func.now()
                return {"status": "failed", "execution_id": execution_id}

            catr = await IntentEngine().run(intent)
            payload = catr.model_dump()

            execution.started_at = func.now()
            execution.output = {"stage": "understand", "catr": payload}
            execution.status = "succeeded"
            execution.finished_at = func.now()
            version.catr = payload

        logger.info("understand: execution %s succeeded", execution_id)
        return {"status": "succeeded", "execution_id": execution_id}
    except Exception as exc:  # noqa: BLE001 — isolate + persist the failure
        logger.exception("understand: execution %s failed", execution_id)
        await _record_failure(exec_uuid, tid, f"{type(exc).__name__}: {exc}")
        return {"status": "failed", "execution_id": execution_id, "error": str(exc)}
