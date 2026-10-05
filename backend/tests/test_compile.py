"""E2E tests for POST /v1/compile (public, stateless — no DB).

Covers a real PROCEED task (plan + compiled prompt + multidimensional diagnostics),
the ASK branch (critical gaps → questions, no prompt), mode selection and target-model
forcing. The Intent Engine stays on its deterministic heuristic path (no API key).
"""

from __future__ import annotations

import httpx
import pytest

from app.main import app

_CLEAR_TASK = (
    "Implémente une fonction Python qui valide une adresse email, avec des tests unitaires"
)


async def _post(body: dict[str, object]) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/v1/compile", json=body)


@pytest.mark.asyncio
async def test_compile_proceeds_on_clear_task() -> None:
    resp = await _post({"task": _CLEAR_TASK})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # "Understood" is always present (shown first in the UI).
    assert body["understood"]["objective"]
    assert body["understood"]["domain"]

    # PROCEED: no questions, a full plan and a compiled prompt.
    assert body["questions"] == []
    assert body["execution_plan"] is not None
    assert body["execution_plan"]["strategy"] in {"single", "chain", "rag"}
    assert body["execution_plan"]["target_model"]  # a model was chosen
    assert body["execution_plan"]["cost"]["estimated"] is True  # costs are ESTIMATES

    # Compiled prompt (default mode = professional) + all three renders.
    compiled = body["compiled_prompt"]
    assert compiled["mode"] == "professional"
    assert compiled["text"] == body["renders"]["professional"]
    assert "## Mission" in compiled["text"]
    assert {"role", "mission"} <= set(compiled["sections"])  # role+mission always present
    for variant in ("compact", "professional", "expert"):
        assert body["renders"][variant].strip()

    # Diagnostic is multidimensional and explainable — 8 axes, each low/medium/high,
    # never a single aggregate score.
    dims = {d["dimension"] for d in body["diagnostics"]}
    assert {
        "clarity",
        "completeness",
        "specificity",
        "robustness",
        "executability",
        "context_quality",
        "output_definition",
        "ambiguity_handling",
    } == dims
    for d in body["diagnostics"]:
        assert d["level"] in {"low", "medium", "high"}
        assert d["label"]  # human-readable label present
        # A weak axis always explains itself (reason) and proposes a fix (recommendation).
        if d["level"] != "high":
            assert d["reason"] and d["recommendation"]

    # Prompt quality: a readiness PQS (0-100), 11 weighted explainable axes, findings.
    pq = body["prompt_quality"]
    assert pq is not None
    assert 0 <= pq["pqs"] <= 100
    assert pq["band"] in {"insufficient", "usable", "strong", "execution_ready"}
    assert len(pq["dimensions"]) == 11
    for d in pq["dimensions"]:
        assert 0.0 <= d["score"] <= 1.0 and d["level"] in {"low", "medium", "high"}
    assert isinstance(pq["findings"], list)
    assert pq["summary"]

    assert body["metadata"]["costs_estimated"] is True
    assert body["metadata"]["deterministic"] is True  # no LLM called without a key


@pytest.mark.asyncio
async def test_compile_asks_on_vague_task() -> None:
    resp = await _post({"task": "truc"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["understood"]["objective"]  # still present on ASK
    assert body["questions"]  # at least one clarifying question
    assert body["compiled_prompt"] is None
    assert body["execution_plan"] is None
    assert body["renders"] is None
    assert body["prompt_quality"] is None  # no prompt compiled yet → no PQS
    # A vague task has critical gaps → clarity is "low" with a reason + corrective action.
    clarity = next(d for d in body["diagnostics"] if d["dimension"] == "clarity")
    assert clarity["level"] == "low"
    assert clarity["reason"] and clarity["recommendation"]


@pytest.mark.asyncio
async def test_compile_expert_mode_selects_expert_render() -> None:
    resp = await _post({"task": _CLEAR_TASK, "mode": "expert"})
    body = resp.json()
    assert body["compiled_prompt"]["mode"] == "expert"
    assert body["compiled_prompt"]["text"] == body["renders"]["expert"]
    assert "## Rigor" in body["compiled_prompt"]["text"]


@pytest.mark.asyncio
async def test_compile_can_force_target_model() -> None:
    resp = await _post({"task": _CLEAR_TASK, "target_model": "gpt-4o"})
    body = resp.json()
    assert body["execution_plan"]["target_model"] == "gpt-4o"
    assert body["metadata"]["target_model"] == "gpt-4o"
