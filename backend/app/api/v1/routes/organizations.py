"""Organization endpoints (tenant root).

``organizations`` is RLS-restricted to the current tenant (``id = app.tenant_id``),
so a tenant-scoped session sees only its own org. ``POST`` is a DEV-only bootstrap
to obtain an org/tenant id for the dev ``X-Tenant-ID`` flow before real
provisioning exists; it pins the GUC to the new id so the RLS WITH CHECK passes.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession, TenantSession
from app.core.config import settings
from app.core.tenancy import apply_tenant_guc
from app.models.organization import Organization
from app.schemas.organization import OrganizationCreate, OrganizationRead

router = APIRouter()


@router.post(
    "/organizations",
    response_model=OrganizationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an organization (DEV bootstrap only)",
)
async def create_organization(payload: OrganizationCreate, db: DbSession) -> Organization:
    if settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization creation is disabled in production",
        )
    org = Organization(id=uuid.uuid4(), slug=payload.slug, name=payload.name)
    # RLS on organizations is `id = app.tenant_id`; pin the GUC to the new id so
    # the INSERT's WITH CHECK passes and the row is readable back.
    await apply_tenant_guc(db, org.id)
    db.add(org)
    await db.flush()
    await db.refresh(org)
    return org


@router.get(
    "/organizations/me",
    response_model=OrganizationRead,
    summary="Get the current tenant's organization (RLS-enforced)",
)
async def get_my_organization(db: TenantSession) -> Organization:
    org = (await db.execute(select(Organization))).scalars().first()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org
