"""Smoke tests that need no external services."""

from __future__ import annotations

import httpx
import pytest

from app import __version__
from app.main import app


@pytest.mark.asyncio
async def test_liveness() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_reports_version_and_db() -> None:
    """Without a database, /v1/health returns 200 with db=ko and the version."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == __version__
    assert body["db"] == "ko"
    assert body["status"] == "degraded"


@pytest.mark.asyncio
async def test_pipeline_runs_all_stages_understand_real() -> None:
    """The pipeline runs end-to-end key-less (heuristic): understand and strategize
    are real, later stages are still STUB. (The /compile route itself is auth-gated —
    see tests/test_compile.py.)"""
    from app.engines.pipeline import build_default_pipeline

    ctx = await build_default_pipeline().run("Implémente une fonction qui parse un fichier CSV")
    by_stage = {r.stage: r for r in ctx.trace}
    assert ctx.trace[0].stage == "understand"
    assert ctx.trace[1].stage == "strategize"
    assert by_stage["understand"].is_stub is False
    assert by_stage["strategize"].is_stub is False
    # strategize consumed the CATR into a real Strategy.
    strategy = ctx.artifacts["strategize"]
    assert strategy["method"] == "heuristic-v1"
    assert strategy["approach"] in {"single_step", "multi_step", "clarify_first"}
    assert isinstance(strategy["steps"], list)
    # At least one later stage is still a placeholder.
    assert any(r.is_stub for r in ctx.trace)
