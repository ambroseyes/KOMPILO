"""Schemas for POST /v1/execute — run a plan and return the result + REAL metadata.

``RealCost.actual`` is True and the field is named ``actual_cost`` so a real spend is
never confused with the compile-time ``CostEstimate`` (``estimated=True``). On an
ambiguous task the pipeline returns ``questions`` and does not execute.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.compile import CompileMode
from app.schemas.verify import VerificationReport


class ExecuteRequest(BaseModel):
    task: str | None = Field(default=None, max_length=10_000)
    prompt_version_id: uuid.UUID | None = None
    mode: CompileMode = "professional"
    output_format: str = Field(default="markdown", max_length=100)
    quality_contract: list[str] = Field(default_factory=list)
    target_model: str | None = None
    # Optional output contract: when output_format is "json", the result is validated.
    output_schema: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _one_source(self) -> ExecuteRequest:
        if not self.task and self.prompt_version_id is None:
            raise ValueError("provide either `task` or `prompt_version_id`")
        return self


class ExecuteStepResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int
    action: str
    output: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cached: bool
    latency_ms: int
    repaired: bool = False  # a JSON-contract repair retry was applied to this step


class RealCost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actual: bool = True  # REAL spend — distinct from the compile-time estimate
    currency: str = "USD"
    input_tokens: int
    output_tokens: int
    cost_usd: float


class ExecuteMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    provider_is_real: bool  # False when the offline Echo STUB produced the output
    model: str | None
    actual_cost: RealCost
    latency_ms: int
    cached: bool
    idempotent_replay: bool = False
    note: str | None = None


class ExecuteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: uuid.UUID | None  # null when clarification is needed (not executed)
    status: str  # succeeded | needs_clarification | failed
    output: str
    steps: list[ExecuteStepResult]
    questions: list[str]
    metadata: ExecuteMetadata | None
    verification: VerificationReport | None = None
