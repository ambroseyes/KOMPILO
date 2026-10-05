"""Execution Strategy — decomposition + recommended execution tactics (PPOA steps 8–11,
Framework §9 "Execution Strategies", CDC §6).

The Strategy Engine already picks the high-level approach (single / chain / rag). This layer
adds the *finer* execution strategy: how to run the task reliably — a subtask decomposition
(with dependencies) and a set of recommended tactics (decompose, tool-augmented,
verification-loop, ensemble), each justified. It is derived deterministically from the CATR
+ complexity + strategy; it invents no subtask (the decomposition comes from the stated
sub-goals) and promises nothing about the answer.

Honesty stance (Ambro's principle — optimize PROCESS reliability, never promise
infallibility): these are heuristic RECOMMENDATIONS that make the right process explicit.
The executor is unchanged, so tactics like ``ensemble`` or ``tool_augmented`` are advised,
not yet carried out by the runtime — the field documents the recommended process, and (for
complex work) a concise "recommended approach" directive is woven into the prompt.

Kept decoupled from ``schemas.compile`` (no import from it) so ``CompileResponse`` can embed
an ``ExecutionStrategy`` without a circular import.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ExecutionTactic = Literal[
    "direct",  # a single straightforward pass (simple tasks)
    "decomposition",  # break into ordered sub-tasks and solve each
    "tool_augmented",  # rely on external sources/tools/retrieval, do not invent them
    "verification_loop",  # generate, then verify against criteria and correct
    "ensemble",  # high stakes: several independent attempts, then reconcile
]


class SubTask(BaseModel):
    """One node of the decomposition — derived from a stated sub-goal, never invented."""

    model_config = ConfigDict(extra="forbid")

    id: int
    goal: str
    depends_on: list[int] = Field(default_factory=list)
    rationale: str


class TacticRecommendation(BaseModel):
    """A recommended (or explicitly not-recommended) execution tactic, with its reason."""

    model_config = ConfigDict(extra="forbid")

    tactic: ExecutionTactic
    recommended: bool
    rationale: str


class ExecutionStrategy(BaseModel):
    """Decomposition + recommended tactics for executing the task reliably."""

    model_config = ConfigDict(extra="forbid")

    primary: ExecutionTactic  # the dominant recommended mode
    tactics: list[TacticRecommendation] = Field(default_factory=list)
    decomposition: list[SubTask] = Field(default_factory=list)
    injected: bool = False  # whether a "recommended approach" directive was woven in
    summary: str
    note: str
