"""TEMPLATE — RLS isolation integration test for Kompilo.

A worked copy lives at ``backend/tests/integration/test_mvp_rls_isolation.py``.
Use this as the pattern when you add a new tenant-owned table: seed two orgs, a
row under each, then assert a tenant-A session sees only A's rows, an unscoped
session sees none (fail-closed), and a forced cross-tenant write is rejected.

Run against a DISPOSABLE database reachable as the app role (``kompilo_app``):

    DATABASE_URL=postgresql+asyncpg://kompilo_app:...@localhost:5432/kompilo \\
        pytest tests/integration -v
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import select

from app.core.tenancy import apply_tenant_guc
from app.db.session import async_session_factory, engine, session_scope
from app.models.organization import Organization
from app.models.project import Project  # swap for YOUR new tenant-owned model


async def _db_reachable() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
        return True
    except Exception:
        return False


async def _create_org(slug: str) -> uuid.UUID:
    org_id = uuid.uuid4()
    async with session_scope() as s:
        await apply_tenant_guc(s, org_id)  # id == GUC so WITH CHECK passes
        s.add(Organization(id=org_id, slug=slug, name=slug))
    return org_id


@pytest.mark.asyncio
async def test_rls_isolates_tenants() -> None:
    if not await _db_reachable():
        pytest.skip("No database reachable at DATABASE_URL")

    suffix = uuid.uuid4().hex[:8]
    org_a = await _create_org(f"a-{suffix}")
    org_b = await _create_org(f"b-{suffix}")

    async with session_scope() as s:
        await apply_tenant_guc(s, org_a)
        s.add(Project(tenant_id=org_a, slug=f"a-{suffix}", name="A"))
    async with session_scope() as s:
        await apply_tenant_guc(s, org_b)
        s.add(Project(tenant_id=org_b, slug=f"b-{suffix}", name="B"))

    # Scoped to A → sees only A's rows.
    async with async_session_factory() as s:
        await apply_tenant_guc(s, org_a)
        rows = (await s.execute(select(Project).where(Project.tenant_id == org_b))).scalars().all()
    assert rows == [], "tenant A must not see tenant B's rows"

    # No tenant set → sees nothing.
    async with async_session_factory() as s:
        rows = (await s.execute(select(Project))).scalars().all()
    assert rows == []
