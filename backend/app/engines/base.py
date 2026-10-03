"""Core pipeline abstractions for Kompilo's execution-intelligence engine.

The pipeline turns a human *intent* into an *execution strategy* through a fixed
sequence of stages:

    understand -> strategize -> compile -> route -> execute -> verify
    -> evaluate -> improve

Each stage is a small, independently testable unit implementing ``Stage``.
This module defines the contracts only — real stage logic lives in ``stages.py``.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StageResult:
    stage: str
    status: str  # "ok" | "skipped" | "error"
    note: str
    output: dict[str, Any] = field(default_factory=dict)
    # True while the stage is a placeholder; a real stage sets this False.
    is_stub: bool = True


@dataclass
class PipelineContext:
    """Mutable state threaded through every stage of a single run."""

    intent: str
    context: dict[str, Any] = field(default_factory=dict)
    # Accumulated artifacts keyed by stage name.
    artifacts: dict[str, Any] = field(default_factory=dict)
    trace: list[StageResult] = field(default_factory=list)


class Stage(abc.ABC):
    """A single pipeline stage."""

    #: Stable identifier used in traces and artifacts.
    name: str

    @abc.abstractmethod
    async def run(self, ctx: PipelineContext) -> StageResult:
        """Execute the stage against the shared context and return its result."""
        raise NotImplementedError
