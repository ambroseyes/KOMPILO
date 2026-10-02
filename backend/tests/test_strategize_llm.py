"""Unit tests for the Claude-backed strategize planner (scripted FakeLLMClient).

No network, no API key: the LLM port is faked. These cover the forced-tool
round-trip into a ``Strategy`` (``claude-v1``), the bounded retry/validation
behaviour, and the ``strategize`` engine-selection + heuristic fallback.
"""

from __future__ import annotations

import pytest

import app.engines.strategize as strategize_mod
from app.engines.llm import FakeLLMClient
from app.engines.llm.base import LLMError, LLMTimeout, LLMToolCall
from app.engines.strategize import strategize, strategize_llm
from app.schemas.catr import Catr


def _catr(**overrides: object) -> Catr:
    base: dict[str, object] = {
        "method": "heuristic-v1",
        "goal": "Résumer un article",
        "task_type": "qa",
        "language": "fr",
        "entities": [],
        "inputs": [],
        "constraints": [],
        "assumptions": [],
        "open_questions": [],
        "success_criteria": [],
        "confidence": 0.8,
    }
    base.update(overrides)
    return Catr.model_validate(base)


def _valid_args(**overrides: object) -> dict[str, object]:
    args: dict[str, object] = {
        "approach": "multi_step",
        "rationale": "Décomposer en étapes ordonnées.",
        "steps": [
            {"order": 1, "title": "Lire", "description": "Lire l'article.", "depends_on": []},
            {
                "order": 2,
                "title": "Résumer",
                "description": "Produire le résumé.",
                "depends_on": [1],
            },
        ],
        "candidate_count": 2,
        "needs_clarification": False,
        "confidence": 0.85,
    }
    args.update(overrides)
    return args


def _call(args: dict[str, object]) -> LLMToolCall:
    return LLMToolCall(
        name="propose_strategy",
        arguments=args,
        model="fake-model",
        usage={"input_tokens": 10, "output_tokens": 20},
    )


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the retry backoff so tests stay fast."""

    async def _instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(strategize_mod.asyncio, "sleep", _instant)


async def test_llm_nominal_produces_strategy_marked_claude() -> None:
    llm = FakeLLMClient([_call(_valid_args())])
    strategy = await strategize_llm(_catr(), {}, llm)
    assert strategy.method == "claude-v1"  # provenance stamped by us, not the model
    assert strategy.approach == "multi_step"
    assert len(strategy.steps) == 2
    assert llm.call_count == 1


async def test_llm_retries_then_succeeds() -> None:
    llm = FakeLLMClient([LLMTimeout("slow"), _call(_valid_args())])
    strategy = await strategize_llm(_catr(), {}, llm)
    assert strategy.method == "claude-v1"
    assert llm.call_count == 2


async def test_llm_gives_up_after_bounded_retries() -> None:
    llm = FakeLLMClient([LLMTimeout("1"), LLMTimeout("2"), LLMTimeout("3")])
    with pytest.raises(LLMError):
        await strategize_llm(_catr(), {}, llm)
    assert llm.call_count == 3  # llm_max_retries (2) + 1


async def test_llm_rejects_offschema_tool_call() -> None:
    # confidence out of range → validation fails on every attempt → raises.
    llm = FakeLLMClient([_call(_valid_args(confidence=5.0))] * 3)
    with pytest.raises(Exception):  # noqa: B017 — ValidationError or LLMError
        await strategize_llm(_catr(), {}, llm)


async def test_strategize_falls_back_to_heuristic_without_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(strategize_mod, "get_llm_client", lambda: None)
    strategy = await strategize(_catr(task_type="code_generation", confidence=0.8))
    assert strategy.method == "heuristic-v1"  # no key → deterministic heuristic


async def test_strategize_falls_back_when_llm_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    failing = FakeLLMClient([LLMError("boom")] * 3)
    monkeypatch.setattr(strategize_mod, "get_llm_client", lambda: failing)
    strategy = await strategize(_catr(task_type="code_generation", confidence=0.8))
    assert strategy.method == "heuristic-v1"  # degraded honestly, not an error


async def test_strategize_uses_llm_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = FakeLLMClient([_call(_valid_args())])
    monkeypatch.setattr(strategize_mod, "get_llm_client", lambda: llm)
    strategy = await strategize(_catr())
    assert strategy.method == "claude-v1"
    assert llm.call_count == 1
