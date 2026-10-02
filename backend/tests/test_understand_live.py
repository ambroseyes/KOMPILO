"""Live smoke test for the Claude-backed understand analyzer against Anthropic.

Skipped unless ANTHROPIC_API_KEY is set, so it never runs in CI or key-less dev.
Run it manually to validate the prompt and the forced-tool round-trip:

    ANTHROPIC_API_KEY=... pytest -m live tests/test_understand_live.py
"""

from __future__ import annotations

import os

import pytest

from app.engines.understand import understand

pytestmark = pytest.mark.live

_NO_KEY = not os.getenv("ANTHROPIC_API_KEY")


@pytest.mark.skipif(_NO_KEY, reason="ANTHROPIC_API_KEY not set")
async def test_live_understand_round_trip() -> None:
    catr = await understand(
        "Translate the product description into French, under 100 words.",
        {"locale": "fr-FR"},
    )

    assert catr.method == "claude-v1"  # a real model call, not the heuristic
    assert catr.goal
    assert catr.task_type in {
        "code_generation",
        "data_analysis",
        "writing",
        "qa",
        "planning",
        "other",
    }
    assert 0.0 <= catr.confidence <= 1.0
