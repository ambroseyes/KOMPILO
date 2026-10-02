"""No-DB unit tests for the Intent Engine v1 and its heuristics.

The heuristic path is deterministic and offline. The LLM path is exercised with an
injected fake provider (no network, no key), including the cost-control rule that the
LLM is NOT called when heuristic confidence is high.
"""

from __future__ import annotations

import pytest

from app.engines.intent import IntentEngine
from app.engines.providers.base import CompletionResult, ProviderCapabilities, ProviderError
from app.schemas.catr import CanonicalAITask


def _caps(name: str) -> ProviderCapabilities:
    return ProviderCapabilities(provider=name, supports_streaming=False, is_real=False)


class _FakeProvider:
    """Records calls and returns a canned JSON completion."""

    name = "fake"

    def __init__(self, response: str) -> None:
        self._response = response
        self.calls = 0

    def capabilities(self) -> ProviderCapabilities:
        return _caps(self.name)

    async def complete(
        self, *, model: str, prompt: str, system: str | None = None, **_: object
    ) -> CompletionResult:
        self.calls += 1
        return CompletionResult(self._response, 1, 1, model, self.name)


class _FailingProvider:
    name = "failing"

    def __init__(self) -> None:
        self.calls = 0

    def capabilities(self) -> ProviderCapabilities:
        return _caps(self.name)

    async def complete(
        self, *, model: str, prompt: str, system: str | None = None, **_: object
    ) -> CompletionResult:
        self.calls += 1
        raise ProviderError("boom")


# ── Heuristic path (no provider) ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_heuristic_method_and_type() -> None:
    catr = await IntentEngine().run("Implémente une fonction qui parse un fichier")
    assert isinstance(catr, CanonicalAITask)
    assert catr.meta.method == "heuristic-v1"
    assert catr.meta.enriched_by_llm is False


@pytest.mark.asyncio
async def test_is_deterministic() -> None:
    intent = "Analyse les données du fichier ventes.csv et calcule la moyenne"
    a = await IntentEngine().run(intent)
    b = await IntentEngine().run(intent)
    assert a.model_dump() == b.model_dump()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("intent", "domain"),
    [
        ("Implémente une fonction qui parse un fichier", "software"),
        ("Analyse les données du fichier ventes.csv et calcule la moyenne", "data"),
        ("Write a short blog post about climate change", "writing"),
        ("Planifie la roadmap du projet sur trois mois", "product"),
        ("Pourquoi le ciel est-il bleu ?", "general"),
    ],
)
async def test_domain_classification(intent: str, domain: str) -> None:
    catr = await IntentEngine().run(intent)
    assert catr.domain == domain
    assert catr.objective
    assert 0.0 <= catr.meta.confidence <= 1.0


@pytest.mark.asyncio
async def test_extracts_inputs_context_and_expected_output() -> None:
    catr = await IntentEngine().run("Analyse le fichier ventes.csv en Python")
    assert "ventes.csv" in catr.inputs
    assert any("python" in c.lower() for c in catr.context)
    assert catr.expected_output is not None  # data_analysis has a template


@pytest.mark.asyncio
async def test_code_without_language_flags_missing_information() -> None:
    catr = await IntentEngine().run("Corrige le bug dans la fonction de login")
    labels = {m.label for m in catr.missing_information}
    assert any("langage" in label or "language" in label for label in labels)
    assert any(m.importance == "high" for m in catr.missing_information)


@pytest.mark.asyncio
async def test_risk_detection_for_destructive_intent() -> None:
    catr = await IntentEngine().run("Supprime la base de données en production")
    assert catr.risk == "high"


@pytest.mark.asyncio
async def test_vague_intent_is_low_confidence_and_flagged() -> None:
    catr = await IntentEngine().run("truc")
    assert catr.meta.confidence < 0.5
    assert catr.ambiguities
    assert catr.missing_information


# ── LLM path (injected fake provider) ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_llm_refines_when_confidence_low() -> None:
    fake = _FakeProvider('{"objective": "Objectif raffiné", "expected_output": "Sortie raffinée"}')
    catr = await IntentEngine(provider=fake).run("truc")  # vague → low confidence
    assert fake.calls == 1
    assert catr.meta.enriched_by_llm is True
    assert catr.meta.method == "heuristic-v1+llm"
    assert catr.objective == "Objectif raffiné"
    assert catr.expected_output == "Sortie raffinée"


@pytest.mark.asyncio
async def test_llm_not_called_when_confidence_high() -> None:
    """Cost control: a clear intent stays on the free heuristic path."""
    fake = _FakeProvider("{}")
    intent = "Analyse les données du fichier ventes.csv et calcule la moyenne et la médiane"
    catr = await IntentEngine(provider=fake).run(intent)
    assert fake.calls == 0
    assert catr.meta.enriched_by_llm is False


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_heuristics() -> None:
    failing = _FailingProvider()
    catr = await IntentEngine(provider=failing).run("truc")
    assert failing.calls == 1
    assert catr.meta.enriched_by_llm is False  # fell back cleanly
    assert catr.meta.method == "heuristic-v1"


@pytest.mark.asyncio
async def test_llm_bad_json_falls_back() -> None:
    fake = _FakeProvider("this is not json")
    catr = await IntentEngine(provider=fake).run("truc")
    assert catr.meta.enriched_by_llm is False
