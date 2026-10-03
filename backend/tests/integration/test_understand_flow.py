"""Integration: the async `understand` flow (executions + ARQ worker + RLS).

Covers:
- POST /executions validates the version has a source_intent (422) and otherwise
  creates a pending, tenant-scoped execution;
- the worker task turns source_intent into a CATR, writing it to the execution
  output AND the prompt version's `catr`;
- the worker is tenant-confined (running it under the wrong tenant is a no-op);
- cross-tenant isolation on the executions list;
- the full queue path end-to-end (POST -> ARQ burst worker -> poll succeeded),
  when a Redis is reachable.

Requires a migrated DB reached as the app role; skips otherwise. The full queue
path additionally needs Redis (REDIS_URL). DISPOSABLE DB.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import sqlalchemy as sa

from app.core.queue import get_redis_settings
from app.core.tenancy import apply_tenant_guc
from app.db.session import engine, session_scope
from app.main import app
from app.models.organization import Organization
from app.models.prompt import PromptVersion
from app.workers.tasks import run_pipeline_task, shutdown, startup

_INTENT = "Implémente une fonction qui parse un fichier ventes.csv en Python"


async def _db_reachable() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
        return True
    except Exception:
        return False


async def _redis_reachable() -> bool:
    try:
        from arq import create_pool

        pool = await create_pool(get_redis_settings())
        await pool.ping()
        await pool.aclose()
        return True
    except Exception:
        return False


async def _create_org(slug: str) -> uuid.UUID:
    org_id = uuid.uuid4()
    async with session_scope() as s:
        await apply_tenant_guc(s, org_id)
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


async def _make_version(client: httpx.AsyncClient, token: str, *, source_intent: str | None) -> str:
    suffix = uuid.uuid4().hex[:8]
    project = await client.post(
        "/v1/projects", headers=_bearer(token), json={"slug": f"u-{suffix}", "name": "U"}
    )
    project_id = project.json()["id"]
    prompt = await client.post(
        f"/v1/projects/{project_id}/prompts",
        headers=_bearer(token),
        json={"slug": f"p-{suffix}", "name": "P"},
    )
    prompt_id = prompt.json()["id"]
    body: dict[str, object] = {"content": "You are a helpful assistant."}
    if source_intent is not None:
        body["source_intent"] = source_intent
    version = await client.post(
        f"/v1/prompts/{prompt_id}/versions", headers=_bearer(token), json=body
    )
    assert version.status_code == 201, version.text
    return str(version.json()["id"])


@pytest.mark.asyncio
async def test_understand_async_flow_and_isolation() -> None:
    if not await _db_reachable():
        pytest.skip("No database reachable at DATABASE_URL")

    suffix = uuid.uuid4().hex[:8]
    slug_a, slug_b = f"und-a-{suffix}", f"und-b-{suffix}"
    org_a = await _create_org(slug_a)
    org_b = await _create_org(slug_b)

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            member = await _register_login(client, slug_a, "member@a.io")
            other = await _register_login(client, slug_b, "admin@b.io")

            # ── 422 when the version has no source_intent ──────────────────────
            empty_version = await _make_version(client, member, source_intent=None)
            no_intent = await client.post(
                "/v1/executions", headers=_bearer(member), json={"prompt_version_id": empty_version}
            )
            assert no_intent.status_code == 422, no_intent.text

            # ── Create a runnable version + a pending execution ────────────────
            version_id = await _make_version(client, member, source_intent=_INTENT)
            created = await client.post(
                "/v1/executions", headers=_bearer(member), json={"prompt_version_id": version_id}
            )
            assert created.status_code == 202, created.text
            execution = created.json()
            exec_id = execution["id"]
            assert execution["status"] == "pending"
            assert execution["tenant_id"] == str(org_a)
            assert execution["input"]["stage"] == "pipeline"

            # ── Worker logic (direct call) runs the FULL pipeline ──────────────
            result = await run_pipeline_task({}, exec_id, str(org_a))
            assert result["status"] == "succeeded", result

            fetched = await client.get(f"/v1/executions/{exec_id}", headers=_bearer(member))
            assert fetched.status_code == 200
            body = fetched.json()
            assert body["status"] == "succeeded"
            catr = body["output"]["catr"]
            assert catr["meta"]["method"] == "heuristic-v1"
            assert catr["domain"] == "software"
            assert catr["objective"]
            assert body["started_at"] is not None and body["finished_at"] is not None
            # The single pipeline ran end to end — its per-stage trace is recorded,
            # starting with understand.
            trace = body["output"]["trace"]
            assert trace and trace[0]["stage"] == "understand"

            # The CATR is also written back onto the prompt version (checked in DB,
            # tenant-scoped, since there is no raw-version GET that exposes catr here).
            async with session_scope() as s:
                await apply_tenant_guc(s, org_a)
                stored = await s.get(PromptVersion, uuid.UUID(version_id))
                assert stored is not None
                assert stored.catr is not None
                assert stored.catr["domain"] == "software"

            # ── Worker is tenant-confined: running under B can't touch A's row ──
            pending = await client.post(
                "/v1/executions", headers=_bearer(member), json={"prompt_version_id": version_id}
            )
            pending_id = pending.json()["id"]
            wrong_tenant = await run_pipeline_task({}, pending_id, str(org_b))
            assert wrong_tenant["status"] == "missing"  # invisible to tenant B
            still_pending = await client.get(
                f"/v1/executions/{pending_id}", headers=_bearer(member)
            )
            assert still_pending.json()["status"] == "pending"

            # ── Cross-tenant isolation on the list ─────────────────────────────
            assert (await client.get("/v1/executions", headers=_bearer(other))).json() == []
            mine = await client.get("/v1/executions", headers=_bearer(member))
            assert {e["id"] for e in mine.json()} >= {exec_id, pending_id}

            # ── Full queue path (POST -> ARQ burst worker -> poll) ─────────────
            if await _redis_reachable():
                from arq.worker import Worker

                queued = await client.post(
                    "/v1/executions",
                    headers=_bearer(member),
                    json={"prompt_version_id": version_id},
                )
                queued_id = queued.json()["id"]
                worker = Worker(
                    functions=[run_pipeline_task],
                    redis_settings=get_redis_settings(),
                    on_startup=startup,
                    on_shutdown=shutdown,
                    burst=True,
                    poll_delay=0.05,
                )
                await worker.async_run()
                await worker.close()

                polled = await client.get(f"/v1/executions/{queued_id}", headers=_bearer(member))
                assert polled.json()["status"] == "succeeded", polled.text
                assert polled.json()["output"]["catr"]["domain"] == "software"
    finally:
        await _delete_org(org_a)
        await _delete_org(org_b)
