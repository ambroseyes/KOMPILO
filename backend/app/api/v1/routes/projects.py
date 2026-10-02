"""Tenant-scoped CRUD for projects — authenticated, RLS-enforced, soft-deletable.

Every route requires an authenticated member (router-level ``get_current_user``),
so PostgreSQL RLS scopes rows to the caller's tenant. Writes derive ``tenant_id``
and ``created_by`` from the authenticated user, never the client. Deletion is a
SOFT delete (sets ``deleted_at``), restricted to org admins, and cascades to the
project's prompts and their versions. See the ``kompilo-rls`` / ``kompilo-crud``
skills.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, OrgAdmin, TenantSession, get_current_user
from app.models.project import Project
from app.models.prompt import Prompt, PromptVersion
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

# Router-level dependency: all project routes require an authenticated member.
router = APIRouter(dependencies=[Depends(get_current_user)])


async def _get_active_project(db: AsyncSession, project_id: uuid.UUID) -> Project:
    """Fetch a live (not soft-deleted) project in the caller's tenant, or 404.

    RLS makes other tenants' rows invisible, so a miss is a legitimate 404 rather
    than a 403 (we never reveal that a foreign row exists).
    """
    stmt = select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    project = (await db.execute(stmt)).scalars().first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post(
    "/projects",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project",
)
async def create_project(payload: ProjectCreate, user: CurrentUser, db: TenantSession) -> Project:
    # tenant_id and created_by come from the authenticated user, never the client.
    project = Project(
        tenant_id=user.tenant_id,
        created_by=user.id,
        slug=payload.slug,
        name=payload.name,
        description=payload.description,
    )
    db.add(project)
    try:
        await db.flush()
    except IntegrityError as exc:
        # Partial unique index on (tenant_id, slug) WHERE deleted_at IS NULL.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A project with slug '{payload.slug}' already exists",
        ) from exc
    await db.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectRead], summary="List projects")
async def list_projects(db: TenantSession) -> list[Project]:
    stmt = select(Project).where(Project.deleted_at.is_(None)).order_by(Project.created_at)
    return list((await db.execute(stmt)).scalars().all())


@router.get("/projects/{project_id}", response_model=ProjectRead, summary="Get a project")
async def get_project(project_id: uuid.UUID, db: TenantSession) -> Project:
    return await _get_active_project(db, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectRead, summary="Update a project")
async def update_project(
    project_id: uuid.UUID, payload: ProjectUpdate, db: TenantSession
) -> Project:
    project = await _get_active_project(db, project_id)
    # slug is immutable (not in ProjectUpdate), so no uniqueness conflict here.
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await db.flush()
    await db.refresh(project)
    return project


@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a project and its prompts/versions (org admin only)",
)
async def delete_project(project_id: uuid.UUID, admin: OrgAdmin, db: TenantSession) -> Response:
    project = await _get_active_project(db, project_id)
    # now() is transaction-stable in Postgres, so all cascaded rows share a timestamp.
    deleted_at = func.now()
    # Cascade: soft-delete this project's prompt versions, then its prompts.
    # RLS scopes every statement to the admin's tenant.
    await db.execute(
        update(PromptVersion)
        .where(
            PromptVersion.deleted_at.is_(None),
            PromptVersion.prompt_id.in_(select(Prompt.id).where(Prompt.project_id == project_id)),
        )
        .values(deleted_at=deleted_at)
    )
    await db.execute(
        update(Prompt)
        .where(Prompt.project_id == project_id, Prompt.deleted_at.is_(None))
        .values(deleted_at=deleted_at)
    )
    project.deleted_at = deleted_at
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
