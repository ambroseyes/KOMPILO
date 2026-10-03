"""Strategy Engine v1 — pick single / chain / rag from a CATR + complexity.

Clear, rule-based decision with a recorded rationale and the signals that fired.
Guardrail: never escalate to a heavier strategy when a simpler one suffices — an
escalation must be justified by an explicit signal (retrieval sources, or genuine
multi-step complexity), and a ``simple`` task without a retrieval source stays ``single``.
"""

from __future__ import annotations

import re

from app.schemas.catr import CanonicalAITask
from app.schemas.strategize import ComplexityAssessment, Strategy, StrategyKind

_FILE_RE = re.compile(r"\.(?:csv|json|txt|xlsx|pdf|md|parquet|sql|ya?ml|docx?)$", re.I)
_PROVIDED_MARKERS = ("provided content", "contenu fourni", "the following", "ci-dessous")


def _looks_like_source(item: str) -> bool:
    low = item.lower()
    return (
        low.startswith("http")
        or bool(_FILE_RE.search(item.strip()))
        or any(marker in low for marker in _PROVIDED_MARKERS)
    )


def _has_retrieval_signal(catr: CanonicalAITask) -> bool:
    # A real external source to ground on — never invented; only from CATR inputs.
    return any(_looks_like_source(i) for i in catr.inputs)


class StrategyEngine:
    """Rule-based strategy selection (v1)."""

    def decide(self, catr: CanonicalAITask, complexity: ComplexityAssessment) -> Strategy:
        retrieval = _has_retrieval_signal(catr)
        multi_step = complexity.level in {"complex", "agentic"} or len(catr.sub_goals) >= 3
        signals: list[str] = [f"complexity={complexity.level}"]
        if retrieval:
            signals.append("retrieval_source_present")
        if multi_step:
            signals.append("multi_step")

        # Guardrail: a simple task with no external source to consult stays single.
        if complexity.level == "simple" and not retrieval:
            return Strategy(
                kind="single",
                rationale="Simple task with no external source; a single call suffices.",
                signals=signals,
            )

        kind: StrategyKind
        if retrieval:
            kind = "rag"
            rationale = (
                "External source(s) referenced in the inputs — ground the answer via retrieval."
            )
        elif multi_step:
            kind = "chain"
            rationale = (
                "Multi-step work (complex/agentic or ≥3 sub-goals) — decompose into a chain."
            )
        else:
            kind = "single"
            rationale = (
                "Single objective, no retrieval source and not multi-step — a single call suffices."
            )

        return Strategy(kind=kind, rationale=rationale, signals=signals)
