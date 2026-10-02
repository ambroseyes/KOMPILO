"""The `strategize` stage — turns a CATR into an execution Strategy.

Two analyzers share one contract, ``strategize(catr, context) -> Strategy``:

* a deterministic, offline HEURISTIC planner (``strategize_plan``, ``method="heuristic-v1"``)
  that maps the CATR's ``task_type`` and clarity to a small ordered plan — rule-based
  only, no API key, no network, so it is unit-testable in isolation; and
* a Claude-backed planner (``strategize_llm``, ``method="claude-v1"``) that emits the
  same :class:`~app.schemas.strategy.Strategy` through a forced tool call.

``strategize`` prefers the LLM when a provider is configured and degrades to the
heuristic on failure, exactly like :mod:`app.engines.understand`. The ``method`` marker
always tells which planner actually produced the result.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import ValidationError

from app.core.config import settings
from app.engines.llm import LLMClient, LLMError, get_llm_client
from app.engines.prompts.strategize import (
    TOOL_DESCRIPTION,
    TOOL_NAME,
    build_system_prompt,
    build_user_message,
    strategy_tool_schema,
)
from app.schemas.catr import Catr, TaskType
from app.schemas.strategy import Approach, Strategy, StrategyStep
from app.telemetry.logging import get_logger

logger = get_logger(__name__)

# Base for the exponential backoff between LLM retries (seconds); small by design.
_BACKOFF_BASE_S = 0.2


def _t(language: str, fr: str, en: str) -> str:
    """Pick the French or English template for the CATR's language."""
    return fr if language == "fr" else en


# Ordered step templates per multi-step task type: (fr_title, en_title, fr_desc, en_desc).
_PLAN_TEMPLATES: dict[TaskType, tuple[tuple[str, str, str, str], ...]] = {
    "code_generation": (
        (
            "Concevoir la solution",
            "Design the solution",
            "Définir l'approche technique et les interfaces.",
            "Define the technical approach and interfaces.",
        ),
        (
            "Implémenter",
            "Implement",
            "Écrire le code qui réalise l'intention.",
            "Write the code that fulfils the intent.",
        ),
        (
            "Tester et valider",
            "Test and validate",
            "Vérifier le comportement et couvrir les cas limites.",
            "Check behaviour and cover edge cases.",
        ),
    ),
    "data_analysis": (
        (
            "Préparer les données",
            "Prepare the data",
            "Charger et nettoyer les entrées.",
            "Load and clean the inputs.",
        ),
        (
            "Analyser",
            "Analyze",
            "Appliquer le calcul ou la méthode statistique requis.",
            "Apply the required computation or statistical method.",
        ),
        (
            "Synthétiser les résultats",
            "Summarize the results",
            "Restituer des conclusions interprétables.",
            "Report interpretable conclusions.",
        ),
    ),
    "writing": (
        (
            "Établir le plan",
            "Outline",
            "Structurer les idées avant la rédaction.",
            "Structure the ideas before drafting.",
        ),
        (
            "Rédiger le brouillon",
            "Draft",
            "Produire une première version complète.",
            "Produce a complete first version.",
        ),
        (
            "Réviser",
            "Revise",
            "Corriger le ton, le format et les contraintes.",
            "Fix tone, format and constraints.",
        ),
    ),
    "planning": (
        (
            "Définir les objectifs",
            "Define the objectives",
            "Clarifier le résultat visé.",
            "Clarify the intended outcome.",
        ),
        (
            "Découper en jalons",
            "Break into milestones",
            "Identifier les étapes intermédiaires.",
            "Identify the intermediate steps.",
        ),
        (
            "Ordonner et prioriser",
            "Order and prioritize",
            "Séquencer les étapes et leurs dépendances.",
            "Sequence the steps and their dependencies.",
        ),
    ),
}

# Task types answered in a single step: (fr_title, en_title, fr_desc, en_desc).
_SINGLE_STEP: dict[TaskType, tuple[str, str, str, str]] = {
    "qa": (
        "Répondre à la question",
        "Answer the question",
        "Formuler une réponse exacte et directe.",
        "Formulate an accurate, direct answer.",
    ),
    "other": (
        "Produire le livrable",
        "Produce the deliverable",
        "Réaliser ce que l'intention demande.",
        "Deliver what the intent asks for.",
    ),
}


def _needs_clarification(catr: Catr) -> bool:
    """A CATR needs clarification when it has open questions or low confidence."""
    return bool(catr.open_questions) or catr.confidence < settings.strategize_confidence_threshold


def _clarify_strategy(catr: Catr) -> Strategy:
    """A ``clarify_first`` strategy: surface the CATR's open questions as a single step."""
    language = catr.language
    questions = catr.open_questions or [
        _t(
            language,
            "Peux-tu préciser le résultat attendu ?",
            "Can you clarify the expected outcome?",
        )
    ]
    joined = " ".join(questions)
    step = StrategyStep(
        order=1,
        title=_t(language, "Clarifier l'intention", "Clarify the intent"),
        description=_t(
            language,
            f"Obtenir les précisions nécessaires avant de planifier : {joined}",
            f"Obtain the clarifications needed before planning: {joined}",
        ),
    )
    return Strategy(
        approach="clarify_first",
        rationale=_t(
            language,
            "Des questions ouvertes ou une faible confiance empêchent une planification fiable.",
            "Open questions or low confidence prevent confident planning.",
        ),
        steps=[step],
        candidate_count=1,
        needs_clarification=True,
        confidence=round(min(catr.confidence, 0.4), 2),
    )


