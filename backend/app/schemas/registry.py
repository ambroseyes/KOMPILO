"""Model Capability Registry schema (typed loader target).

One ``ModelCapability`` per real model the router may choose. Capabilities are DATA,
read by the router — never hardcoded in routing logic. ``last_verified`` is mandatory:
cost/context/latency drift, so a stale entry must be visible and re-verified. A missing
or false capability is treated as "not supported" (fail-closed) by the router.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReasoningStrength = Literal["basic", "medium", "advanced", "frontier"]

#: Ordered rank for threshold comparisons (read from the registry, not hardcoded logic).
REASONING_RANK: dict[ReasoningStrength, int] = {
    "basic": 1,
    "medium": 2,
    "advanced": 3,
    "frontier": 4,
}


class ModelCapability(BaseModel):
    # `model` is a plain field name here; disable Pydantic's protected "model_" namespace.
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    model: str
    provider: str
    context_window: int = Field(..., gt=0)
    supports_tools: bool
    supports_vision: bool
    structured_output: bool
    reasoning_strength: ReasoningStrength
    cost_in: float = Field(..., ge=0.0)  # USD per 1M input tokens
    cost_out: float = Field(..., ge=0.0)  # USD per 1M output tokens
    latency_ms: int = Field(..., gt=0)
    last_verified: date  # MANDATORY — see module docstring

    @property
    def reasoning_rank(self) -> int:
        return REASONING_RANK[self.reasoning_strength]

    @property
    def cost_total(self) -> float:
        """Blended per-1M-token cost used for ranking (inputs weighted heavier)."""
        return self.cost_in + self.cost_out
