"""Intent Engine v1 — turn a human sentence into a CATR (CanonicalAITask).

Pipeline:
  (a) fast, deterministic heuristics (domain, task type, extraction) → a full CATR;
  (b) ONLY if heuristic confidence is below the threshold AND a provider is configured,
      call a light LLM to refine ``objective`` + ``expected_output`` (cost control);
  (c) return the (possibly partial) strictly-typed CATR.

The LLM never runs in tests or offline: with no API key ``get_default_provider()``
returns ``None`` and the engine stays on the deterministic heuristic path. The CATR's
``meta`` records whether the LLM was used (``heuristic-v1`` vs ``heuristic-v1+llm``).
"""

from __future__ import annotations

import json

from app.core.config import settings
from app.engines.heuristics import build_heuristic_catr
from app.engines.providers import LLMProvider, ProviderError, get_default_provider
from app.schemas.catr import CanonicalAITask
from app.telemetry.logging import get_logger

logger = get_logger(__name__)

_OBJECTIVE_MAX = 200

_LLM_SYSTEM = (
    "You extract a task's objective and expected output from a user's sentence. "
    "Reply with STRICT JSON only: "
    '{"objective": "<one concise sentence>", "expected_output": "<concise description>"}. '
    "Use the sentence's own language. No markdown, no extra keys."
)


class IntentEngine:
    """Heuristics-first intent extraction with an optional, cost-gated LLM refinement."""

    def __init__(
        self,
        provider: LLMProvider | None = None,
        *,
        confidence_threshold: float | None = None,
    ) -> None:
        # Resolve the provider at call sites' discretion; None → heuristics only.
        self._provider = provider if provider is not None else get_default_provider()
        self._threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else settings.intent_confidence_threshold
        )

    async def run(self, sentence: str) -> CanonicalAITask:
        catr = build_heuristic_catr(sentence)  # (a) fast heuristics
        # (b) cost control: call the LLM only when unsure AND a provider exists.
        if catr.meta.confidence >= self._threshold or self._provider is None:
            return catr
        return await self._refine_with_llm(sentence, catr)

    async def _refine_with_llm(self, sentence: str, catr: CanonicalAITask) -> CanonicalAITask:
        assert self._provider is not None  # guarded by the caller
        user = f'Sentence: """{sentence.strip()}"""'
        try:
            raw = await self._provider.complete_json(system=_LLM_SYSTEM, user=user, max_tokens=300)
            data = json.loads(raw)
        except (ProviderError, json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "intent: LLM refine failed (%s); keeping heuristic CATR", type(exc).__name__
            )
            return catr
        if not isinstance(data, dict):
            return catr

        updates: dict[str, object] = {}
        objective = data.get("objective")
        if isinstance(objective, str) and objective.strip():
            updates["objective"] = objective.strip()[:_OBJECTIVE_MAX]
        expected = data.get("expected_output")
        if isinstance(expected, str) and expected.strip():
            updates["expected_output"] = expected.strip()

        meta = catr.meta.model_copy(update={"enriched_by_llm": True, "method": "heuristic-v1+llm"})
        return catr.model_copy(update={**updates, "meta": meta})