def _plan_steps(task_type: TaskType, language: str) -> tuple[Approach, list[StrategyStep]]:
    """Return the (approach, steps) for a clear CATR of this task type."""
    if task_type in _SINGLE_STEP:
        fr_title, en_title, fr_desc, en_desc = _SINGLE_STEP[task_type]
        step = StrategyStep(
            order=1,
            title=_t(language, fr_title, en_title),
            description=_t(language, fr_desc, en_desc),
        )
        return "single_step", [step]

    template = _PLAN_TEMPLATES[task_type]
    steps = [
        StrategyStep(
            order=i,
            title=_t(language, fr_title, en_title),
            description=_t(language, fr_desc, en_desc),
            depends_on=[i - 1] if i > 1 else [],
        )
        for i, (fr_title, en_title, fr_desc, en_desc) in enumerate(template, start=1)
    ]
    return "multi_step", steps


def _rationale(approach: Approach, task_type: TaskType, language: str) -> str:
    if approach == "single_step":
        return _t(
            language,
            f"La tâche ({task_type}) se satisfait d'une seule action.",
            f"The task ({task_type}) is satisfied by a single action.",
        )
    return _t(
        language,
        f"La tâche ({task_type}) se décompose en étapes ordonnées.",
        f"The task ({task_type}) decomposes into ordered steps.",
    )


def strategize_plan(catr: Catr, context: dict[str, Any] | None = None) -> Strategy:
    """Deterministically plan a CATR into a Strategy (heuristic-v1).

    ``context`` is accepted for forward-compatibility (caller hints) but the
    heuristic planner does not consume it yet.
    """
    _ = context  # reserved; not used by the heuristic planner
    if _needs_clarification(catr):
        return _clarify_strategy(catr)

    language = catr.language
    approach, steps = _plan_steps(catr.task_type, language)
    # Confidence tracks the CATR's but is never higher than it (planning can only add
    # uncertainty), with a small bonus for a decisive single-step plan.
    confidence = catr.confidence + (0.05 if approach == "single_step" else 0.0)
    return Strategy(
        approach=approach,
        rationale=_rationale(approach, catr.task_type, language),
        steps=steps,
        candidate_count=1,
        needs_clarification=False,
        confidence=round(max(0.05, min(0.98, confidence)), 2),
    )


async def strategize_llm(catr: Catr, context: dict[str, Any] | None, llm: LLMClient) -> Strategy:
    """Plan a CATR into a Strategy via a forced-tool Claude call (``claude-v1``).

    The model emits the Strategy fields through the ``propose_strategy`` tool; we
    stamp ``method="claude-v1"`` and re-validate against :class:`Strategy` (so an
    off-schema tool call is rejected). Bounded retries with backoff on a transient
    LLM error or a validation failure; the last error propagates.
    """
    system = build_system_prompt()
    user = build_user_message(catr, context)
    schema = strategy_tool_schema()
    attempts = settings.llm_max_retries + 1
    last_error: Exception | None = None

    for attempt in range(attempts):
        try:
            call = await llm.emit_tool(
                system=system,
                user=user,
                tool_name=TOOL_NAME,
                tool_description=TOOL_DESCRIPTION,
                input_schema=schema,
                model=settings.strategize_model,
                max_tokens=settings.llm_max_tokens,
                temperature=0.0,
            )
            return Strategy.model_validate({**call.arguments, "method": "claude-v1"})
        except (LLMError, ValidationError) as exc:
            last_error = exc
            logger.warning("strategize(llm) attempt %d/%d failed: %s", attempt + 1, attempts, exc)
            if attempt + 1 < attempts:
                await asyncio.sleep(_BACKOFF_BASE_S * (2**attempt))

    raise last_error if last_error is not None else LLMError("strategize failed")


async def strategize(catr: Catr, context: dict[str, Any] | None = None) -> Strategy:
    """Produce a Strategy, preferring the LLM planner and falling back to heuristic.

    Engine selection is by configuration: an Anthropic key yields the Claude planner
    (``claude-v1``); with no provider configured the deterministic heuristic
    (``heuristic-v1``) is used. If a configured LLM call ultimately fails, we degrade
    to the heuristic rather than erroring — the ``method`` marker always tells which
    planner actually produced the result.
    """
    llm = get_llm_client()
    if llm is None:
        return strategize_plan(catr, context)
    try:
        return await strategize_llm(catr, context, llm)
    except (LLMError, ValidationError):
        logger.warning("strategize: LLM planning failed; falling back to heuristic")
        return strategize_plan(catr, context)
