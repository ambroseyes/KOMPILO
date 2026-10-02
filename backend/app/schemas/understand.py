"""Contract for the ``understand`` pipeline stage.

``UnderstandResult`` is the stable, validated interface that downstream stages
(``strategize`` and beyond) consume — they depend on this shape, never on the
raw intent text.

The split is deliberate:

- ``UnderstandCore`` is exactly what the LLM is asked to emit. Its JSON Schema
  (``UnderstandCore.model_json_schema()``) is the tool input schema, and the
  model's tool call is re-validated against it (belt and braces).
- ``UnderstandResult`` extends it with fields our own code fills: the derived
  ``needs_clarification`` flag and provenance (``model``, ``usage``). These are
  never trusted from the model.

All collection fields default to ``[]`` (never ``null``), ``task_type`` is a
closed enum (an invented label fails validation), and ``confidence`` is bounded
to ``[0, 1]``.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class TaskType(StrEnum):
    """Closed taxonomy of what the user is asking for."""

    GENERATION = "generation"
    EXTRACTION = "extraction"
    TRANSFORMATION = "transformation"
    QA = "qa"
    CLASSIFICATION = "classification"
    AGENTIC = "agentic"
    OTHER = "other"


class AmbiguitySeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Entity(BaseModel):
    """A concrete object, format, or target named in the intent."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=200)
    type: str = Field(..., min_length=1, max_length=100)
    value: str | None = Field(default=None, max_length=2000)


class Ambiguity(BaseModel):
    """Something missing or unclear that could block ``strategize``."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=1, max_length=1000)
    severity: AmbiguitySeverity = AmbiguitySeverity.MEDIUM


class UnderstandCore(BaseModel):
    """The fields the LLM produces. Its JSON Schema is the tool input schema."""

    model_config = ConfigDict(extra="forbid")

    normalized_intent: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Canonical, imperative restatement of the intent.",
    )
    language: str = Field(
        ...,
        min_length=2,
        max_length=10,
        description="Detected (or imposed) response language, ISO 639-1 / BCP-47.",
    )
    task_type: TaskType = TaskType.OTHER
    goal: str = Field(..., min_length=1, max_length=4000)
    entities: list[Entity] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    ambiguities: list[Ambiguity] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)


class UnderstandResult(UnderstandCore):
    """Core understanding plus fields the stage derives/fills (not the model)."""

    # Derived deterministically by our code from ambiguities + confidence.
    needs_clarification: bool = False
    # Provenance, filled by the stage after the call.
    model: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)
