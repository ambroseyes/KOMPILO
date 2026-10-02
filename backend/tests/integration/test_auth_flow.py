"""Integration: register → login (JWT) → /me → token-derived tenant isolation.

Proves the full chain: a JWT's ``tid`` drives the tenant GUC, and RLS then isolates
data per token. Requires a migrated DB reachable as the app role; skips otherwise.
Use a DISPOSABLE database.
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


@pytest.mark.asyncio
async def test_register_login_me_and_token_scoped_isolation() -> None:
    if not await _db_reachable():
        pytest.skip("No database reachable at DATABASE_URL")

    suffix = uuid.uuid4().hex[:8]
    slug_a, slug_b = f"auth-a-{suffix}", f"auth-b-{suffix}"
    org_a = await _create_org(slug_a)
    org_b = await _create_org(slug_b)

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Register + log in user A.
            reg = await client.post(
                "/v1/auth/register",
                json={"org_slug": slug_a, "email": "Alice@Example.com", "password": "s3cret-pass"},
            )
            assert reg.status_code == 201, reg.text
            assert reg.json()["email"] == "alice@example.com"  # normalized
            assert reg.json()["tenant_id"] == str(org_a)

            login = await client.post(
                "/v1/auth/login",
                json={"org_slug": slug_a, "email": "alice@example.com", "password": "s3cret-pass"},
            )
            assert login.status_code == 200, login.text
            token_a = login.json()["access_token"]
            auth_a = {"Authorization": f"Bearer {token_a}"}

            # /me returns the user, tenant derived from the token.
            me = await client.get("/v1/auth/me", headers=auth_a)
            assert me.status_code == 200
            assert me.json()["tenant_id"] == str(org_a)

            # Token-derived tenant: create an artifact with NO X-Tenant-ID header.
            art = await client.post("/v1/artifacts", headers=auth_a, json={"name": "from-token"})
            assert art.status_code == 201, art.text
            assert art.json()["tenant_id"] == str(org_a)

            # Register + log in user B; B's token must not see A's artifact.
            await client.post(
                "/v1/auth/register",
                json={"org_slug": slug_b, "email": "bob@example.com", "password": "s3cret-pass"},
            )
            login_b = await client.post(
                "/v1/auth/login",
                json={"org_slug": slug_b, "email": "bob@example.com", "password": "s3cret-pass"},
            )
            token_b = login_b.json()["access_token"]
            list_b = await client.get(
                "/v1/artifacts", headers={"Authorization": f"Bearer {token_b}"}
            )
            assert list_b.status_code == 200
            assert list_b.json() == []  # B sees none of A's rows

            # Wrong password and unknown org → 401.
            bad_pw = await client.post(
                "/v1/auth/login",
                json={"org_slug": slug_a, "email": "alice@example.com", "password": "wrong"},
            )
            assert bad_pw.status_code == 401
            bad_org = await client.post(
                "/v1/auth/login",
                json={
                    "org_slug": "nope-" + suffix,
                    "email": "x@example.com",
                    "password": "whatever",
                },
            )
            assert bad_org.status_code == 401
    finally:
        await _delete_org(org_a)
        await _delete_org(org_b)
