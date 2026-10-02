"""Schemas for the Kompilo compile pipeline (intent -> execution strategy)."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class CompileRequest(BaseModel):
    intent: str = Field(
        ...,
        min_length=1,
        max_length=10_000,
        description="Human intent to compile into an execution strategy.",
    )
    context: dict[str, Any] = Field(default_factory=dict)


class StageTrace(BaseModel):
    stage: str
    status: str
    note: str
    is_stub: bool = Field(
        True,
        description="True while this stage is a STUB placeholder.",
    )


class CompileResponse(BaseModel):
    execution_id: uuid.UUID = Field(
        ...,
        description="Id of the persisted Execution recording this run.",
    )
    intent: str
    strategy: dict[str, Any]
    trace: list[StageTrace]
    is_stub: bool = Field(
        True,
        description="True while ANY pipeline stage is still a STUB implementation.",
    )
