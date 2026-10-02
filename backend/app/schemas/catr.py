"""CATR — the Canonical AI Task Representation (output of the Intent Engine).

``CanonicalAITask`` is Kompilo's structured, strictly-typed understanding of a human
intent: what to achieve, in which domain, with which inputs/context/constraints, for
whom, how hard/risky it is, and — crucially — what is still MISSING or ambiguous. It
is produced by ``app.engines.intent.IntentEngine`` and consumed by the downstream
pipeline (strategize/compile/…) and stored on ``prompt_versions.catr``.

``meta`` records provenance so no consumer mistakes heuristic output for model
reasoning: ``method`` is ``heuristic-v1`` (rules only) or ``heuristic-v1+llm`` (a light
LLM refined objective/expected_output), and ``enriched_by_llm`` says whether the LLM
was actually called. A partial CATR is valid: optional fields may be empty while the
engine lacks the information (that's what ``missing_information`` is for).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Complexity = Literal["low", "medium", "high"]
Risk = Literal["low", "medium", "high"]
Importance = Literal["low", "medium", "high"]


class MissingInformation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    importance: Importance


class CatrMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str  # "heuristic-v1" | "heuristic-v1+llm"
    confidence: float = Field(..., ge=0.0, le=1.0)
    enriched_by_llm: bool


class CanonicalAITask(BaseModel):
    """Strictly-typed canonical task representation (CATR)."""

    model_config = ConfigDict(extra="forbid")

    objective: str
    sub_goals: list[str] = Field(default_factory=list)
    domain: str
    inputs: list[str] = Field(default_factory=list)
    context: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    expected_output: str | None = None
    audience: str | None = None
    complexity: Complexity
    missing_information: list[MissingInformation] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    risk: Risk
    meta: CatrMeta
