"""Schemas for the Version Manager — save a compilation as a version, and diff two.

The diff is deliberately NEUTRAL: it reports what changed between two versions and never
declares one "better". A quality verdict requires a measurement (an eval), which the MVP
does not have — so none is given here. See ``engines/version_manager.py``.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.compile import CompileMode, CompileResponse
from app.schemas.prompt import PromptVersionRead

ChangeKind = Literal["added", "removed", "changed"]


# ── Save a compilation ───────────────────────────────────────────────────────
class SaveCompilationRequest(BaseModel):
    """Compile ``task`` server-side and persist the result as the prompt's next version.

    The snapshot (catr / ir / renders / diagnostics) is produced by Kompilo Core here,
    not trusted from the client — so a stored version always reflects a real compilation.
    """

    task: str = Field(..., min_length=1, max_length=10_000)
    source_intent: str | None = Field(default=None, max_length=10_000)
    mode: CompileMode = "professional"
    output_format: str = Field(default="markdown", max_length=100)
    target_model: str | None = None
    quality_contract: list[str] = Field(default_factory=list)


class SaveCompilationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: PromptVersionRead
    compile: CompileResponse


# ── Diff between two versions ─────────────────────────────────────────────────
class FieldChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str  # dotted path within the CATR, e.g. "objective" or "constraints"
    change: ChangeKind
    before: Any | None = None
    after: Any | None = None


class ScalarDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    before: str | None = None
    after: str | None = None
    changed: bool


class RenderDiff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str  # compact | professional | expert
    changed: bool
    unified_diff: str  # a textual unified diff (empty when unchanged)


class DiagnosticDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str
    before: str | None = None  # the level on the "from" version
    after: str | None = None  # the level on the "to" version
    changed: bool


class VersionDiff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_id: uuid.UUID
    from_version: int
    to_version: int
    source_intent: ScalarDelta
    model_target: ScalarDelta
    catr_fields: list[FieldChange]
    renders: list[RenderDiff]
    diagnostics: list[DiagnosticDelta]
    summary: str
    # Made explicit so no consumer mistakes a diff for a quality ranking.
    note: str = (
        "Comparaison neutre : décrit les différences entre deux versions, "
        "sans juger laquelle est « meilleure » (aucun verdict sans mesure)."
    )
