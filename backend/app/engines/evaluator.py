"""Evaluator v1 — a deterministic, MEASURED evaluation of an execution output.

Produces an ``EvaluationReport``: explicit, weighted criteria, each scored in [0, 1] with
the evidence behind it, plus a weighted overall score. This is a real measurement (a
reproducible heuristic proxy, ``method="rules-v1"`` — NOT an LLM judge), which is exactly
what lets a downstream consumer give a quality verdict (the version diff cannot, because
it has no measurement). See the ``kompilo-pipeline`` skill.
"""

from __future__ import annotations

import re

from app.schemas.catr import CanonicalAITask
from app.schemas.evaluate import EvaluationCriterion, EvaluationReport
from app.schemas.verify import VerificationReport

_WORD_RE = re.compile(r"[a-zà-ÿ0-9]{4,}", re.IGNORECASE)
# A small bilingual stopword set so "coverage" is about meaningful terms, not glue words.
_STOP = {
    "dans",
    "pour",
    "avec",
    "sans",
    "cette",
    "votre",
    "notre",
    "leur",
    "elle",
    "nous",
    "vous",
    "être",
    "fait",
    "plus",
    "tout",
    "tous",
    "that",
    "this",
    "with",
    "from",
    "your",
    "their",
    "which",
    "about",
    "into",
    "will",
    "should",
    "would",
}
_MIN_USEFUL_CHARS = 20


def _keywords(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text) if w.lower() not in _STOP}


def _coverage(reference: str, output_words: set[str]) -> tuple[float, int, int]:
    """Fraction of the reference's keywords present in the output (found, total)."""
    ref = _keywords(reference)
    if not ref:
        return 1.0, 0, 0
    found = len(ref & output_words)
    return found / len(ref), found, len(ref)


class Evaluator:
    def evaluate(
        self,
        output: str,
        *,
        catr: CanonicalAITask,
        verification: VerificationReport,
        quality_contract: list[str] | None = None,
    ) -> EvaluationReport:
        quality_contract = quality_contract or []
        out = output.strip()
        out_words = _keywords(out)
        criteria: list[EvaluationCriterion] = []

        # 1. Format valid (critical) — from the Verifier.
        criteria.append(
            EvaluationCriterion(
                name="format_valid",
                passed=verification.valid,
                score=1.0 if verification.valid else 0.0,
                weight=1.0,
                detail=verification.summary,
            )
        )

        # 2. Non-empty / substantive (critical).
        non_empty = bool(out)
        substantive = len(out) >= _MIN_USEFUL_CHARS
        criteria.append(
            EvaluationCriterion(
                name="non_empty",
                passed=non_empty,
                score=1.0 if substantive else (0.5 if non_empty else 0.0),
                weight=0.5,
                detail=f"{len(out)} caractère(s) de sortie",
            )
        )

        # 3. Objective coverage — are the objective's key terms reflected in the output?
        cov, found, total = _coverage(catr.objective, out_words)
        criteria.append(
            EvaluationCriterion(
                name="objective_coverage",
                passed=cov >= 0.3 or total == 0,
                score=round(cov, 3),
                weight=1.0,
                detail=(
                    f"{found}/{total} terme(s) clé(s) de l'objectif présent(s)"
                    if total
                    else "objectif sans terme clé mesurable"
                ),
            )
        )

        # 4. Constraints adherence — each constraint's keywords should appear somewhere.
        constraints = [*catr.constraints, *quality_contract]
        if constraints:
            satisfied = sum(1 for c in constraints if _keywords(c) & out_words or not _keywords(c))
            frac = satisfied / len(constraints)
            criteria.append(
                EvaluationCriterion(
                    name="constraints_adherence",
                    passed=frac >= 0.5,
                    score=round(frac, 3),
                    weight=1.0,
                    detail=f"{satisfied}/{len(constraints)} contrainte(s) reflétée(s)",
                )
            )

        total_w = sum(c.weight for c in criteria) or 1.0
        score = round(sum(c.score * c.weight for c in criteria) / total_w, 3)
        # "passed" is gated on the CRITICAL criteria only (format + non-empty).
        critical = {"format_valid", "non_empty"}
        passed = all(c.passed for c in criteria if c.name in critical)
        summary = (
            f"score mesuré {score:.2f} ({'conforme' if passed else 'non conforme'}) "
            f"sur {len(criteria)} critère(s) — heuristique rules-v1"
        )
        return EvaluationReport(score=score, passed=passed, criteria=criteria, summary=summary)
