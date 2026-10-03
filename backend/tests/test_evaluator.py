"""Unit tests for the Evaluator (deterministic, measured — no DB, no LLM)."""

from __future__ import annotations

from app.engines.evaluator import Evaluator
from app.schemas.catr import CanonicalAITask, CatrMeta
from app.schemas.verify import VerificationReport


def _catr(**over: object) -> CanonicalAITask:
    base: dict[str, object] = {
        "objective": "Rédiger un message de bienvenue chaleureux pour un nouveau client",
        "domain": "writing",
        "complexity": "medium",
        "risk": "low",
        "meta": CatrMeta(method="heuristic-v1", confidence=0.8, enriched_by_llm=False),
    }
    base.update(over)
    return CanonicalAITask(**base)  # type: ignore[arg-type]


def _ok_verif() -> VerificationReport:
    return VerificationReport(valid=True, format="markdown", issues=[], summary="OK")


def _bad_verif() -> VerificationReport:
    return VerificationReport(valid=False, format="json", issues=[], summary="invalid JSON")


def test_good_output_scores_high_and_passes() -> None:
    out = "Bienvenue chaleureux ! Merci de rejoindre notre service, cher nouveau client."
    report = Evaluator().evaluate(out, catr=_catr(), verification=_ok_verif())
    assert report.measured is True and report.method == "rules-v1"
    assert report.passed is True
    assert 0.0 <= report.score <= 1.0 and report.score > 0.5
    names = {c.name for c in report.criteria}
    assert {"format_valid", "non_empty", "objective_coverage"} <= names


def test_invalid_format_fails_critical() -> None:
    report = Evaluator().evaluate('{"x": 1', catr=_catr(), verification=_bad_verif())
    fmt = next(c for c in report.criteria if c.name == "format_valid")
    assert fmt.passed is False and fmt.score == 0.0
    assert report.passed is False  # a critical criterion failed


def test_empty_output_fails() -> None:
    report = Evaluator().evaluate("   ", catr=_catr(), verification=_ok_verif())
    non_empty = next(c for c in report.criteria if c.name == "non_empty")
    assert non_empty.passed is False
    assert report.passed is False


def test_constraints_criterion_present_when_constraints_exist() -> None:
    catr = _catr(constraints=["Ton chaleureux", "Maximum 50 mots"])
    report = Evaluator().evaluate(
        "Un message chaleureux de bienvenue.", catr=catr, verification=_ok_verif()
    )
    assert any(c.name == "constraints_adherence" for c in report.criteria)


def test_score_is_reproducible() -> None:
    out = "Bienvenue ! Merci de rejoindre notre service."
    a = Evaluator().evaluate(out, catr=_catr(), verification=_ok_verif())
    b = Evaluator().evaluate(out, catr=_catr(), verification=_ok_verif())
    assert a.score == b.score  # deterministic
