"""CATR — Canonical Analyzed Task Representation (output of the `understand` stage).

The CATR is the structured understanding of a human intent: what the goal is, what
kind of task it is, the entities/inputs/constraints involved, the assumptions made
to fill gaps, the open questions that would block a confident plan, and how success
is judged. It is consumed by the downstream pipeline (strategize/compile/…).

``method`` records HOW the CATR was produced. ``heuristic-v1`` means a deterministic,
rule-based analyzer (NOT an LLM). This marker is intentional: no consumer should
mistake heuristic output for model reasoning. A Claude-backed analyzer would emit a
different ``method`` behind the same schema.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TaskType = Literal[
    "code_generation",
    "data_analysis",
    "writing",
    "qa",
    "planning",
    "other",
]

CatrMethod = Literal["heuristic-v1"]


class Catr(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: CatrMethod = "heuristic-v1"
    goal: str = Field(..., description="Normalized one-line objective.")
    task_type: TaskType
    language: str = Field(
        ..., description="Detected language of the intent (ISO-639-1, best effort)."
    )
    entities: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
