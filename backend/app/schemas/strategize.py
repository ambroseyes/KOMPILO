"""Strategize-stage outputs (consume a CATR): ambiguity, complexity, strategy, route.

All strictly typed (``extra="forbid"``). These are the deterministic, rule-based v1
engine outputs; none of them invent missing information — gaps are surfaced, not filled.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ── Ambiguity ────────────────────────────────────────────────────────────────────
Severity = Literal["CRITICAL", "IMPORTANT", "OPTIONAL"]
Decision = Literal["ASK", "PROCEED"]
AmbiguityKind = Literal["vague_term", "contradiction", "missing_information"]


class AmbiguityFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: AmbiguityKind
    severity: Severity
    detail: str


class AmbiguityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Decision
    # 1..3 targeted questions, present ONLY when decision == "ASK".
    questions: list[str] = Field(default_factory=list)
    findings: list[AmbiguityFinding] = Field(default_factory=list)


# ── Complexity ───────────────────────────────────────────────────────────────────
ComplexityLevel = Literal["simple", "moderate", "complex", "agentic"]


class ComplexityAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: ComplexityLevel
    score: float = Field(..., ge=0.0, le=1.0)
    features: dict[str, float]  # transparent, normalized feature values
    method: str  # "rules-v1" (the learned PyTorch backend is a future STUB)


# ── Strategy ─────────────────────────────────────────────────────────────────────
StrategyKind = Literal["single", "chain", "rag"]


class Strategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: StrategyKind
    rationale: str
    signals: list[str] = Field(default_factory=list)  # what drove the choice


# ── Routing ──────────────────────────────────────────────────────────────────────
class RouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: str | None  # chosen model id, or None when nothing qualifies
    fallbacks: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    rationale: str


# ── Aggregate (the strategize stage's output) ────────────────────────────────────
class StrategizeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ambiguity: AmbiguityReport
    complexity: ComplexityAssessment
    strategy: Strategy
    route: RouteDecision
