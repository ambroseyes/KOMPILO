"""Live smoke test for the real understand stage against Anthropic.

Skipped unless ANTHROPIC_API_KEY is set, so it never runs in CI or key-less dev.
Run it manually to validate the prompt and the forced-tool round-trip:

    ANTHROPIC_API_KEY=... pytest -m live tests/test_understand_live.py
"""

from __future__ import annotations

import os

import pytest

from app.engines.base import PipelineContext
from app.engines.llm import get_llm_client
from app.engines.stages import UnderstandStage

pytestmark = pytest.mark.live

_NO_KEY = not os.getenv("ANTHROPIC_API_KEY")


@pytest.mark.skipif(_NO_KEY, reason="ANTHROPIC_API_KEY not set")
async def test_live_understand_round_trip() -> None:
    client = get_llm_client()
    assert client is not None
    ctx = PipelineContext(
        intent="Translate the product description into French, under 100 words.",
        context={"locale": "fr-FR"},
    )
    result = await UnderstandStage(client).run(ctx)

    assert result.status == "ok", result.note
    understanding = ctx.artifacts["understand"]
    assert understanding["normalized_intent"]
    assert understanding["task_type"] in {
        "generation",
        "extraction",
        "transformation",
        "qa",
        "classification",
        "agentic",
        "other",
    }
    assert 0.0 <= understanding["confidence"] <= 1.0
    assert understanding["model"]
