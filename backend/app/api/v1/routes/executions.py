"""Executions — async pipeline runs over a prompt version (authenticated + RLS).

``POST /executions`` creates a ``pending`` execution and enqueues the ``understand``
job; the worker (``app.workers``) runs it and updates the row. Poll it via
``GET /executions/{id}``. ``tenant_id`` / ``created_by`` are server-set; RLS scopes
everything to the caller's tenant. See the ``kompilo-crud`` / ``kompilo-rls`` skills.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, TenantSession, get_current_user
from app.core.queue import enqueue_pipeline
from app.models.execution import Execution
from app.models.prompt import PromptVersion
from app.schemas.execution import ExecutionCreate, ExecutionRead
from app.services.budget import check_budget

router = APIRouter(dependencies=[Depends(get_current_user)])


async def _get_active_version(db: AsyncSession, version_id: uuid.UUID) -> PromptVersion:
    stmt = select(PromptVersion).where(
        PromptVersion.id == version_id, PromptVersion.deleted_at.is_(None)
    )
    version = (await db.execute(stmt)).scalars().first()
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prompt version not found"
        )
    return version


@router.post(
    "/executions",
    response_model=ExecutionRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run the full pipeline over a prompt version (async)",
)
async def create_execution(
    payload: ExecutionCreate,
    user: CurrentUser,
    db: TenantSession,
    background: BackgroundTasks,
) -> Execution:
    # Budget gate BEFORE enqueuing: an over-budget tenant gets an immediate 402,
    # no pending row, no worker job. Never degrades the run — only allows or refuses.
    await check_budget(db, user.tenant_id)

    version = await _get_active_version(db, payload.prompt_version_id)
    if not (version.source_intent or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Prompt version has no source_intent to understand",
        )

    execution = Execution(
        tenant_id=user.tenant_id,
        created_by=user.id,
        prompt_version_id=version.id,
        status="pending",
        input={"stage": "pipeline", "context": payload.context},
    )
    db.add(execution)
    await db.flush()
    await db.refresh(execution)

    # Enqueue AFTER the response commits (BackgroundTasks run post-response), so the
    # worker never races the row's creation. tenant_id is pinned in the worker's GUC.
    background.add_task(enqueue_pipeline, execution.id, user.tenant_id)
    return execution


@router.get("/executions", response_model=list[ExecutionRead], summary="List executions")
async def list_executions(db: TenantSession) -> list[Execution]:
    stmt = (
        select(Execution)
        .where(Execution.deleted_at.is_(None))
        .order_by(Execution.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


@router.get(
    "/executions/{execution_id}",
    response_model=ExecutionRead,
    summary="Get an execution (poll its status/output)",
)
async def get_execution(execution_id: uuid.UUID, db: TenantSession) -> Execution:
    stmt = select(Execution).where(Execution.id == execution_id, Execution.deleted_at.is_(None))
    execution = (await db.execute(stmt)).scalars().first()
    if execution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    return execution
