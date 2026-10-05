"""Unit tests for the Prompt Quality Score (deterministic; no DB, no LLM).

Pin the boundaries: the weights total 100, the composite stays in [0, 100], a well-
specified prompt scores strictly higher than a bare one, every weak axis explains itself,
and the shared signal helpers behave (evidence policy, vague terms, output contract,
forced chain-of-thought).
"""

from __future__ import annotations

from datetime import date

from app.engines.prompt_scorer import (
    WEIGHTS,
    composite,
    forced_cot,
    has_evidence_policy,
    output_contract_ok,
    score_dimensions,
    vague_terms,
)
from app.schemas.catr import CanonicalAITask, CatrMeta
from app.schemas.registry import ModelCapability
from app.schemas.strategize import (
    AmbiguityFinding,
    AmbiguityReport,
    ComplexityAssessment,
    RouteDecision,
)


def _catr(**kw: object) -> CanonicalAITask:
    base: dict[str, object] = dict(
        objective="Rédige une politique de sécurité réseau pour une PME",
        sub_goals=[],
        domain="general",
        inputs=[],
        context=[],
        constraints=[],
        expected_output=None,
        audience=None,
        complexity="medium",
        missing_information=[],
        ambiguities=[],
        risk="low",
        meta=CatrMeta(method="heuristic-v1", confidence=0.9, enriched_by_llm=False),
    )
    base.update(kw)
    return CanonicalAITask(**base)  # type: ignore[arg-type]


def _complexity(level: str = "moderate") -> ComplexityAssessment:
    return ComplexityAssessment(level=level, score=0.5, features={}, method="rules-v1")  # type: ignore[arg-type]


def _route(primary: str | None = "gpt-4o") -> RouteDecision:
    return RouteDecision(primary=primary, fallbacks=[], required_capabilities=[], rationale="t")


def _ambiguity(findings: list[AmbiguityFinding] | None = None) -> AmbiguityReport:
    return AmbiguityReport(decision="PROCEED", questions=[], findings=findings or [])


def _profile(strength: str = "advanced") -> ModelCapability:
    return ModelCapability(
        model="gpt-4o",
        provider="openai",
        context_window=128_000,
        supports_tools=True,
        supports_vision=True,
        structured_output=True,
        reasoning_strength=strength,  # type: ignore[arg-type]
        cost_in=2.5,
        cost_out=10.0,
        latency_ms=800,
        last_verified=date(2026, 10, 2),
    )


def _score(catr: CanonicalAITask, text: str, sections: list[str], qc: list[str] | None = None):
    dims = score_dimensions(
        catr=catr,
        prompt_text=text,
        section_names=sections,
        route=_route(),
        complexity=_complexity(),
        profile=_profile(),
        ambiguity=_ambiguity(),
        output_format="markdown",
        quality_contract=qc or [],
    )
    return dims, composite(dims)


def test_weights_sum_to_100() -> None:
    assert sum(WEIGHTS.values()) == 100


def test_eleven_axes_each_explainable_and_bounded() -> None:
    dims, (pqs, band, gate) = _score(_catr(), "## Role\nX\n\n## Mission\nY", ["role", "mission"])
    assert len(dims) == len(WEIGHTS) == 11
    assert 0 <= pqs <= 100
    assert band in {"insufficient", "usable", "strong", "execution_ready"}
    for d in dims:
        assert 0.0 <= d.score <= 1.0
        assert d.level in {"low", "medium", "high"}
        assert d.label
        if d.level != "high":  # a weak axis always explains itself + proposes a fix
            assert d.reason and d.recommendation


def test_well_specified_prompt_outscores_a_bare_one() -> None:
    _, (bare_pqs, bare_band, bare_gate) = _score(
        _catr(), "## Role\nX\n\n## Mission\nY", ["role", "mission"]
    )
    rich_catr = _catr(
        constraints=["Conforme RGPD", "Livrable en 16 semaines"],
        context=["Charte interne de l'entreprise"],
        sub_goals=["Analyser l'existant", "Rédiger les règles"],
        expected_output="Un rapport structuré en 5 sections",
        risk="medium",
    )
    rich_text = (
        "## Role\nX\n\n## Mission\nY\n\n## Validation\n- vérifie les règles\n\n"
        "## Preuve & incertitude\n- cite les sources, ne pas inventer"
    )
    rich_sections = ["role", "mission", "context", "constraints", "output_format", "validation"]
    _, (rich_pqs, rich_band, rich_gate) = _score(
        rich_catr, rich_text, rich_sections, qc=["cite les sources", "ajoute des tests"]
    )
    assert rich_pqs > bare_pqs
    assert bare_band in {"insufficient", "usable"}
    assert bare_gate is False  # a bare prompt never clears the release gate


def test_has_evidence_policy_detects_uncertainty_language() -> None:
    assert has_evidence_policy("Distingue les faits des hypothèses et cite la source.")
    assert not has_evidence_policy("## Role\nExpert.\n## Mission\nFais la tâche.")


def test_vague_terms_flagged_only_without_a_number() -> None:
    assert "temps réel" in vague_terms(_catr(objective="Construis un pipeline temps réel"))
    # A measurable definition nearby (a digit) counts as operationalized.
    assert vague_terms(_catr(objective="Pipeline temps réel: latence < 100 ms")) == []


def test_output_contract_and_forced_cot_helpers() -> None:
    assert output_contract_ok(_catr(expected_output="un JSON"), "markdown")
    assert output_contract_ok(_catr(), "json")
    assert not output_contract_ok(_catr(), "markdown")
    assert forced_cot(_profile("frontier"), "Reason step by step before answering.")
    assert not forced_cot(_profile("medium"), "Reason step by step before answering.")
