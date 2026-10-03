"""Complexity Engine v1 — classify a CATR as simple / moderate / complex / agentic.

Rules + thresholds over transparent, normalized features (length, domain weight, tool
signal, number of sub-goals). Deterministic and explainable (the ``features`` are
returned alongside the level).

STUB: a learned PyTorch complexity model will replace the rule-based scorer later; see
``_ml_complexity_stub`` below. v1 is rules-only (``method == "rules-v1"``).
"""

from __future__ import annotations

from app.schemas.catr import CanonicalAITask
from app.schemas.strategize import ComplexityAssessment, ComplexityLevel

# Per-domain base complexity weight (0..1). Read here, not scattered through the code.
_DOMAIN_WEIGHT: dict[str, float] = {
    "software": 0.8,
    "data": 0.9,
    "product": 0.6,
    "writing": 0.4,
    "general": 0.3,
}

# Feature weights for the composite score (sum to 1.0).
_W_LENGTH = 0.25
_W_SUBGOALS = 0.30
_W_DOMAIN = 0.25
_W_TOOLS = 0.20

# Score thresholds → level.
_T_SIMPLE = 0.25
_T_MODERATE = 0.50
_T_COMPLEX = 0.75


def _ml_complexity_stub(catr: CanonicalAITask) -> ComplexityLevel | None:
    """STUB — future PyTorch complexity classifier. Not implemented in v1.

    Kept as an explicit seam so the rule-based path can be swapped for a learned model
    behind the same engine without touching callers. Returns ``None`` (not available).
    """
    return None


# Language that implies tool use / agentic orchestration (beyond inputs/domain).
_TOOL_WORDS: tuple[str, ...] = (
    "agent",
    "agentic",
    "outil",
    "outils",
    "tool",
    "tools",
    "orchestr",
    "workflow",
    "pipeline",
    "automatise",
    "automate",
    "escalade",
    "escalate",
    "scrape",
    "crawl",
)


def _tool_signal(catr: CanonicalAITask) -> float:
    # Tools/retrieval are implied by external inputs, software/data work, OR explicit
    # tool/agentic language in the objective and sub-goals.
    if catr.inputs:
        return 1.0
    if catr.domain in {"software", "data"}:
        return 1.0
    hay = " ".join([catr.objective, *catr.sub_goals]).lower()
    return 1.0 if any(word in hay for word in _TOOL_WORDS) else 0.0


class ComplexityEngine:
    """Rule-based complexity assessment (v1)."""

    def assess(self, catr: CanonicalAITask) -> ComplexityAssessment:
        word_count = len(catr.objective.split()) + sum(len(g.split()) for g in catr.sub_goals)
        num_sub_goals = len(catr.sub_goals)

        features = {
            "length": round(min(word_count / 40.0, 1.0), 3),
            "sub_goals": round(min(num_sub_goals / 5.0, 1.0), 3),
            "domain_weight": _DOMAIN_WEIGHT.get(catr.domain, 0.3),
            "tools": _tool_signal(catr),
        }
        score = round(
            _W_LENGTH * features["length"]
            + _W_SUBGOALS * features["sub_goals"]
            + _W_DOMAIN * features["domain_weight"]
            + _W_TOOLS * features["tools"],
            3,
        )

        # Agentic override: genuinely multi-step work that also needs tools.
        if num_sub_goals >= 4 and features["tools"] >= 1.0:
            level: ComplexityLevel = "agentic"
        elif score >= _T_COMPLEX:
            level = "complex"
        elif score >= _T_MODERATE:
            level = "moderate"
        elif score >= _T_SIMPLE:
            level = "moderate" if num_sub_goals >= 3 else "simple"
        else:
            level = "simple"

        return ComplexityAssessment(level=level, score=score, features=features, method="rules-v1")
