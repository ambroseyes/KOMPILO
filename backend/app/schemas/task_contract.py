"""Task Contract — a model-neutral, structured specification of the task (PPOA step 14,
Framework §5 "Universal Task Contract", CDC §4).

The contract is the pipeline's portable statement of *what* must be done and *what makes
the result acceptable*, independent of any model or vendor. It is DERIVED deterministically
from the CATR + the strategy/route + the evidence & security layers — it never invents
requirements. Two of its derived parts (``scope`` and ``success_criteria``) are woven into
the compiled prompt, which is the measurable payoff: the PQS ``scope_discipline`` and
``success_criteria`` axes rise because the prompt now states its boundaries and its
acceptance criteria explicitly.

Honesty stance (Ambro's principle): the contract structures and BOUNDS the work from the
task as stated; it does not guarantee the statement is complete or correct. Gaps stay
surfaced (``assumptions`` carries the unverified givens; unknowns remain flagged by the
evidence layer). ``model_preferences`` is a capability-based suggestion from the router,
NEVER a lock to a provider — any model family meeting the required capabilities can run it.

Kept decoupled from ``schemas.compile`` (no import from it) so ``CompileResponse`` can
embed a ``TaskContract`` without a circular import.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SuccessCriterion(BaseModel):
    """One acceptance criterion — what makes the result acceptable, and how to check it."""

    model_config = ConfigDict(extra="forbid")

    statement: str
    measurable: bool  # True when the criterion can be checked objectively (not a judgement call)
    verification: str  # concretely, how to verify this criterion


class OutputContract(BaseModel):
    """The expected shape of the output, stated independently of any model."""

    model_config = ConfigDict(extra="forbid")

    format: str  # e.g. "markdown", "json", "text"
    structured: bool  # whether a machine-checkable structure is expected
    schema_hint: str | None = None  # a hint of the expected structure/content, when known
    model_independent: bool = True  # the contract is portable across model families


class ModelPreferences(BaseModel):
    """A CAPABILITY-based model suggestion from the router — not a vendor lock.

    ``primary``/``fallbacks`` are concrete ids the router picked to satisfy
    ``required_capabilities``; any other model family meeting the same capabilities is a
    valid substitute (``portability_note`` says so explicitly).
    """

    model_config = ConfigDict(extra="forbid")

    primary: str | None
    fallbacks: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    rationale: str
    portability_note: str


class TaskContract(BaseModel):
    """A model-neutral specification of the task + its acceptance criteria."""

    model_config = ConfigDict(extra="forbid")

    objective: str
    domain: str
    scope: list[str] = Field(default_factory=list)  # what is in scope
    out_of_scope: list[str] = Field(default_factory=list)  # explicit boundaries (anti-drift)
    assumptions: list[str] = Field(default_factory=list)  # unverified givens taken to proceed
    success_criteria: list[SuccessCriterion] = Field(default_factory=list)
    validation: list[str] = Field(default_factory=list)  # how the result will be checked
    # Present only when the objective is a decision/choice; None otherwise.
    decision_criteria: list[str] | None = None
    constraints: list[str] = Field(default_factory=list)
    output_contract: OutputContract
    model_preferences: ModelPreferences
    note: str
