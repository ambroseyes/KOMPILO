"""Unit tests for the adversarial review (deterministic; no DB, no LLM).

A bare prompt raises the expected findings; a well-specified one clears them; the vague-
term, decision-criteria and forced-chain-of-thought rules fire only when they should.
"""

from __future__ import annotations

from datetime import date

from app.engines.prompt_review import review
from app.schemas.catr import CanonicalAITask, CatrMeta
from app.schemas.registry import ModelCapability


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


def _kinds(catr: CanonicalAITask, text: str, sections: list[str], **kw: object) -> set[str]:
    findings = review(
        catr=catr,
        prompt_text=text,
        section_names=sections,
        profile=kw.get("profile", _profile()),  # type: ignore[arg-type]
        output_format=kw.get("output_format", "markdown"),  # type: ignore[arg-type]
        quality_contract=kw.get("quality_contract", []),  # type: ignore[arg-type]
    )
    return {f.kind for f in findings}


def test_bare_prompt_raises_the_core_gaps() -> None:
    kinds = _kinds(_catr(), "## Role\nX\n\n## Mission\nY", ["role", "mission"])
    assert {"missing_success_criteria", "missing_validation", "missing_evidence_policy"} <= kinds


def test_well_specified_prompt_clears_those_gaps() -> None:
    catr = _catr(expected_output="Un rapport en 5 sections")
    text = (
        "## Role\nX\n\n## Mission\nY\n\n## Validation\n- vérifie\n\n"
        "## Preuve & incertitude\n- cite les sources, ne pas inventer"
    )
    kinds = _kinds(
        catr,
        text,
        ["role", "mission", "validation"],
        quality_contract=["ajoute des tests"],
    )
    assert "missing_validation" not in kinds
    assert "missing_evidence_policy" not in kinds
    assert "missing_success_criteria" not in kinds


def test_vague_term_and_decision_rules() -> None:
    assert "vague_term" in _kinds(
        _catr(objective="Construis un système temps réel"),
        "## Role\nX\n\n## Mission\nY",
        ["role", "mission"],
    )
    assert "no_decision_criteria" in _kinds(
        _catr(objective="Choisir entre AWS et GCP"),
        "## Role\nX\n\n## Mission\nY",
        ["role", "mission"],
    )


def test_forced_cot_flagged_on_strong_reasoner_only() -> None:
    text = "## Role\nX\n\n## Mission\nY\n\n## Rigor\n- Reason step by step before answering."
    assert "forced_cot_on_reasoner" in _kinds(
        _catr(), text, ["role", "mission"], profile=_profile("frontier")
    )
    assert "forced_cot_on_reasoner" not in _kinds(
        _catr(), text, ["role", "mission"], profile=_profile("medium")
    )
