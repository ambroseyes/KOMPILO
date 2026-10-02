"""Tenant-scoped CRUD for prompts and their IMMUTABLE versions.

Every route requires an authenticated member (router-level ``get_current_user``),
so PostgreSQL RLS filters rows to the caller's tenant. ``tenant_id`` is derived
from the authenticated user and the parent (``project_id``/``prompt_id``) comes
from the URL path — never from the client body. Deleting a prompt is an org-admin
soft-delete. See the ``kompilo-rls`` skill.

Immutability
------------
Prompt versions are append-only. There is no update or delete route for a version:
the ``content`` and ``version`` of a created version never change. A new revision
is a new version row whose number is server-assigned and monotonic per prompt
(``1, 2, 3, ...``). The ``(tenant_id, prompt_id, version)`` unique constraint is
the backstop against a racing duplicate.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, OrgAdmin, TenantSession, get_current_user
from app.models.project import Project
from app.models.prompt import Prompt, PromptVersion
from app.schemas.prompt import (
    PromptCreate,
    PromptRead,
    PromptUpdate,
    PromptVersionCreate,
    PromptVersionRead,
)

router = APIRouter(dependencies=[Depends(get_current_user)])


async def _live_project_or_404(db: AsyncSession, project_id: uuid.UUID) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    )
    project = result.scalars().first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def _live_prompt_or_404(db: AsyncSession, prompt_id: uuid.UUID) -> Prompt:
    result = await db.execute(
        select(Prompt).where(Prompt.id == prompt_id, Prompt.deleted_at.is_(None))
    )
    prompt = result.scalars().first()
    if prompt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found")
    return prompt


# ── Prompts ───────────────────────────────────────────────────────────────────
@router.post(
    "/projects/{project_id}/prompts",
    response_model=PromptRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a prompt in a project",
)
async def create_prompt(
    project_id: uuid.UUID, payload: PromptCreate, user: CurrentUser, db: TenantSession
) -> Prompt:
    await _live_project_or_404(db, project_id)  # 404 if not visible to this tenant
    prompt = Prompt(
        tenant_id=user.tenant_id,
        project_id=project_id,
        created_by=user.id,
        **payload.model_dump(),
    )
    db.add(prompt)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A prompt with this slug already exists in this project",
        ) from exc
    await db.refresh(prompt)
    return prompt


@router.get(
    "/projects/{project_id}/prompts",
    response_model=list[PromptRead],
    summary="List prompts in a project",
)
async def list_prompts(project_id: uuid.UUID, db: TenantSession) -> list[Prompt]:
    await _live_project_or_404(db, project_id)
    result = await db.execute(
        select(Prompt)
        .where(Prompt.project_id == project_id, Prompt.deleted_at.is_(None))
        .order_by(Prompt.created_at)
    )
    return list(result.scalars().all())


@router.get("/prompts/{prompt_id}", response_model=PromptRead, summary="Get a prompt")
async def get_prompt(prompt_id: uuid.UUID, db: TenantSession) -> Prompt:
    return await _live_prompt_or_404(db, prompt_id)


@router.patch("/prompts/{prompt_id}", response_model=PromptRead, summary="Update a prompt")
async def update_prompt(prompt_id: uuid.UUID, payload: PromptUpdate, db: TenantSession) -> Prompt:
    prompt = await _live_prompt_or_404(db, prompt_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(prompt, field, value)
    await db.flush()
    await db.refresh(prompt)
    return prompt


@router.delete(
    "/prompts/{prompt_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a prompt (org admin only, soft delete)",
)
async def delete_prompt(prompt_id: uuid.UUID, admin: OrgAdmin, db: TenantSession) -> Response:
    prompt = await _live_prompt_or_404(db, prompt_id)
    prompt.deleted_at = datetime.now(UTC)
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Prompt versions (immutable, append-only) ──────────────────────────────────
@router.post(
    "/prompts/{prompt_id}/versions",
    response_model=PromptVersionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new immutable version of a prompt",
)
async def create_prompt_version(
    prompt_id: uuid.UUID, payload: PromptVersionCreate, user: CurrentUser, db: TenantSession
) -> PromptVersion:
    await _live_prompt_or_404(db, prompt_id)
    # Next monotonic version for this prompt (RLS scopes the MAX to this tenant).
    current_max = (
        await db.execute(
            select(func.max(PromptVersion.version)).where(PromptVersion.prompt_id == prompt_id)
        )
    ).scalar_one_or_none()
    next_version = (current_max or 0) + 1

    version = PromptVersion(
        tenant_id=user.tenant_id,
        prompt_id=prompt_id,
        version=next_version,
        content=payload.content,
        model_target=payload.model_target,
        author_id=user.id,
    )
    db.add(version)
    try:
        await db.flush()
    except IntegrityError as exc:
        # A concurrent create took this version number; the unique constraint held.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Version conflict, please retry",
        ) from exc
    await db.refresh(version)
    return version


@router.get(
    "/prompts/{prompt_id}/versions",
    response_model=list[PromptVersionRead],
    summary="List a prompt's versions (newest first)",
)
async def list_prompt_versions(prompt_id: uuid.UUID, db: TenantSession) -> list[PromptVersion]:
    await _live_prompt_or_404(db, prompt_id)
    result = await db.execute(
        select(PromptVersion)
        .where(PromptVersion.prompt_id == prompt_id, PromptVersion.deleted_at.is_(None))
        .order_by(PromptVersion.version.desc())
    )
    return list(result.scalars().all())


@router.get(
    "/prompts/{prompt_id}/versions/{version}",
    response_model=PromptVersionRead,
    summary="Get a specific version of a prompt",
)
async def get_prompt_version(
    prompt_id: uuid.UUID, version: int, db: TenantSession
) -> PromptVersion:
    await _live_prompt_or_404(db, prompt_id)
    result = await db.execute(
        select(PromptVersion).where(
            PromptVersion.prompt_id == prompt_id,
            PromptVersion.version == version,
            PromptVersion.deleted_at.is_(None),
        )
    )
    prompt_version = result.scalars().first()
    if prompt_version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prompt version not found"
        )
    return prompt_version
