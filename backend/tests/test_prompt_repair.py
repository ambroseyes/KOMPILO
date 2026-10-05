"""Unit tests for the deterministic prompt repair (no DB, no LLM).

A sub-gate prompt is enriched and its PQS rises; repair only keeps gaining changes; it is
idempotent once the structural fixes are present; a forced chain-of-thought is removed.
"""

from __future__ import annotations

from datetime import date

from app.engines.prompt_repair import repair
from app.schemas.catr import CanonicalAITask, CatrMeta
from app.schemas.registry import ModelCapability
from app.schemas.strategize import AmbiguityReport, ComplexityAssessment, RouteDecision


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


def _repair(text: str, sections: list[str], **kw: object):
    return repair(
        catr=kw.get("catr", _catr()),  # type: ignore[arg-type]
        base_prompt_text=text,
        section_names=sections,
        route=RouteDecision(
            primary="gpt-4o", fallbacks=[], required_capabilities=[], rationale="t"
        ),
        complexity=ComplexityAssessment(
            level="moderate", score=0.5, features={}, method="rules-v1"
        ),
        profile=kw.get("profile", _profile()),  # type: ignore[arg-type]
        ambiguity=AmbiguityReport(decision="PROCEED", questions=[], findings=[]),
        output_format="markdown",
        quality_contract=[],
    )


def test_repair_enriches_and_raises_pqs() -> None:
    res = _repair("## Role\nExpert.\n\n## Mission\nRédige la politique.", ["role", "mission"])
    assert res.applied is True
    assert res.pqs_after > res.pqs_before
    assert any("preuve" in c.lower() for c in res.changes)
    assert any("validation" in c.lower() for c in res.changes)
    assert "Preuve & incertitude" in res.repaired_prompt
    assert "## Validation" in res.repaired_prompt


def test_repair_is_idempotent_when_fixes_already_present() -> None:
    text = (
        "## Role\nExpert.\n\n## Mission\nY.\n\n## Validation\n- vérifie\n\n"
        "## Preuve & incertitude\n- cite les sources, ne pas inventer"
    )
    res = _repair(text, ["role", "mission", "validation"])
    # Evidence + validation already there → no structural change to add.
    assert not any("preuve" in c.lower() for c in res.changes)
    assert not any("Ajout d'un bloc de validation" == c for c in res.changes)


def test_repair_removes_forced_cot_on_strong_reasoner() -> None:
    text = (
        "## Role\nX\n\n## Mission\nY\n\n## Rigor\n"
        "Reason step by step before answering; state assumptions explicitly."
    )
    res = _repair(text, ["role", "mission"], profile=_profile("frontier"))
    assert res.applied is True
    assert "step by step" not in res.repaired_prompt.lower()
    assert res.converged == (res.pqs_after >= 85)
