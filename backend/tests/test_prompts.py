"""No-DB unit tests for the prompts / prompt-versions routes (auth gate)."""

from __future__ import annotations

import uuid

import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_prompts_require_auth() -> None:
    """Without a token every prompt/version route is 401 — before any DB access."""
    project_id = uuid.uuid4()
    prompt_id = uuid.uuid4()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        create_prompt = await client.post(
            f"/v1/projects/{project_id}/prompts", json={"slug": "x", "name": "X"}
        )
        list_prompts = await client.get(f"/v1/projects/{project_id}/prompts")
        get_prompt = await client.get(f"/v1/prompts/{prompt_id}")
        create_version = await client.post(f"/v1/prompts/{prompt_id}/versions", json={})
        list_versions = await client.get(f"/v1/prompts/{prompt_id}/versions")
    assert create_prompt.status_code == 401
    assert list_prompts.status_code == 401
    assert get_prompt.status_code == 401
    assert create_version.status_code == 401
    assert list_versions.status_code == 401
