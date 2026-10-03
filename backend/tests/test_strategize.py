"""No-DB unit tests for the strategize engines: ambiguity, complexity, strategy, router.

All deterministic and offline. Capabilities come from the registry; the router never
knows a model by name.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.engines.ambiguity import AmbiguityEngine
from app.engines.complexity import ComplexityEngine
from app.engines.registry import default_registry, load_model_registry
from app.engines.router import ModelRouter
from app.engines.strategy import StrategyEngine
from app.schemas.catr import CanonicalAITask, CatrMeta, MissingInformation
from app.schemas.registry import ModelCapability
from app.schemas.strategize import ComplexityAssessment, Strategy


def _catr(
    objective: str = "Do a thing",
    *,
    domain: str = "general",
    sub_goals: list[str] | None = None,
    inputs: list[str] | None = None,
    context: list[str] | None = None,
    constraints: list[str] | None = None,
    expected_output: str | None = None,
    missing_information: list[MissingInformation] | None = None,
    ambiguities: list[str] | None = None,
    risk: str = "low",
    catr_complexity: str = "low",
) -> CanonicalAITask:
    return CanonicalAITask(
        objective=objective,
        domain=domain,
        sub_goals=sub_goals or [],
        inputs=inputs or [],
        context=context or [],
        constraints=constraints or [],
        expected_output=expected_output,
        missing_information=missing_information or [],
        ambiguities=ambiguities or [],
        complexity=catr_complexity,  # type: ignore[arg-type]
        risk=risk,  # type: ignore[arg-type]
        meta=CatrMeta(method="heuristic-v1", confidence=0.9, enriched_by_llm=False),
    )


def _assessment(level: str, score: float = 0.5) -> ComplexityAssessment:
    return ComplexityAssessment(level=level, score=score, features={}, method="rules-v1")  # type: ignore[arg-type]


# ── Registry loader ───────────────────────────────────────────────────────────────
def test_registry_loads_three_models_with_last_verified() -> None:
    models = load_model_registry()
    assert len(models) >= 3
    assert all(isinstance(m.last_verified, date) for m in models)
    assert {m.model for m in models} >= {"gpt-4o-mini", "gpt-4o", "claude-sonnet-5-5"}


def test_registry_entry_requires_last_verified() -> None:
    entry = {
        "model": "x",
        "provider": "p",
        "context_window": 1000,
        "supports_tools": True,
        "supports_vision": True,
        "structured_output": True,
        "reasoning_strength": "medium",
        "cost_in": 1.0,
        "cost_out": 1.0,
        "latency_ms": 100,
        # last_verified intentionally omitted
    }
    with pytest.raises(ValidationError):
        ModelCapability.model_validate(entry)


# ── Ambiguity ─────────────────────────────────────────────────────────────────────
def test_ambiguity_proceeds_on_clear_task() -> None:
    report = AmbiguityEngine().analyze(
        _catr("Rédige un email de remerciement", domain="writing", constraints=["100 mots"])
    )
    assert report.decision == "PROCEED"
    assert report.questions == []


def test_ambiguity_asks_on_critical_missing_info() -> None:
    report = AmbiguityEngine().analyze(
        _catr(
            "Truc",
            missing_information=[MissingInformation(label="objectif précis", importance="high")],
            ambiguities=["Intention très courte, peu de détails."],
        )
    )
    assert report.decision == "ASK"
    assert 1 <= len(report.questions) <= 3
    assert "objectif précis" in report.questions[0]


def test_ambiguity_asks_on_contradiction() -> None:
    report = AmbiguityEngine().analyze(
        _catr("Rédige un texte", constraints=["en français", "in english"])
    )
    assert report.decision == "ASK"
    assert any("contredisent" in q for q in report.questions)


def test_ambiguity_proceeds_when_only_important() -> None:
    report = AmbiguityEngine().analyze(
        _catr(
            "Analyse",
            missing_information=[
                MissingInformation(label="longueur et format", importance="medium")
            ],
        )
    )
    assert report.decision == "PROCEED"  # IMPORTANT alone never forces a question
    assert report.findings  # but it is surfaced


# ── Complexity ────────────────────────────────────────────────────────────────────
def test_complexity_simple() -> None:
    assert ComplexityEngine().assess(_catr("Dire bonjour", domain="general")).level == "simple"


def test_complexity_moderate() -> None:
    catr = _catr(
        "Implémente une fonction de connexion utilisateur",
        domain="software",
        sub_goals=["valider l'entrée", "hacher le mot de passe"],
    )
    assert ComplexityEngine().assess(catr).level == "moderate"


def test_complexity_complex() -> None:
    catr = _catr(
        "Analyse le jeu de données clients et produis un rapport complet avec visualisations "
        "et recommandations stratégiques détaillées",
        domain="data",
        sub_goals=["nettoyer les données", "agréger par région", "générer les visualisations"],
    )
    assert ComplexityEngine().assess(catr).level == "complex"


def test_complexity_agentic() -> None:
    catr = _catr(
        "Construis un agent de support",
        domain="software",
        sub_goals=[
            "lire le ticket",
            "chercher la doc",
            "rédiger la réponse",
            "escalader si besoin",
        ],
        inputs=["tickets.csv"],
    )
    assert ComplexityEngine().assess(catr).level == "agentic"


def test_complexity_agentic_from_tool_language() -> None:
    # No inputs, but explicit agentic/tool language + 4 sub-goals → agentic.
    catr = _catr(
        "Construis un agent de support",
        domain="writing",
        sub_goals=["lire le ticket", "chercher la doc", "rédiger la réponse", "escalade si besoin"],
    )
    assert ComplexityEngine().assess(catr).level == "agentic"


# ── Strategy ──────────────────────────────────────────────────────────────────────
def test_strategy_single_for_simple() -> None:
    s = StrategyEngine().decide(_catr("Dis bonjour"), _assessment("simple", 0.1))
    assert s.kind == "single"


def test_strategy_rag_when_source_present() -> None:
    s = StrategyEngine().decide(
        _catr("Réponds à partir du document", inputs=["manuel.pdf"]), _assessment("moderate", 0.5)
    )
    assert s.kind == "rag"


def test_strategy_chain_for_multistep() -> None:
    s = StrategyEngine().decide(
        _catr("Refactore le module", sub_goals=["a", "b", "c"]), _assessment("complex", 0.8)
    )
    assert s.kind == "chain"


def test_strategy_guardrail_no_escalation_when_simple() -> None:
    # Simple + no external source ⇒ single, even with several sub-goals.
    s = StrategyEngine().decide(
        _catr("Petite tâche", sub_goals=["a", "b", "c"]), _assessment("simple", 0.2)
    )
    assert s.kind == "single"


# ── Router ────────────────────────────────────────────────────────────────────────
def test_router_simple_picks_cheap_fast_model() -> None:
    route = ModelRouter().route(
        _catr("x"), Strategy(kind="single", rationale=""), _assessment("simple", 0.1)
    )
    assert route.primary == "gpt-4o-mini"
    assert route.fallbacks  # others offered as fallback


def test_router_complex_picks_advanced_with_fallback() -> None:
    route = ModelRouter().route(
        _catr("x"), Strategy(kind="chain", rationale=""), _assessment("complex", 0.8)
    )
    assert route.primary == "claude-sonnet-5-5"
    assert "gpt-4o" in route.fallbacks
    assert "gpt-4o-mini" not in route.fallbacks  # filtered out: reasoning too low


def test_router_agentic_requires_frontier_and_tools() -> None:
    route = ModelRouter().route(
        _catr("x"), Strategy(kind="chain", rationale=""), _assessment("agentic", 0.9)
    )
    assert route.primary == "claude-sonnet-5-5"
    assert "tools" in route.required_capabilities


def test_router_reads_capabilities_from_registry_vision() -> None:
    # Capability is DATA: a model lacking vision is excluded when vision is required.
    registry = [
        ModelCapability(
            model="novision",
            provider="p",
            context_window=200000,
            supports_tools=True,
            supports_vision=False,
            structured_output=True,
            reasoning_strength="frontier",
            cost_in=0.1,
            cost_out=0.1,
            latency_ms=100,
            last_verified=date(2026, 1, 1),
        ),
        ModelCapability(
            model="withvision",
            provider="p",
            context_window=200000,
            supports_tools=True,
            supports_vision=True,
            structured_output=True,
            reasoning_strength="frontier",
            cost_in=5.0,
            cost_out=5.0,
            latency_ms=900,
            last_verified=date(2026, 1, 1),
        ),
    ]
    catr = _catr("Décris l'image", inputs=["photo.png"])
    route = ModelRouter(registry).route(
        catr, Strategy(kind="single", rationale=""), _assessment("simple", 0.1)
    )
    assert "vision" in route.required_capabilities
    assert route.primary == "withvision"  # the cheaper no-vision model is excluded
    assert "novision" not in route.fallbacks


def test_router_returns_none_when_nothing_qualifies() -> None:
    registry = [
        ModelCapability(
            model="weak",
            provider="p",
            context_window=4000,
            supports_tools=False,
            supports_vision=False,
            structured_output=False,
            reasoning_strength="basic",
            cost_in=0.1,
            cost_out=0.1,
            latency_ms=100,
            last_verified=date(2026, 1, 1),
        )
    ]
    route = ModelRouter(registry).route(
        _catr("x"), Strategy(kind="rag", rationale=""), _assessment("agentic", 0.9)
    )
    assert route.primary is None


def test_default_registry_is_cached() -> None:
    assert default_registry() is default_registry()
