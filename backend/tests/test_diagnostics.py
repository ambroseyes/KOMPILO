"""Unit tests for the Diagnostic Engine (8 explainable axes, no single score)."""

from __future__ import annotations

from app.engines.diagnostics import DiagnosticEngine
from app.schemas.catr import CanonicalAITask, CatrMeta, MissingInformation
from app.schemas.strategize import (
    AmbiguityFinding,
    AmbiguityReport,
    ComplexityAssessment,
    RouteDecision,
    Strategy,
)

EXPECTED_AXES = {
    "clarity",
    "completeness",
    "specificity",
    "robustness",
    "executability",
    "context_quality",
    "output_definition",
    "ambiguity_handling",
}


def _catr(**overrides: object) -> CanonicalAITask:
    base: dict[str, object] = {
        "objective": "Écrire un script",
        "domain": "software",
        "complexity": "medium",
        "risk": "low",
        "meta": CatrMeta(method="heuristic-v1", confidence=0.8, enriched_by_llm=False),
    }
    base.update(overrides)
    return CanonicalAITask(**base)  # type: ignore[arg-type]


def _ambiguity(
    decision: str = "PROCEED", findings: list[AmbiguityFinding] | None = None
) -> AmbiguityReport:
    return AmbiguityReport(decision=decision, questions=[], findings=findings or [])  # type: ignore[arg-type]


def _complexity(level: str = "simple") -> ComplexityAssessment:
    return ComplexityAssessment(level=level, score=0.2, features={}, method="rules-v1")  # type: ignore[arg-type]


def _by_dim(dims: list) -> dict[str, object]:
    return {d.dimension: d for d in dims}


def test_assess_returns_the_eight_axes() -> None:
    dims = DiagnosticEngine().assess(_catr(), _ambiguity())
    assert {d.dimension for d in dims} == EXPECTED_AXES


def test_weak_axes_carry_reason_and_recommendation_high_do_not() -> None:
    dims = DiagnosticEngine().assess(_catr(), _ambiguity())
    for d in dims:
        if d.level == "high":
            assert d.reason is None and d.recommendation is None
        else:
            assert d.reason and d.recommendation


def test_clarity_low_on_critical_finding() -> None:
    crit = [AmbiguityFinding(kind="missing_information", severity="CRITICAL", detail="x")]
    dims = _by_dim(DiagnosticEngine().assess(_catr(), _ambiguity("ASK", crit)))
    assert dims["clarity"].level == "low"  # type: ignore[attr-defined]


def test_completeness_low_on_high_importance_missing() -> None:
    catr = _catr(missing_information=[MissingInformation(label="langage cible", importance="high")])
    dims = _by_dim(DiagnosticEngine().assess(catr, _ambiguity()))
    assert dims["completeness"].level == "low"  # type: ignore[attr-defined]


def test_specificity_high_when_inputs_constraints_and_output_present() -> None:
    catr = _catr(inputs=["un CSV"], constraints=["< 100 lignes"], expected_output="une fonction")
    dims = _by_dim(DiagnosticEngine().assess(catr, _ambiguity()))
    assert dims["specificity"].level == "high"  # type: ignore[attr-defined]


def test_robustness_tracks_risk_and_guardrails() -> None:
    low = _by_dim(DiagnosticEngine().assess(_catr(risk="low"), _ambiguity()))
    assert low["robustness"].level == "high"  # type: ignore[attr-defined]
    high_bare = _by_dim(DiagnosticEngine().assess(_catr(risk="high"), _ambiguity()))
    assert high_bare["robustness"].level == "low"  # type: ignore[attr-defined]
    high_guard = _by_dim(
        DiagnosticEngine().assess(
            _catr(risk="high", constraints=["valider les entrées et gérer les erreurs"]),
            _ambiguity(),
        )
    )
    assert high_guard["robustness"].level == "medium"  # type: ignore[attr-defined]


def test_executability_reflects_route_availability() -> None:
    # No route (ASK branch) → medium, "à évaluer après clarification".
    none_route = _by_dim(DiagnosticEngine().assess(_catr(), _ambiguity()))
    assert none_route["executability"].level == "medium"  # type: ignore[attr-defined]

    # A resolved primary model on a simple task → high.
    route = RouteDecision(
        primary="gpt-4o-mini", fallbacks=[], required_capabilities=[], rationale=""
    )
    strat = Strategy(kind="single", rationale="", signals=[])
    ok = _by_dim(
        DiagnosticEngine().assess(
            _catr(), _ambiguity(), complexity=_complexity("simple"), strategy=strat, route=route
        )
    )
    assert ok["executability"].level == "high"  # type: ignore[attr-defined]

    # No model qualifies → low.
    empty = RouteDecision(primary=None, fallbacks=[], required_capabilities=["tools"], rationale="")
    none = _by_dim(
        DiagnosticEngine().assess(
            _catr(), _ambiguity(), complexity=_complexity("simple"), strategy=strat, route=empty
        )
    )
    assert none["executability"].level == "low"  # type: ignore[attr-defined]


def test_context_quality_low_for_rag_without_source() -> None:
    rag = Strategy(kind="rag", rationale="", signals=[])
    route = RouteDecision(primary="m", fallbacks=[], required_capabilities=[], rationale="")
    dims = _by_dim(
        DiagnosticEngine().assess(
            _catr(context=[]), _ambiguity(), complexity=_complexity(), strategy=rag, route=route
        )
    )
    assert dims["context_quality"].level == "low"  # type: ignore[attr-defined]


def test_output_definition_and_ambiguity_handling() -> None:
    # No expected_output + markdown → low output_definition.
    dims = _by_dim(DiagnosticEngine().assess(_catr(), _ambiguity()))
    assert dims["output_definition"].level == "low"  # type: ignore[attr-defined]
    # Many residual ambiguities → low ambiguity_handling.
    many = _catr(ambiguities=["a", "b", "c", "d"])
    dims2 = _by_dim(DiagnosticEngine().assess(many, _ambiguity()))
    assert dims2["ambiguity_handling"].level == "low"  # type: ignore[attr-defined]


def test_no_single_aggregate_score() -> None:
    # The diagnostic is a list of axes — there is no scalar score field anywhere.
    dims = DiagnosticEngine().assess(_catr(), _ambiguity())
    for d in dims:
        assert not hasattr(d, "score")
