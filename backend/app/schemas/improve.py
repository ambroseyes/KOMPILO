"""Improve-stage schemas — concrete, GROUNDED suggestions (never hallucinated).

Each improvement is derived from a named signal already produced by the pipeline (a weak
diagnostic axis, a failed evaluation criterion, missing information, or a residual
ambiguity) and carries that provenance in ``derived_from``. See ``engines/improver.py``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Improvement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str  # what to improve, e.g. "constraints", "expected_output", "objective"
    suggestion: str  # the concrete action
    rationale: str  # why it helps
    derived_from: str  # provenance, e.g. "diagnostic:specificity", "eval:format_valid"


class ImprovementReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    improvements: list[Improvement]
    method: str = "rules-v1"
    summary: str
