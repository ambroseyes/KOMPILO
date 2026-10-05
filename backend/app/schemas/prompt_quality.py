"""Schemas for the Prompt Quality block (PPOA steps 15-17): adversarial review,
Prompt Quality Score (PQS) and deterministic prompt repair.

Design note — reconciling two conventions on purpose:
  * Kompilo's OUTPUT diagnostic (``DiagnosticEngine``) deliberately exposes NO single
    score — strengths/weaknesses are named per axis. That stays untouched.
  * The PQS here is a DIFFERENT object: a *readiness* score of the compiled PROMPT
    SPECIFICATION, which both source specs explicitly call for ("This is not a truth
    score; it is a readiness score"). It keeps the per-axis explainability (every
    dimension carries a level + reason + recommendation, like the diagnostic) AND adds
    the weighted composite the specs require, clearly labelled as readiness — never a
    prediction that the answer will be correct.

Kept decoupled from ``schemas.compile`` (no import from it) so ``CompileResponse`` can
embed a ``PromptQualityReport`` without a circular import.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReadinessLevel = Literal["low", "medium", "high"]
PqsBand = Literal["insufficient", "usable", "strong", "execution_ready"]
FindingSeverity = Literal["low", "medium", "high"]

# Band thresholds (Framework §18) and the release gate (CDC Appendix C). These are
# STARTING points to recalibrate on real evaluation data after deployment — not laws.
BAND_USABLE = 60
BAND_STRONG = 75
BAND_EXECUTION_READY = 90
RELEASE_GATE = 85


class PqsDimension(BaseModel):
    """One weighted axis of the PQS, explainable on its own (like a diagnostic axis)."""

    model_config = ConfigDict(extra="forbid")

    dimension: str  # machine key, e.g. "evidence_discipline"
    label: str  # human label (French)
    weight: int  # points this axis contributes at score 1.0 (all weights sum to 100)
    score: float = Field(..., ge=0.0, le=1.0)
    points: float  # round(weight * score, 2) — this axis' contribution to the composite
    level: ReadinessLevel
    detail: str
    reason: str | None = None  # why it is weak (set when level != "high")
    recommendation: str | None = None  # corrective action (set when level != "high")


class AdversarialFinding(BaseModel):
    """A concrete weakness the adversarial review raised about the compiled prompt."""

    model_config = ConfigDict(extra="forbid")

    kind: str  # machine key, e.g. "missing_validation"
    severity: FindingSeverity
    label: str  # human label (French)
    detail: str
    recommendation: str


class PromptRepairResult(BaseModel):
    """Result of the deterministic repair loop over the compiled prompt."""

    model_config = ConfigDict(extra="forbid")

    applied: bool  # whether any structural change was made
    pqs_before: int
    pqs_after: int
    iterations: int
    converged: bool  # stopped because the gate was reached or no further gain
    changes: list[str] = Field(default_factory=list)  # human-readable fixes applied
    repaired_prompt: str  # the improved prompt text (empty string when nothing changed)
    note: str


class PromptQualityReport(BaseModel):
    """PQS + adversarial findings + repair for one compiled prompt."""

    model_config = ConfigDict(extra="forbid")

    pqs: int = Field(..., ge=0, le=100)  # composite READINESS score (not a truth score)
    band: PqsBand
    gate_passed: bool  # pqs >= RELEASE_GATE
    dimensions: list[PqsDimension]
    findings: list[AdversarialFinding]
    repair: PromptRepairResult | None
    summary: str
    note: str
