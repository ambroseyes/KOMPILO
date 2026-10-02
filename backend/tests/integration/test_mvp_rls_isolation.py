"""Integration: MVP RLS isolation, exercised AS THE APPLICATION ROLE.

The core guarantee: a query run in tenant A's context never returns tenant B's
rows. Also checks fail-closed (no tenant → zero rows) and that WITH CHECK rejects
a forced cross-tenant write.

Requires a migrated database reachable as the app role (``kompilo_app``) via
DATABASE_URL; skips when none is reachable. Use a DISPOSABLE database.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.core.tenancy import apply_tenant_guc
from app.db.session import async_session_factory, engine, session_scope
from app.models.organization import Organization
from app.models.project import Project


async def _db_reachable() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
        return True
    except Exception:
        return False


async def _create_org(slug: str, name: str) -> uuid.UUID:
    org_id = uuid.uuid4()
    async with session_scope() as s:
        await apply_tenant_guc(s, org_id)  # id == GUC so the WITH CHECK passes
        s.add(Organization(id=org_id, slug=slug, name=name))
    return org_id


async def _create_project(tenant_id: uuid.UUID, slug: str) -> uuid.UUID:
    project_id = uuid.uuid4()
    async with session_scope() as s:
        await apply_tenant_guc(s, tenant_id)
        s.add(Project(id=project_id, tenant_id=tenant_id, slug=slug, name=slug))
    return project_id


async def _delete_org(org_id: uuid.UUID) -> None:
    async with session_scope() as s:
        await apply_tenant_guc(s, org_id)
        await s.execute(sa.delete(Organization).where(Organization.id == org_id))


@pytest.mark.asyncio
async def test_tenant_a_cannot_see_tenant_b_rows() -> None:
    if not await _db_reachable():
        pytest.skip("No database reachable at DATABASE_URL")

    suffix = uuid.uuid4().hex[:8]
    org_a = await _create_org(f"a-{suffix}", "Org A")
    org_b = await _create_org(f"b-{suffix}", "Org B")

    try:
        proj_a = await _create_project(org_a, f"proj-a-{suffix}")
        proj_b = await _create_project(org_b, f"proj-b-{suffix}")

        # In tenant A's context: see only A's project; B's rows are invisible.
        async with async_session_factory() as s:
            await apply_tenant_guc(s, org_a)
            visible = (await s.execute(select(Project.id))).scalars().all()
            assert set(visible) == {proj_a}

            # The explicit cross-tenant query for B's data returns ZERO rows.
            by_b = (await s.execute(select(Project).where(Project.id == proj_b))).scalars().all()
            assert by_b == []

        # No tenant set → zero rows (fail-closed).
        async with async_session_factory() as s:
            none_visible = (await s.execute(select(Project.id))).scalars().all()
            assert none_visible == []

        # A cannot write a row tagged for B (WITH CHECK rejects it).
        with pytest.raises(DBAPIError):
            async with async_session_factory() as s:
                await apply_tenant_guc(s, org_a)
                s.add(Project(tenant_id=org_b, slug=f"x-{suffix}", name="x"))
                await s.commit()
    finally:
        await _delete_org(org_a)
        await _delete_org(org_b)
