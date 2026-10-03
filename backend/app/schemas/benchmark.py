"""Schemas for measured version comparison and the auto-improvement loop (V1.5 #1).

These turn Kompilo's existing, honest building blocks into a *verdict backed by numbers*:

- the Evaluator (``rules-v1``) gives a reproducible per-output measurement;
- a shared set of evaluation *cases* lets two prompt versions be scored on the SAME
  yardstick, so a comparison can say which is better, by how much, and where it regressed;
- the Improver's grounded suggestions drive a rewrite→re-measure loop.

Honesty is preserved end to end: with no real provider key the offline Echo STUB produces
the outputs, so every result carries ``provider_is_real`` and a ``note`` — a ranking over
stub outputs is explicitly flagged as not meaningful. ``method="rules-v1"`` throughout: a
deterministic heuristic proxy, never an LLM judge.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.compile import CompileMode
from app.schemas.evaluate import EvaluationCriterion


class EvalCase(BaseModel):
    """One evaluation scenario: a concrete input/task the prompt should handle well."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)
    task: str = Field(..., min_length=1, max_length=10_000)
    output_format: str = Field(default="markdown", max_length=100)


class CaseScore(BaseModel):
    """A single (version|iteration × case) measurement."""

    model_config = ConfigDict(extra="forbid")

    case: str
    score: float = Field(..., ge=0.0, le=1.0)
    passed: bool
    criteria: list[EvaluationCriterion]
    provider_is_real: bool
    output_excerpt: str


class AggregateScore(BaseModel):
    """A version's (or iteration's) measurement aggregated over the case set."""

    model_config = ConfigDict(extra="forbid")

    label: str  # e.g. "v3" or "iteration 2"
    mean_score: float = Field(..., ge=0.0, le=1.0)
    pass_rate: float = Field(..., ge=0.0, le=1.0)
    per_criterion: dict[str, float]  # mean score per criterion name
    cases: list[CaseScore]


# ── Version comparison ───────────────────────────────────────────────────────
class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_version: int = Field(..., ge=1)
    to_version: int = Field(..., ge=1)
    # When empty, a single baseline case is derived from the versions' source_intent.
    cases: list[EvalCase] = Field(default_factory=list, max_length=20)


class CriterionDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    from_score: float
    to_score: float
    delta: float  # to - from (positive = the newer version improved on this criterion)


class CaseRegression(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case: str
    from_score: float
    to_score: float
    delta: float  # negative — the newer version scored lower on this case


class VersionComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_id: uuid.UUID
    from_version: int
    to_version: int
    from_result: AggregateScore
    to_result: AggregateScore
    verdict: str  # "to_better" | "from_better" | "tie"
    margin: float  # to.mean - from.mean
    per_criterion_delta: list[CriterionDelta]
    regressions: list[CaseRegression]
    method: str = "rules-v1"
    provider_is_real: bool
    summary: str
    note: str


# ── Auto-improvement loop ────────────────────────────────────────────────────
class ImprovementLoopRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: str = Field(..., min_length=1, max_length=10_000)
    cases: list[EvalCase] = Field(default_factory=list, max_length=20)
    mode: CompileMode = "professional"
    output_format: str = Field(default="markdown", max_length=100)
    target_model: str | None = None
    quality_contract: list[str] = Field(default_factory=list)
    max_iterations: int = Field(default=3, ge=1, le=6)
    target_score: float = Field(default=0.9, ge=0.0, le=1.0)


class LoopIteration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iteration: int
    mean_score: float = Field(..., ge=0.0, le=1.0)
    pass_rate: float = Field(..., ge=0.0, le=1.0)
    n_improvements: int
    added_contract: list[str]  # grounded quality-contract lines folded in for the NEXT run


class ImprovementLoopResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str  # "succeeded" | "needs_clarification"
    iterations: list[LoopIteration]
    best_iteration: int
    best_score: float
    best_quality_contract: list[str]
    best_compiled_prompt: str | None
    stop_reason: (
        str  # target_reached | converged | no_improvements | max_iterations | needs_clarification
    )
    method: str = "rules-v1"
    provider_is_real: bool
    summary: str
    note: str
