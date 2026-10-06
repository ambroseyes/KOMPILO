"""Schemas for the Kompilo Core compile endpoint (intent → execution strategy → prompt).

The response is deliberately multidimensional: an execution plan, the compiled prompt
(selected by ``mode``) plus all render variants, an EXPLAINABLE diagnostic (several
dimensions, never a single score), clarifying questions when the task is too ambiguous
to proceed, and metadata whose costs are explicitly ESTIMATED.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.evidence import EvidenceReport
from app.schemas.execution_strategy import ExecutionStrategy
from app.schemas.prompt_quality import PromptQualityReport
from app.schemas.security import SecurityReport
from app.schemas.task_contract import TaskContract

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
DiagnosticLevel = Literal["low", "medium", "high"]


class DiagnosticDimension(BaseModel):
    """One axis of the explainable diagnostic.

    There is NEVER a single aggregate score: each axis stands on its own with a
    ``level`` (low/medium/high), a one-line ``detail``, and — when the axis is weak
    (not ``high``) — the ``reason`` it is weak plus a concrete ``recommendation``.
    """

    model_config = ConfigDict(extra="forbid")

    dimension: str  # machine key, e.g. "clarity"
    label: str  # human label (French), e.g. "Clarté"
    level: DiagnosticLevel
    detail: str
    reason: str | None = None  # why it is weak (set when level != "high")
    recommendation: str | None = None  # corrective action (set when level != "high")


# ── Metadata + response ─────────────────────────────────────────────────────────────
class UnderstoodIntent(BaseModel):
    """What Kompilo understood from the task (shown first, in ASK and PROCEED alike)."""

    model_config = ConfigDict(extra="forbid")

    objective: str
    domain: str


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

    understood: UnderstoodIntent
    # execution_plan / compiled_prompt / renders are null when clarification is needed
    # (decision == ASK): the pipeline stops after the ambiguity check.
    execution_plan: ExecutionPlan | None
    compiled_prompt: CompiledPrompt | None
    renders: PromptRenders | None
    diagnostics: list[DiagnosticDimension]
    # Prompt readiness: PQS + adversarial findings + repair. Null on ASK (no prompt yet).
    prompt_quality: PromptQualityReport | None = None
    # Evidence & uncertainty: how the task's material is classified + the policy woven into
    # the prompt. Null on ASK (no prompt compiled yet).
    evidence: EvidenceReport | None = None
    # Security: injection findings + the trust-boundary policy woven into the prompt.
    # Null on ASK (no prompt compiled yet).
    security: SecurityReport | None = None
    # Task Contract: model-neutral spec (scope, measurable success criteria, assumptions,
    # validation, output contract, capability-based model preferences). Null on ASK.
    task_contract: TaskContract | None = None
    # Execution Strategy: subtask decomposition + recommended tactics (decompose,
    # tool-augmented, verification-loop, ensemble). Null on ASK.
    execution_strategy: ExecutionStrategy | None = None
    questions: list[str]
    metadata: CompileMetadata
