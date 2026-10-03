"""Unit tests for the Improver (deterministic, grounded — no DB, no LLM)."""

from __future__ import annotations

from app.engines.improver import Improver
from app.schemas.catr import CanonicalAITask, CatrMeta, MissingInformation
from app.schemas.compile import DiagnosticDimension
from app.schemas.evaluate import EvaluationCriterion, EvaluationReport


def _catr(**over: object) -> CanonicalAITask:
    base: dict[str, object] = {
        "objective": "Écrire un email",
        "domain": "writing",
        "complexity": "low",
        "risk": "low",
        "meta": CatrMeta(method="heuristic-v1", confidence=0.8, enriched_by_llm=False),
    }
    base.update(over)
    return CanonicalAITask(**base)  # type: ignore[arg-type]


def _dim(dimension: str, level: str) -> DiagnosticDimension:
    weak = level != "high"
    return DiagnosticDimension(
        dimension=dimension,
        label=dimension,
        level=level,  # type: ignore[arg-type]
        detail="d",
        reason="r" if weak else None,
        recommendation="fais X" if weak else None,
    )


def _eval(passed: bool, criteria: list[EvaluationCriterion]) -> EvaluationReport:
    return EvaluationReport(score=0.5, passed=passed, criteria=criteria, summary="s")


def test_no_signals_yields_no_improvements() -> None:
    report = Improver().suggest(
        catr=_catr(),
        diagnostics=[_dim("clarity", "high")],
        evaluation=_eval(
            True,
            [
                EvaluationCriterion(
                    name="format_valid", passed=True, score=1.0, weight=1.0, detail="ok"
                )
            ],
        ),
    )
    assert report.improvements == []
    assert "aucune" in report.summary.lower()


def test_weak_diagnostic_axis_becomes_an_improvement() -> None:
    report = Improver().suggest(
        catr=_catr(),
        diagnostics=[_dim("specificity", "low"), _dim("clarity", "high")],
        evaluation=_eval(True, []),
    )
    spec = next(i for i in report.improvements if i.target == "specificity")
    assert spec.suggestion == "fais X"
    assert spec.derived_from == "diagnostic:specificity=low"
    # The high axis produces no improvement.
    assert all(i.target != "clarity" for i in report.improvements)


def test_failed_eval_criterion_becomes_an_improvement() -> None:
    crit = [
        EvaluationCriterion(name="format_valid", passed=False, score=0.0, weight=1.0, detail="bad")
    ]
    report = Improver().suggest(catr=_catr(), diagnostics=[], evaluation=_eval(False, crit))
    fmt = next(i for i in report.improvements if i.derived_from == "eval:format_valid")
    assert "format" in fmt.suggestion.lower()


def test_missing_information_and_ambiguities_are_surfaced() -> None:
    catr = _catr(
        missing_information=[MissingInformation(label="langage cible", importance="high")],
        ambiguities=["« court » n'est pas défini"],
    )
    report = Improver().suggest(catr=catr, diagnostics=[], evaluation=_eval(True, []))
    froms = {i.derived_from for i in report.improvements}
    assert "missing_information" in froms and "ambiguity" in froms
    # Every improvement is grounded in a named signal (never invented).
    assert all(i.derived_from for i in report.improvements)
