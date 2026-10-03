"""Background tasks executed by ARQ workers."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func

from app.core.errors import KompiloError
from app.core.tenancy import apply_tenant_guc
from app.db.session import session_scope
from app.engines.orchestrator import KompiloPipeline
from app.engines.retriever import Retriever
from app.models.execution import Execution
from app.models.prompt import PromptVersion
from app.services.execution_store import persist_success
from app.telemetry.logging import get_logger

logger = get_logger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    logger.info("ARQ worker starting up")


async def shutdown(ctx: dict[str, Any]) -> None:
    logger.info("ARQ worker shutting down")


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
        logger.exception("pipeline: could not record failure for execution %s", execution_id)


async def run_pipeline_task(
    ctx: dict[str, Any],
    execution_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """Run the FULL Kompilo pipeline for a pending execution, off the request path.

    Tenant-scoped (the GUC is pinned from the trusted API-supplied ``tenant_id`` so RLS
    confines every read/write). Reads the prompt version's ``source_intent``, runs the
    single ``KompiloPipeline`` (understand → … → execute → verify → evaluate → improve),
    and persists the result the same way ``/v1/execute`` does. An ambiguous task is a valid
    outcome (succeeded, with clarifying questions). A missing/invisible execution is a
    no-op.
    """
    exec_uuid = uuid.UUID(execution_id)
    tid = uuid.UUID(tenant_id)
    try:
        async with session_scope() as s:
            await apply_tenant_guc(s, tid)
            execution = await s.get(Execution, exec_uuid)
            if execution is None:
                logger.warning(
                    "pipeline: execution %s not visible to tenant %s", execution_id, tenant_id
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
                execution.error = "prompt version has no source_intent to run"
                execution.started_at = func.now()
                execution.finished_at = func.now()
                return {"status": "failed", "execution_id": execution_id}

            execution.started_at = func.now()
            result = await KompiloPipeline(retriever=Retriever(s)).run(
                task=intent, tenant_id=tenant_id
            )
            version.catr = result.catr.model_dump(mode="json")

            if result.status == "needs_clarification":
                execution.status = "succeeded"
                execution.output = {
                    "status": "needs_clarification",
                    "questions": result.questions,
                    "trace": result.trace,
                    "catr": result.catr.model_dump(mode="json"),
                }
                execution.finished_at = func.now()
            else:
                await persist_success(s, execution, result)

        logger.info("pipeline: execution %s succeeded", execution_id)
        return {"status": "succeeded", "execution_id": execution_id}
    except KompiloError as exc:
        logger.warning("pipeline: execution %s failed (%s)", execution_id, exc.category)
        await _record_failure(exec_uuid, tid, f"{exc.category}: {exc.detail}")
        return {"status": "failed", "execution_id": execution_id, "error": str(exc.category)}
    except Exception as exc:  # noqa: BLE001 — isolate + persist the failure
        logger.exception("pipeline: execution %s failed", execution_id)
        await _record_failure(exec_uuid, tid, f"{type(exc).__name__}: {exc}")
        return {"status": "failed", "execution_id": execution_id, "error": str(exc)}
