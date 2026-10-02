"""Strategy — the output of the `strategize` stage.

The strategize stage consumes a :class:`~app.schemas.catr.Catr` (the structured
understanding of the intent) and produces a *Strategy*: the chosen high-level
approach, the ordered candidate steps that would satisfy the goal, and whether the
intent is clear enough to plan confidently or needs clarification first. It is
consumed downstream by the ``compile`` stage, which turns these steps into an
executable plan.

``method`` records HOW the strategy was produced — ``heuristic-v1`` is a
deterministic, rule-based planner (NOT an LLM); ``claude-v1`` is a Claude-backed
one. The marker is intentional so no consumer mistakes heuristic output for model
reasoning. Both planners share the one ``strategize`` contract and emit this schema.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# How the strategy was produced (mirrors ``Catr.method``).
StrategyMethod = Literal["heuristic-v1", "claude-v1"]

# The high-level shape of the plan.
#   single_step   — one action satisfies the goal.
#   multi_step    — an ordered sequence of actions.
#   clarify_first — the intent is too ambiguous; clarification is needed before planning.
Approach = Literal["single_step", "multi_step", "clarify_first"]


class StrategyStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int = Field(..., ge=1, description="1-based position of the step in the plan.")
    title: str = Field(..., description="Short imperative label for the step.")
    description: str = Field(..., description="What this step accomplishes.")
    depends_on: list[int] = Field(
        default_factory=list,
        description="Orders of steps that must complete before this one.",
    )


class Strategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: StrategyMethod = "heuristic-v1"
    approach: Approach
    rationale: str = Field(..., description="One line explaining why this approach fits the CATR.")
    steps: list[StrategyStep] = Field(
        default_factory=list,
        description="Ordered candidate steps. Empty only when clarification is needed.",
    )
    candidate_count: int = Field(
        1,
        ge=1,
        description="Number of candidate strategies considered (MVP: a single candidate).",
    )
    needs_clarification: bool = Field(
        False,
        description="True when open questions / low confidence block confident planning.",
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Calibrated confidence (0..1).")
