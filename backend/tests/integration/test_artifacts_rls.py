"""Integration: artifacts are authenticated, role-gated, and tenant-isolated.

Business routes now require a real user (JWT). Members can create/list/get/update;
only org admins can delete. RLS keeps everything scoped to the caller's tenant.
Requires a migrated DB reachable as the app role; skips otherwise. DISPOSABLE DB.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import sqlalchemy as sa

from app.core.tenancy import apply_tenant_guc
from app.db.session import engine, session_scope
from app.main import app
from app.models.organization import Organization


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


async def _delete_org(org_id: uuid.UUID) -> None:
    async with session_scope() as s:
        await apply_tenant_guc(s, org_id)
        await s.execute(sa.delete(Organization).where(Organization.id == org_id))


async def _register_login(client: httpx.AsyncClient, slug: str, email: str) -> str:
    await client.post(
        "/v1/auth/register",
        json={"org_slug": slug, "email": email, "password": "s3cret-pass"},
    )
    resp = await client.post(
        "/v1/auth/login",
        json={"org_slug": slug, "email": email, "password": "s3cret-pass"},
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_artifacts_authz_and_isolation() -> None:
    if not await _db_reachable():
        pytest.skip("No database reachable at DATABASE_URL")

    suffix = uuid.uuid4().hex[:8]
    slug_a, slug_b = f"art-a-{suffix}", f"art-b-{suffix}"
    org_a = await _create_org(slug_a)
    org_b = await _create_org(slug_b)

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            admin = await _register_login(client, slug_a, "admin@a.io")  # first user → admin
            member = await _register_login(client, slug_a, "member@a.io")  # not admin
            other = await _register_login(client, slug_b, "admin@b.io")  # tenant B

            # Unauthenticated → 401.
            assert (await client.get("/v1/artifacts")).status_code == 401

            # A member can create and list.
            created = await client.post(
                "/v1/artifacts", headers=_bearer(member), json={"name": "x"}
            )
            assert created.status_code == 201, created.text
            art_id = created.json()["id"]
            assert created.json()["tenant_id"] == str(org_a)

            listed = await client.get("/v1/artifacts", headers=_bearer(member))
            assert [a["id"] for a in listed.json()] == [art_id]

            # Tenant B sees none of A's artifacts (token-scoped isolation).
            assert (await client.get("/v1/artifacts", headers=_bearer(other))).json() == []

            # Delete is org-admin only: member → 403, admin → 204.
            assert (
                await client.delete(f"/v1/artifacts/{art_id}", headers=_bearer(member))
            ).status_code == 403
            assert (
                await client.delete(f"/v1/artifacts/{art_id}", headers=_bearer(admin))
            ).status_code == 204

            # Admin-only members listing: admin sees both A users, member → 403.
            members = await client.get("/v1/organizations/members", headers=_bearer(admin))
            assert members.status_code == 200
            assert {m["email"] for m in members.json()} == {"admin@a.io", "member@a.io"}
            assert (
                await client.get("/v1/organizations/members", headers=_bearer(member))
            ).status_code == 403
    finally:
        await _delete_org(org_a)
        await _delete_org(org_b)
