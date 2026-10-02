"""Integration: projects / prompts / prompt_versions CRUD + versioning + isolation.

Exercises the item-2 business routes against a real migrated DB reached as the
least-privilege app role (RLS active). Skips if no DB is reachable. DISPOSABLE DB.

Covered:
- authenticated, tenant-scoped CRUD for projects and prompts;
- monotonic version allocation (1, 2, 3 …) per prompt;
- cross-tenant isolation (tenant B never sees tenant A's rows → 404 / empty list);
- role gate (soft-delete is org-admin only);
- cascade soft-delete (deleting a project hides its prompts and versions);
- slug reuse after soft-delete (partial unique index).
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
        await apply_tenant_guc(s, org_id)  # id == GUC so the WITH CHECK passes
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
async def test_projects_prompts_versions_crud_and_isolation() -> None:
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
            other = await _register_login(client, slug_b, "admin@b.io")  # tenant B admin

            # ── Projects: create / read / list, with server-set tenant_id ──────
            created = await client.post(
                "/v1/projects",
                headers=_bearer(member),
                json={"slug": "alpha", "name": "Alpha", "description": "first"},
            )
            assert created.status_code == 201, created.text
            project = created.json()
            project_id = project["id"]
            assert project["tenant_id"] == str(org_a)
            assert project["created_by"] is not None  # derived from the token's user

            listed = await client.get("/v1/projects", headers=_bearer(member))
            assert [p["id"] for p in listed.json()] == [project_id]

            # Duplicate live slug → 409 (partial unique index).
            dup = await client.post(
                "/v1/projects", headers=_bearer(member), json={"slug": "alpha", "name": "Dup"}
            )
            assert dup.status_code == 409, dup.text

            # ── Prompts under the project ──────────────────────────────────────
            p_created = await client.post(
                f"/v1/projects/{project_id}/prompts",
                headers=_bearer(member),
                json={"slug": "greeting", "name": "Greeting"},
            )
            assert p_created.status_code == 201, p_created.text
            prompt = p_created.json()
            prompt_id = prompt["id"]
            assert prompt["project_id"] == project_id
            assert prompt["tenant_id"] == str(org_a)

            p_listed = await client.get(
                f"/v1/projects/{project_id}/prompts", headers=_bearer(member)
            )
            assert [p["id"] for p in p_listed.json()] == [prompt_id]

            # ── Versioning: monotonic 1, 2, 3 ──────────────────────────────────
            numbers = []
            for i in range(3):
                v = await client.post(
                    f"/v1/prompts/{prompt_id}/versions",
                    headers=_bearer(member),
                    json={"model_target": f"m{i}", "catr": {"n": i}},
                )
                assert v.status_code == 201, v.text
                numbers.append(v.json()["version"])
            assert numbers == [1, 2, 3]

            v_listed = await client.get(
                f"/v1/prompts/{prompt_id}/versions", headers=_bearer(member)
            )
            assert [v["version"] for v in v_listed.json()] == [1, 2, 3]

            got_v2 = await client.get(
                f"/v1/prompts/{prompt_id}/versions/2", headers=_bearer(member)
            )
            assert got_v2.status_code == 200
            assert got_v2.json()["version"] == 2
            assert got_v2.json()["catr"] == {"n": 1}
            assert got_v2.json()["author_id"] is not None

            # ── Update a prompt (partial) ──────────────────────────────────────
            patched = await client.patch(
                f"/v1/prompts/{prompt_id}",
                headers=_bearer(member),
                json={"name": "Greeting v2"},
            )
            assert patched.status_code == 200
            assert patched.json()["name"] == "Greeting v2"

            # ── Cross-tenant isolation (tenant B sees nothing of A) ────────────
            assert (await client.get("/v1/projects", headers=_bearer(other))).json() == []
            assert (
                await client.get(f"/v1/projects/{project_id}", headers=_bearer(other))
            ).status_code == 404
            assert (
                await client.get(f"/v1/prompts/{prompt_id}", headers=_bearer(other))
            ).status_code == 404
            # B cannot append a version to A's (invisible) prompt.
            assert (
                await client.post(
                    f"/v1/prompts/{prompt_id}/versions", headers=_bearer(other), json={}
                )
            ).status_code == 404

            # ── Role gate: soft-delete is org-admin only ───────────────────────
            assert (
                await client.delete(f"/v1/prompts/{prompt_id}", headers=_bearer(member))
            ).status_code == 403

            # ── Cascade soft-delete a project → prompts + versions hidden ──────
            assert (
                await client.delete(f"/v1/projects/{project_id}", headers=_bearer(admin))
            ).status_code == 204
            assert (await client.get("/v1/projects", headers=_bearer(member))).json() == []
            assert (
                await client.get(f"/v1/projects/{project_id}", headers=_bearer(member))
            ).status_code == 404
            # The prompt (and thus its versions) is now unreachable.
            assert (
                await client.get(f"/v1/prompts/{prompt_id}", headers=_bearer(member))
            ).status_code == 404

            # ── Slug reuse after soft-delete (partial unique index) ────────────
            recreated = await client.post(
                "/v1/projects", headers=_bearer(member), json={"slug": "alpha", "name": "Alpha 2"}
            )
            assert recreated.status_code == 201, recreated.text
            assert recreated.json()["id"] != project_id
    finally:
        await _delete_org(org_a)
        await _delete_org(org_b)
