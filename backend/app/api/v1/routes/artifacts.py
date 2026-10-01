"""Tenant-scoped CRUD for artifacts — RLS-enforced (see skill: kompilo-rls).

Every handler uses ``TenantSession``, so PostgreSQL RLS filters rows to the
current tenant. ``tenant_id`` on writes comes from ``TenantId`` (the authenticated
tenant), never from the client; the policy's WITH CHECK is defense-in-depth.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantId, TenantSession
from app.models.artifact import Artifact
from app.schemas.artifact import ArtifactCreate, ArtifactRead, ArtifactUpdate

router = APIRouter()


async def _get_owned_or_404(db: AsyncSession, artifact_id: uuid.UUID) -> Artifact:
    # RLS makes other tenants' rows invisible, so a miss is a legitimate 404.
    artifact = await db.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    return artifact


@router.post(
    "/artifacts",
    response_model=ArtifactRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an artifact",
)
async def create_artifact(
    payload: ArtifactCreate, tenant_id: TenantId, db: TenantSession
) -> Artifact:
    artifact = Artifact(tenant_id=tenant_id, **payload.model_dump())  # tenant_id from auth
    db.add(artifact)
    await db.flush()
    await db.refresh(artifact)
    return artifact


@router.get("/artifacts", response_model=list[ArtifactRead], summary="List artifacts")
async def list_artifacts(db: TenantSession) -> list[Artifact]:
    result = await db.execute(select(Artifact).order_by(Artifact.created_at))
    return list(result.scalars().all())


@router.get(
    "/artifacts/{artifact_id}", response_model=ArtifactRead, summary="Get an artifact"
)
async def get_artifact(artifact_id: uuid.UUID, db: TenantSession) -> Artifact:
    return await _get_owned_or_404(db, artifact_id)


@router.patch(
    "/artifacts/{artifact_id}", response_model=ArtifactRead, summary="Update an artifact"
)
async def update_artifact(
    artifact_id: uuid.UUID, payload: ArtifactUpdate, db: TenantSession
) -> Artifact:
    artifact = await _get_owned_or_404(db, artifact_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(artifact, field, value)
    await db.flush()
    await db.refresh(artifact)
    return artifact


@router.delete(
    "/artifacts/{artifact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an artifact",
)
async def delete_artifact(artifact_id: uuid.UUID, db: TenantSession) -> Response:
    artifact = await _get_owned_or_404(db, artifact_id)
    await db.delete(artifact)
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
