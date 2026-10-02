"""Tenant-scoped CRUD for projects — authenticated + RLS-enforced.

Every route requires an authenticated member (router-level ``get_current_user``),
so PostgreSQL RLS filters rows to the caller's tenant. Writes derive ``tenant_id``
from the authenticated user, never from the client. Deletion is an org-admin
soft-delete (``deleted_at``). See the ``kompilo-rls`` skill.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, OrgAdmin, TenantSession, get_current_user
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

# Router-level dependency: all project routes require an authenticated member.
router = APIRouter(dependencies=[Depends(get_current_user)])


async def _get_live_or_404(db: AsyncSession, project_id: uuid.UUID) -> Project:
    # RLS makes other tenants' rows invisible, so a miss is a legitimate 404.
    # Soft-deleted rows are treated as gone.
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    )
    project = result.scalars().first()
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
    # tenant_id comes from the authenticated user, never from the client.
    project = Project(tenant_id=user.tenant_id, created_by=user.id, **payload.model_dump())
    db.add(project)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A project with this slug already exists",
        ) from exc
    await db.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectRead], summary="List projects")
async def list_projects(db: TenantSession) -> list[Project]:
    result = await db.execute(
        select(Project).where(Project.deleted_at.is_(None)).order_by(Project.created_at)
    )
    return list(result.scalars().all())


@router.get("/projects/{project_id}", response_model=ProjectRead, summary="Get a project")
async def get_project(project_id: uuid.UUID, db: TenantSession) -> Project:
    return await _get_live_or_404(db, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectRead, summary="Update a project")
async def update_project(
    project_id: uuid.UUID, payload: ProjectUpdate, db: TenantSession
) -> Project:
    project = await _get_live_or_404(db, project_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await db.flush()
    await db.refresh(project)
    return project


@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project (org admin only, soft delete)",
)
async def delete_project(project_id: uuid.UUID, admin: OrgAdmin, db: TenantSession) -> Response:
    project = await _get_live_or_404(db, project_id)
    project.deleted_at = datetime.now(UTC)
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
