"""Model Router v1 — pick a primary model + fallbacks for a CATR + strategy.

Two phases:
  1. FILTER by required capabilities, read entirely from the registry (never hardcoded
     per-model). A capability that isn't confirmed supported is treated as absent
     (fail-closed), so such a model is excluded.
  2. RANK the survivors by a complexity-weighted blend of quality (reasoning strength),
     cost and latency; return the best as primary and the rest as ordered fallbacks.

Required capabilities are derived from the CATR/strategy/complexity, then matched against
registry fields — the routing logic asks "does this model's registry entry support X?",
it never knows any model by name.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.engines.registry import default_registry
from app.schemas.catr import CanonicalAITask
from app.schemas.registry import ModelCapability
from app.schemas.strategize import ComplexityAssessment, ComplexityLevel, RouteDecision, Strategy

_MIN_REASONING_RANK: dict[ComplexityLevel, int] = {
    "simple": 1,
    "moderate": 2,
    "complex": 3,
    "agentic": 4,
}
_MIN_CONTEXT: dict[ComplexityLevel, int] = {
    "simple": 8_000,
    "moderate": 16_000,
    "complex": 32_000,
    "agentic": 32_000,
}
_RAG_MIN_CONTEXT = 32_000

# (quality, cost, latency) weights by complexity; each row sums to 1.0.
_WEIGHTS: dict[ComplexityLevel, tuple[float, float, float]] = {
    "simple": (0.20, 0.50, 0.30),
    "moderate": (0.40, 0.35, 0.25),
    "complex": (0.60, 0.25, 0.15),
    "agentic": (0.70, 0.20, 0.10),
}

_VISION_EXT_RE = re.compile(r"\.(?:png|jpe?g|gif|webp|bmp|tiff?)$", re.I)
_VISION_WORDS = ("image", "images", "photo", "screenshot", "capture", "diagram", "schéma", "figure")
_STRUCTURED_WORDS = (
    "json",
    "schema",
    "schéma",
    "structured",
    "structuré",
    "table",
    "tableau",
    "yaml",
)


def _needs_vision(catr: CanonicalAITask) -> bool:
    if any(_VISION_EXT_RE.search(i.strip()) for i in catr.inputs):
        return True
    hay = " ".join([catr.objective, *catr.context]).lower()
    return any(w in hay for w in _VISION_WORDS)


def _needs_structured(catr: CanonicalAITask) -> bool:
    if catr.expected_output is None:
        return False
    return any(w in catr.expected_output.lower() for w in _STRUCTURED_WORDS)


def _minmax(values: list[float]) -> list[float]:
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


class ModelRouter:
    def __init__(self, models: Sequence[ModelCapability] | None = None) -> None:
        self._models: tuple[ModelCapability, ...] = (
            tuple(models) if models is not None else default_registry()
        )

    def route(
        self, catr: CanonicalAITask, strategy: Strategy, complexity: ComplexityAssessment
    ) -> RouteDecision:
        level = complexity.level
        needs_tools = level == "agentic" or strategy.kind == "rag"
        needs_vision = _needs_vision(catr)
        needs_structured = _needs_structured(catr)
        min_rank = _MIN_REASONING_RANK[level]
        min_context = _RAG_MIN_CONTEXT if strategy.kind == "rag" else _MIN_CONTEXT[level]

        required: list[str] = [f"reasoning>={_rank_name(min_rank)}", f"context>={min_context}"]
        if needs_tools:
            required.append("tools")
        if needs_vision:
            required.append("vision")
        if needs_structured:
            required.append("structured_output")

        # Phase 1 — filter. Every check reads a registry field; unknown/false ⇒ excluded.
        survivors = [
            m
            for m in self._models
            if m.reasoning_rank >= min_rank
            and m.context_window >= min_context
            and (m.supports_tools if needs_tools else True)
            and (m.supports_vision if needs_vision else True)
            and (m.structured_output if needs_structured else True)
        ]
        if not survivors:
            return RouteDecision(
                primary=None,
                fallbacks=[],
                required_capabilities=required,
                rationale="No model in the registry meets the required capabilities.",
            )

        # Phase 2 — rank by complexity-weighted quality / cost / latency.
        w_q, w_c, w_l = _WEIGHTS[level]
        q_norm = _minmax([float(m.reasoning_rank) for m in survivors])
        c_norm = _minmax([m.cost_total for m in survivors])
        l_norm = _minmax([float(m.latency_ms) for m in survivors])
        scored: list[tuple[float, ModelCapability]] = []
        for m, qn, cn, ln in zip(survivors, q_norm, c_norm, l_norm, strict=True):
            score = w_q * qn + w_c * (1.0 - cn) + w_l * (1.0 - ln)
            scored.append((score, m))
        # Deterministic ordering: score desc, then cheaper, then faster, then name.
        scored.sort(key=lambda sm: (-sm[0], sm[1].cost_total, sm[1].latency_ms, sm[1].model))

        ordered = [m.model for _, m in scored]
        return RouteDecision(
            primary=ordered[0],
            fallbacks=ordered[1:],
            required_capabilities=required,
            rationale=(
                f"{len(survivors)}/{len(self._models)} models met the capabilities; "
                f"ranked for a {level} task "
                f"(quality {w_q:.0%} / cost {w_c:.0%} / latency {w_l:.0%})."
            ),
        )


def _rank_name(rank: int) -> str:
    return {1: "basic", 2: "medium", 3: "advanced", 4: "frontier"}.get(rank, str(rank))
