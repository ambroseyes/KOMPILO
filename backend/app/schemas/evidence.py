"""Evidence & Uncertainty layer — the epistemic discipline of a compiled prompt.

Classifies what the task is built on into explicit *evidence classes*, derives the
source-of-truth hierarchy and the evidence policy woven into the compiled prompt.

Guiding principle (Ambro): no algorithm can guarantee correctness when the source
information is false, incomplete or ambiguous — so the engine is deliberately
CONSERVATIVE. It never promotes anything to a verified fact on its own: material the
user supplied is an operating ASSUMPTION, known gaps are explicit UNKNOWNs, and the
model's own parametric knowledge must be labelled INFERENCE/HYPOTHESIS and never
presented as a fact. ``fact`` / ``verified_external_fact`` are reserved for material a
human or a cited/retrievable source actually backs — the engine marks candidates, not
certainties.

Kept decoupled from ``schemas.compile`` (no import from it) so ``CompileResponse`` can
embed an ``EvidenceReport`` without a circular import.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Highest trust first. The engine never asserts the top two on its own; they require a
# human or a citable/retrievable source to back the statement.
EvidenceClass = Literal[
    "verified_external_fact",  # backed by a citable/retrievable source (e.g. the RAG corpus)
    "fact",  # asserted as given AND internally checkable
    "inference",  # derived by reasoning from givens
    "assumption",  # taken as true to proceed, but NOT verified (most user-provided context)
    "hypothesis",  # a candidate explanation to be tested, not asserted
    "unknown",  # explicitly missing / not known — to surface, never to invent
]

EvidenceSource = Literal[
    "retrieved_corpus",  # a per-tenant RAG corpus (citable at execution time)
    "user_provided",  # context / inputs the user supplied (operating givens)
    "model_knowledge",  # the model's own parametric knowledge (must be labelled)
    "gap",  # a known gap: missing information or an unresolved ambiguity
]

Confidence = Literal["low", "medium", "high"]


class EvidenceItem(BaseModel):
    """One piece of the task's material, sorted into an evidence class + its source."""

    model_config = ConfigDict(extra="forbid")

    statement: str  # the material being classified (trimmed)
    evidence_class: EvidenceClass
    source: EvidenceSource
    confidence: Confidence  # how firmly the material can be relied on (NOT its truth value)
    note: str | None = None


class EvidenceReport(BaseModel):
    """Evidence classification + source-of-truth hierarchy + injected policy for a prompt."""

    model_config = ConfigDict(extra="forbid")

    items: list[EvidenceItem] = Field(default_factory=list)
    hierarchy: list[str] = Field(default_factory=list)  # source-of-truth order, highest first
    policy: list[str] = Field(default_factory=list)  # directive lines woven into the prompt
    unknowns: list[str] = Field(default_factory=list)  # what is explicitly NOT known
    injected: bool = False  # whether the policy was woven into the compiled prompt's IR
    summary: str
    note: str
