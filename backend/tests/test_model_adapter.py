"""Unit tests for the Model Adapter Engine (bloc F; deterministic, no DB, no LLM).

The family is detected from the registry ``provider`` first, then the model name as tokens,
then falls back to a portable ``generic`` default; conventions are read from a DATA table and
never hardcoded per-vendor. The woven directives never force a chain-of-thought (an efficiency
anti-pattern on a strong reasoner), the base prompt stays model-independent, and every known
family is reported so portability is explicit.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.engines.model_adapter import ModelAdapterEngine, adapter_prompt_lines
from app.schemas.registry import ModelCapability, ReasoningStrength


def _profile(
    *,
    model: str = "gpt-4o",
    provider: str = "openai",
    reasoning: ReasoningStrength = "advanced",
) -> ModelCapability:
    return ModelCapability(
        model=model,
        provider=provider,
        context_window=128_000,
        supports_tools=True,
        supports_vision=True,
        structured_output=True,
        reasoning_strength=reasoning,
        cost_in=2.5,
        cost_out=10.0,
        latency_ms=800,
        last_verified=date(2026, 10, 2),
    )


def _adapt(**kw: object):
    return ModelAdapterEngine().adapt(_profile(**kw))  # type: ignore[arg-type]


def test_family_from_provider_anthropic() -> None:
    rep = _adapt(model="claude-sonnet-5-5", provider="anthropic", reasoning="frontier")
    assert rep.family == "anthropic"
    assert rep.label.startswith("Anthropic")
    assert rep.directives  # a family-specific directive is woven
    assert any("xml" in d.lower() for d in rep.directives)
    assert rep.reasoning_native is True  # frontier → never force chain-of-thought


def test_family_from_provider_openai() -> None:
    rep = _adapt(model="gpt-4o", provider="openai")
    assert rep.family == "openai"
    assert rep.directives


def test_family_falls_back_to_name_token_when_provider_unknown() -> None:
    # Unknown provider, but the model name carries a recognisable family token.
    rep = _adapt(model="qwen2.5-72b-instruct", provider="self-hosted", reasoning="medium")
    assert rep.family == "qwen"
    rep2 = _adapt(model="deepseek-r1", provider="unknown-host", reasoning="advanced")
    assert rep2.family == "deepseek"


def test_unknown_family_falls_back_to_generic_and_injects_nothing() -> None:
    rep = _adapt(model="acme-llm-7b", provider="acme", reasoning="medium")
    assert rep.family == "generic"
    assert rep.directives == []
    assert adapter_prompt_lines(rep) == []  # nothing family-specific to weave


def test_no_profile_is_portable_generic_with_no_target() -> None:
    rep = ModelAdapterEngine().adapt(None)
    assert rep.target_model is None and rep.provider is None
    assert rep.family == "generic"
    assert rep.directives == [] and rep.injected is False
    assert rep.model_independent is True


def test_reasoning_native_detection() -> None:
    # A weak, non-reasoning model is not native.
    assert _adapt(model="gpt-4o-mini", provider="openai", reasoning="medium").reasoning_native is (
        False
    )
    # A reasoning-variant NAME flips it on even at a lower declared strength.
    assert _adapt(model="o3-mini", provider="openai", reasoning="medium").reasoning_native is True


def test_directives_never_force_chain_of_thought() -> None:
    # Consistency with prompt_scorer.forced_cot: no family directive may push step-by-step CoT.
    for port in ModelAdapterEngine().adapt(None).known_families:
        for d in port.directives:
            low = d.lower()
            assert "step by step" not in low and "étape par étape" not in low


def test_portability_map_lists_every_known_family() -> None:
    rep = _adapt(model="gpt-4o", provider="openai")
    families = {p.family for p in rep.known_families}
    assert {"anthropic", "openai", "google", "deepseek", "qwen", "mistral", "meta", "generic"} <= (
        families
    )
    for p in rep.known_families:
        assert p.label and p.porting_note  # each family explains how to port to it


def test_adapter_prompt_lines_match_directives() -> None:
    rep = _adapt(model="claude-sonnet-5-5", provider="anthropic", reasoning="frontier")
    assert adapter_prompt_lines(rep) == rep.directives


def test_note_is_honest_about_conventions_not_guarantees() -> None:
    rep = _adapt(model="gpt-4o", provider="openai")
    assert "pas des garanties" in rep.note
    assert "indépendant du modèle" in rep.note.lower() or "indépendant du modèle" in (
        rep.portability_note.lower()
    )


@pytest.mark.parametrize("provider", ["ANTHROPIC", "Anthropic", "anthropic"])
def test_provider_match_is_case_insensitive(provider: str) -> None:
    assert _adapt(model="claude-x", provider=provider, reasoning="frontier").family == "anthropic"
