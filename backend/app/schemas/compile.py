"""Schemas for the Kompilo Core compile endpoint (intent → execution strategy → prompt).

The response is deliberately multidimensional: an execution plan, the compiled prompt
(selected by ``mode``) plus all render variants, an EXPLAINABLE diagnostic (several
dimensions, never a single score), clarifying questions when the task is too ambiguous
to proceed, and metadata whose costs are explicitly ESTIMATED.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CompileMode = Literal["compact", "professional", "expert"]


class CompileRequest(BaseModel):
    task: str = Field(
        ..., min_length=1, max_length=10_000, description="What the user wants to accomplish."
    )
    context: dict[str, Any] = Field(default_factory=dict)
    target_model: str | None = Field(
        default=None, description="Force a model id from the registry."
    )
    mode: CompileMode = "professional"
    output_format: str = Field(default="markdown", max_length=100)
    quality_contract: list[str] = Field(default_factory=list, description="Quality requirements.")


# ── Compiled prompt ────────────────────────────────────────────────────────────────
class PromptSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    content: str


class PromptRenders(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compact: str
    professional: str
    expert: str


class CompiledPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: CompileMode
    text: str  # the render selected by `mode`
    sections: list[str]  # section names dynamically selected (no decorative sections)
    ir: list[PromptSection]  # the intermediate representation


# ── Execution plan ─────────────────────────────────────────────────────────────────
class ExecutionStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int
    action: str
    detail: str


class CostEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimated: bool = True  # ALWAYS an estimate, never a billed amount
    currency: str = "USD"
    input_tokens_est: int
    output_tokens_est: int
    cost_usd_est: float
    disclaimer: str = "Rough estimate from token heuristics and registry prices; not a quote."


class ExecutionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: str
    target_model: str | None
    fallback_models: list[str]
    steps: list[ExecutionStep]
    cost: CostEstimate


# ── Diagnostics (multidimensional, explainable) ─────────────────────────────────────
class DiagnosticDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str
    level: str
    detail: str


# ── Metadata + response ─────────────────────────────────────────────────────────────
class CompileMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: str = "kompilo-core-v1"
    deterministic: bool
    llm_used: bool
    target_model: str | None
    costs_estimated: bool = True
    notes: list[str] = Field(default_factory=list)


class CompileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # execution_plan / compiled_prompt / renders are null when clarification is needed
    # (decision == ASK): the pipeline stops after the ambiguity check.
    execution_plan: ExecutionPlan | None
    compiled_prompt: CompiledPrompt | None
    renders: PromptRenders | None
    diagnostics: list[DiagnosticDimension]
    questions: list[str]
    metadata: CompileMetadata
