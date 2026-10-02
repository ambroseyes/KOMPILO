"""Tenant endpoints + a tenant-scoped endpoint that demonstrates RLS."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession, TenantSession
from app.core.config import settings
from app.models.tenant import PipelineRun, Tenant
from app.schemas.tenant import PipelineRunRead, TenantCreate, TenantRead

router = APIRouter()


@router.get("/tenants", response_model=list[TenantRead], summary="List tenants")
async def list_tenants(db: DbSession) -> list[Tenant]:
    """Control-table read — proves DB connectivity through the app role."""
    result = await db.execute(select(Tenant).order_by(Tenant.created_at))
    return list(result.scalars().all())


@router.post(
    "/tenants",
    response_model=TenantRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a tenant (DEV bootstrap only)",
)
async def create_tenant(payload: TenantCreate, db: DbSession) -> Tenant:
    # DEV-ONLY: real tenant provisioning will be an authenticated admin flow.
    if settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant creation is disabled in production",
        )
    tenant = Tenant(slug=payload.slug, name=payload.name)
    db.add(tenant)
    await db.flush()
    await db.refresh(tenant)
    return tenant


@router.get(
    "/me/pipeline-runs",
    response_model=list[PipelineRunRead],
    summary="List pipeline runs for the current tenant (RLS-enforced)",
)
async def list_my_runs(db: TenantSession) -> list[PipelineRun]:
    """RLS guarantees only the current tenant's rows are visible."""
    result = await db.execute(select(PipelineRun).order_by(PipelineRun.created_at))
    return list(result.scalars().all())
