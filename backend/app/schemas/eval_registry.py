"""Compile Eval Registry schema (bloc G) — deterministic cross-model regression guard.

A registry of eval *fixtures* replayed through the compile pipeline, each with DETERMINISTIC,
checkable expectations about the compiled result (decision, strategy, PQS band, woven
sections, injection flagging, detected model family). Running the same fixtures across
several target models makes the engine's behaviour comparable per family.

Honesty: this guards the PROCESS — that the engine keeps producing well-formed, well-specified
prompts — NOT the correctness of any model's answer. Answer quality needs real execution plus
ground truth (the output-based EvalHarness, flagged not-meaningful offline). No LLM is called
here, so the result is deterministic and always meaningful.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Decision = Literal["ASK", "PROCEED"]


class CompileExpectation(BaseModel):
    """Deterministic expectations about a compiled result. Every field is optional — only
    the ones that are set are checked, so a fixture asserts exactly what it means to."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    decision: Decision | None = None  # ASK vs PROCEED
    strategy: str | None = None  # single | chain | rag (PROCEED only)
    min_pqs: int | None = Field(default=None, ge=0, le=100)  # floor on the PQS
    min_band: str | None = None  # floor on the PQS band
    required_sections: list[str] = Field(default_factory=list)  # woven sections present
    security_risk: str | None = None  # expected security.risk, e.g. "high" on an injection
    evidence_injected: bool | None = None  # evidence policy woven into the prompt
    model_family: str | None = None  # detected model-adapter family (needs a pinned model)


class CompileEvalCase(BaseModel):
    """One fixture: an input task + the deterministic expectations it must keep meeting."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    name: str = Field(..., min_length=1, max_length=120)
    task: str = Field(..., min_length=1, max_length=10_000)
    output_format: str = Field(default="markdown", max_length=100)
    # When set, the case runs ONLY against this model (model-specific expectations such as
    # `model_family`). When None, it runs across the cross-model sweep (model-independent
    # expectations that must hold for every target).
    target_model: str | None = None
    expect: CompileExpectation = Field(default_factory=CompileExpectation)


class CheckResult(BaseModel):
    """The outcome of one deterministic expectation check."""

    model_config = ConfigDict(extra="forbid")

    name: str  # e.g. "decision", "min_pqs", "section:security"
    passed: bool
    expected: str
    actual: str


class CaseEvalResult(BaseModel):
    """A single (case × target model) evaluation."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    case: str
    target_model: str | None
    family: str | None  # model-adapter family (None on ASK, where no prompt is compiled)
    decision: Decision
    pqs: int | None  # None on ASK
    band: str | None  # None on ASK
    checks: list[CheckResult]
    passed: bool  # all checks passed


class ModelEvalSummary(BaseModel):
    """The engine's behaviour aggregated over the cases that ran against one model."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    target_model: str | None
    family: str | None
    n_cases: int
    n_passed: int
    pass_rate: float = Field(..., ge=0.0, le=1.0)
    mean_pqs: float | None  # mean over the model's PROCEED cases (None if none proceeded)


class EvalRegistryReport(BaseModel):
    """The full deterministic regression report over the registry × the model sweep."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    n_cases: int
    target_models: list[str | None]
    results: list[CaseEvalResult]
    by_model: list[ModelEvalSummary]
    regressions: list[CaseEvalResult]  # results with at least one failed check
    pass_rate: float = Field(..., ge=0.0, le=1.0)
    deterministic: bool  # True when no case triggered the optional intent LLM
    method: str = "compile-eval-v1"
    summary: str
    note: str
