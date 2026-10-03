"""Version comparator — a MEASURED ranking of two prompt versions (V1.5 #1).

The neutral version diff states *what changed*; it refuses a quality verdict because it has
no measurement. This comparator supplies the measurement: it runs each version's compiled
prompt over the SAME set of evaluation cases through the :class:`EvalHarness`, aggregates
the Evaluator's (``rules-v1``) scores, and returns which version is better, by how much,
per criterion, and where the newer version regressed.

It stays honest: a ranking produced over the offline Echo STUB (no real provider key) is
flagged via ``provider_is_real`` and an explicit ``note``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.engines.eval_harness import STUB_NOTE, EvalHarness, aggregate
from app.schemas.benchmark import (
    CaseRegression,
    CriterionDelta,
    EvalCase,
    VersionComparison,
)

# Mean-score gap at or below which the two versions are called a tie (measurement noise).
_TIE_MARGIN = 0.02
# A per-case drop larger than this counts as a regression.
_REGRESSION_EPS = 0.01


class ComparatorError(ValueError):
    """A comparison cannot be run (e.g. no cases and no source_intent to derive one)."""


@dataclass(frozen=True, slots=True)
class VersionUnderTest:
    """The diff-irrelevant projection a comparison needs: the prompt text to execute."""

    version: int
    prompt_text: str  # the compiled prompt (selected render) to execute
    source_intent: str | None


class VersionComparator:
    def __init__(self, harness: EvalHarness | None = None) -> None:
        self._harness = harness or EvalHarness()

    def _resolve_cases(
        self, cases: list[EvalCase], a: VersionUnderTest, b: VersionUnderTest
    ) -> list[EvalCase]:
        if cases:
            return cases
        baseline = (a.source_intent or b.source_intent or "").strip()
        if not baseline:
            raise ComparatorError(
                "No cases provided and neither version has a source_intent to derive one."
            )
        return [EvalCase(name="baseline", task=baseline)]

    async def compare(
        self,
        *,
        prompt_id: uuid.UUID,
        a: VersionUnderTest,
        b: VersionUnderTest,
        cases: list[EvalCase],
        tenant_id: str,
    ) -> VersionComparison:
        resolved = self._resolve_cases(cases, a, b)

        a_scores = []
        b_scores = []
        for case in resolved:
            # One shared yardstick per case: compile it ONCE, score both versions on it.
            case_catr, plan = await self._harness.prepare_case(case)
            a_scores.append(
                await self._harness.measure(
                    compiled_prompt=a.prompt_text,
                    case=case,
                    case_catr=case_catr,
                    plan=plan,
                    tenant_id=tenant_id,
                )
            )
            b_scores.append(
                await self._harness.measure(
                    compiled_prompt=b.prompt_text,
                    case=case,
                    case_catr=case_catr,
                    plan=plan,
                    tenant_id=tenant_id,
                )
            )

        from_agg = aggregate(f"v{a.version}", a_scores)
        to_agg = aggregate(f"v{b.version}", b_scores)
        margin = round(to_agg.mean_score - from_agg.mean_score, 3)
        if abs(margin) <= _TIE_MARGIN:
            verdict = "tie"
        elif margin > 0:
            verdict = "to_better"
        else:
            verdict = "from_better"

        names = sorted(set(from_agg.per_criterion) | set(to_agg.per_criterion))
        per_criterion_delta = [
            CriterionDelta(
                name=name,
                from_score=from_agg.per_criterion.get(name, 0.0),
                to_score=to_agg.per_criterion.get(name, 0.0),
                delta=round(
                    to_agg.per_criterion.get(name, 0.0) - from_agg.per_criterion.get(name, 0.0), 3
                ),
            )
            for name in names
        ]

        regressions = [
            CaseRegression(
                case=fa.case,
                from_score=fa.score,
                to_score=tb.score,
                delta=round(tb.score - fa.score, 3),
            )
            for fa, tb in zip(a_scores, b_scores, strict=True)
            if tb.score < fa.score - _REGRESSION_EPS
        ]

        provider_is_real = any(s.provider_is_real for s in (*a_scores, *b_scores))
        verdict_fr = {
            "to_better": f"v{b.version} est meilleure (+{margin:.2f})",
            "from_better": f"v{a.version} est meilleure ({margin:.2f})",
            "tie": "égalité (écart dans le bruit de mesure)",
        }[verdict]
        summary = (
            f"v{a.version} {from_agg.mean_score:.2f} vs v{b.version} {to_agg.mean_score:.2f} "
            f"sur {len(resolved)} cas — {verdict_fr}"
            + (f", {len(regressions)} régression(s)" if regressions else "")
        )
        note = (
            STUB_NOTE
            if not provider_is_real
            else "Mesure reproductible rules-v1 (proxy heuristique, pas un juge LLM)."
        )

        return VersionComparison(
            prompt_id=prompt_id,
            from_version=a.version,
            to_version=b.version,
            from_result=from_agg,
            to_result=to_agg,
            verdict=verdict,
            margin=margin,
            per_criterion_delta=per_criterion_delta,
            regressions=regressions,
            provider_is_real=provider_is_real,
            summary=summary,
            note=note,
        )
