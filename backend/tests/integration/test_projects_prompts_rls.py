"""Integration: projects / prompts / prompt_versions CRUD.

Proves the full feature end-to-end: authenticated + role-gated routes, tenant
isolation via RLS, and the IMMUTABLE versioning of prompt_versions (append-only,
server-assigned monotonic version numbers, no update/delete of a version).

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
async def test_projects_prompts_versions_crud_authz_and_isolation() -> None:
    if not await _db_reachable():
        pytest.skip("No database reachable at DATABASE_URL")

    suffix = uuid.uuid4().hex[:8]
    slug_a, slug_b = f"pp-a-{suffix}", f"pp-b-{suffix}"
    org_a = await _create_org(slug_a)
    org_b = await _create_org(slug_b)

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            admin = await _register_login(client, slug_a, "admin@a.io")  # first user → admin
            member = await _register_login(client, slug_a, "member@a.io")  # not admin
            other = await _register_login(client, slug_b, "admin@b.io")  # tenant B

            # ── Unauthenticated → 401 everywhere ─────────────────────────────
            assert (await client.get("/v1/projects")).status_code == 401

            # ── Projects: member can create + list + get + update ────────────
            created = await client.post(
                "/v1/projects",
                headers=_bearer(member),
                json={"slug": "proj-1", "name": "Project One"},
            )
            assert created.status_code == 201, created.text
            project = created.json()
            project_id = project["id"]
            assert project["tenant_id"] == str(org_a)
            assert project["created_by"] is not None

            # Duplicate slug → 409.
            dup = await client.post(
                "/v1/projects",
                headers=_bearer(member),
                json={"slug": "proj-1", "name": "dupe"},
            )
            assert dup.status_code == 409, dup.text

            listed = await client.get("/v1/projects", headers=_bearer(member))
            assert [p["id"] for p in listed.json()] == [project_id]

            patched = await client.patch(
                f"/v1/projects/{project_id}",
                headers=_bearer(member),
                json={"description": "updated"},
            )
            assert patched.status_code == 200
            assert patched.json()["description"] == "updated"

            # ── Prompts under the project ────────────────────────────────────
            prompt_resp = await client.post(
                f"/v1/projects/{project_id}/prompts",
                headers=_bearer(member),
                json={"slug": "greet", "name": "Greeting"},
            )
            assert prompt_resp.status_code == 201, prompt_resp.text
            prompt_id = prompt_resp.json()["id"]
            assert prompt_resp.json()["project_id"] == project_id

            # Prompt under a non-existent project → 404.
            missing = await client.post(
                f"/v1/projects/{uuid.uuid4()}/prompts",
                headers=_bearer(member),
                json={"slug": "x", "name": "x"},
            )
            assert missing.status_code == 404

            prompts_listed = await client.get(
                f"/v1/projects/{project_id}/prompts", headers=_bearer(member)
            )
            assert [p["id"] for p in prompts_listed.json()] == [prompt_id]

            # ── Immutable versioning ─────────────────────────────────────────
            v1 = await client.post(
                f"/v1/prompts/{prompt_id}/versions",
                headers=_bearer(member),
                json={"content": "Hello v1", "model_target": "claude"},
            )
            assert v1.status_code == 201, v1.text
            assert v1.json()["version"] == 1
            assert v1.json()["content"] == "Hello v1"
            assert v1.json()["author_id"] is not None

            v2 = await client.post(
                f"/v1/prompts/{prompt_id}/versions",
                headers=_bearer(member),
                json={"content": "Hello v2"},
            )
            assert v2.status_code == 201
            assert v2.json()["version"] == 2  # monotonic, server-assigned

            versions = await client.get(
                f"/v1/prompts/{prompt_id}/versions", headers=_bearer(member)
            )
            assert [v["version"] for v in versions.json()] == [2, 1]  # newest first

            # Fetch a specific version by its number; content is unchanged.
            got_v1 = await client.get(
                f"/v1/prompts/{prompt_id}/versions/1", headers=_bearer(member)
            )
            assert got_v1.status_code == 200
            assert got_v1.json()["content"] == "Hello v1"

            # A version is IMMUTABLE: no PATCH/PUT/DELETE route exists → 405.
            assert (
                await client.patch(
                    f"/v1/prompts/{prompt_id}/versions/1",
                    headers=_bearer(member),
                    json={"content": "tampered"},
                )
            ).status_code == 405
            assert (
                await client.delete(f"/v1/prompts/{prompt_id}/versions/1", headers=_bearer(member))
            ).status_code == 405

            # ── Tenant isolation: B sees none of A's rows ────────────────────
            assert (await client.get("/v1/projects", headers=_bearer(other))).json() == []
            assert (
                await client.get(f"/v1/projects/{project_id}", headers=_bearer(other))
            ).status_code == 404
            assert (
                await client.get(f"/v1/prompts/{prompt_id}", headers=_bearer(other))
            ).status_code == 404
            assert (
                await client.get(f"/v1/prompts/{prompt_id}/versions", headers=_bearer(other))
            ).status_code == 404

            # ── Delete is org-admin only (soft delete) ───────────────────────
            # Prompt: member → 403, admin → 204.
            assert (
                await client.delete(f"/v1/prompts/{prompt_id}", headers=_bearer(member))
            ).status_code == 403
            assert (
                await client.delete(f"/v1/prompts/{prompt_id}", headers=_bearer(admin))
            ).status_code == 204
            # Gone from reads after soft delete.
            assert (
                await client.get(f"/v1/prompts/{prompt_id}", headers=_bearer(member))
            ).status_code == 404
            assert (
                await client.get(f"/v1/projects/{project_id}/prompts", headers=_bearer(member))
            ).json() == []

            # Project: member → 403, admin → 204, then gone.
            assert (
                await client.delete(f"/v1/projects/{project_id}", headers=_bearer(member))
            ).status_code == 403
            assert (
                await client.delete(f"/v1/projects/{project_id}", headers=_bearer(admin))
            ).status_code == 204
            assert (await client.get("/v1/projects", headers=_bearer(member))).json() == []
            assert (
                await client.get(f"/v1/projects/{project_id}", headers=_bearer(member))
            ).status_code == 404
    finally:
        await _delete_org(org_a)
        await _delete_org(org_b)
