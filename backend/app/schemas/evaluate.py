"""Evaluate-stage schemas — a MEASURED, explainable evaluation of an output.

Unlike the version diff (which refuses a quality verdict because it has no measurement),
the Evaluator produces a real, reproducible measurement: explicit, weighted criteria each
with a score and the evidence behind it. ``method="rules-v1"`` makes clear it is a
deterministic heuristic proxy, not an LLM judge. See ``engines/evaluator.py``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EvaluationCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    passed: bool
    score: float = Field(..., ge=0.0, le=1.0)
    weight: float = Field(..., ge=0.0)
    detail: str  # the evidence behind the score


class EvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # A real, weighted measurement in [0, 1] — reproducible from the criteria below.
    score: float = Field(..., ge=0.0, le=1.0)
    passed: bool  # all critical criteria passed
    criteria: list[EvaluationCriterion]
    method: str = "rules-v1"  # deterministic heuristic proxy, NOT an LLM judge
    measured: bool = True  # explicit: this is a measurement, so a verdict is allowed
    summary: str
