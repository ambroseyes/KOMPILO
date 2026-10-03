"""Verifier schemas — validate an output against its contract (format + optional schema)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

IssueKind = Literal[
    "empty_output",
    "parse_error",
    "missing_field",
    "type_mismatch",
    "format",
]


class VerificationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: IssueKind
    detail: str
    path: str | None = None  # dotted path to the offending field, when applicable


class VerificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    format: str
    issues: list[VerificationIssue] = Field(default_factory=list)
    summary: str
