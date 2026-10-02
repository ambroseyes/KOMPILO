"""Unit tests for the Claude-backed understand analyzer (scripted FakeLLMClient).

No network, no API key: the LLM port is faked. These cover the forced-tool
round-trip into a ``Catr`` (``claude-v1``), the bounded retry/validation behaviour,
and the ``understand`` engine-selection + heuristic fallback.
"""

from __future__ import annotations

import pytest

import app.engines.understand as understand_mod
from app.engines.llm import FakeLLMClient
from app.engines.llm.base import LLMError, LLMTimeout, LLMToolCall
from app.engines.understand import analyze_intent_llm, understand


def _valid_args(**overrides: object) -> dict[str, object]:
    args: dict[str, object] = {
        "goal": "Produce a 3-bullet summary.",
        "task_type": "qa",
        "language": "en",
        "entities": [],
        "inputs": [],
        "constraints": [],
        "assumptions": [],
        "open_questions": [],
        "success_criteria": [],
        "confidence": 0.9,
    }
    args.update(overrides)
    return args


def _call(args: dict[str, object]) -> LLMToolCall:
    return LLMToolCall(
        name="analyze_intent",
        arguments=args,
        model="fake-model",
        usage={"input_tokens": 10, "output_tokens": 20},
    )


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the retry backoff so tests stay fast."""

    async def _instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(understand_mod.asyncio, "sleep", _instant)


async def test_llm_nominal_produces_catr_marked_claude() -> None:
    llm = FakeLLMClient([_call(_valid_args())])
    catr = await analyze_intent_llm("Summarise this article", {}, llm)
    assert catr.method == "claude-v1"  # provenance stamped by us, not the model
    assert catr.task_type == "qa"
    assert catr.goal == "Produce a 3-bullet summary."
    assert llm.call_count == 1


async def test_llm_retries_then_succeeds() -> None:
    llm = FakeLLMClient([LLMTimeout("slow"), _call(_valid_args())])
    catr = await analyze_intent_llm("x", {}, llm)
    assert catr.method == "claude-v1"
    assert llm.call_count == 2


async def test_llm_gives_up_after_bounded_retries() -> None:
    llm = FakeLLMClient([LLMTimeout("1"), LLMTimeout("2"), LLMTimeout("3")])
    with pytest.raises(LLMError):
        await analyze_intent_llm("x", {}, llm)
    assert llm.call_count == 3  # llm_max_retries (2) + 1


async def test_llm_rejects_offschema_tool_call() -> None:
    # confidence out of range → validation fails on every attempt → raises.
    llm = FakeLLMClient([_call(_valid_args(confidence=5.0))] * 3)
    with pytest.raises(Exception):  # noqa: B017 — ValidationError or LLMError
        await analyze_intent_llm("x", {}, llm)


async def test_understand_falls_back_to_heuristic_without_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(understand_mod, "get_llm_client", lambda: None)
    catr = await understand("Analyse le fichier ventes.csv en Python")
    assert catr.method == "heuristic-v1"  # no key → deterministic heuristic


async def test_understand_falls_back_when_llm_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    failing = FakeLLMClient([LLMError("boom")] * 3)
    monkeypatch.setattr(understand_mod, "get_llm_client", lambda: failing)
    catr = await understand("Corrige le bug dans la fonction de login")
    assert catr.method == "heuristic-v1"  # degraded honestly, not an error


async def test_understand_uses_llm_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = FakeLLMClient([_call(_valid_args())])
    monkeypatch.setattr(understand_mod, "get_llm_client", lambda: llm)
    catr = await understand("Summarise this article")
    assert catr.method == "claude-v1"
    assert llm.call_count == 1
