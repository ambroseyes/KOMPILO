"""Execution Strategy Engine (PPOA steps 8–11) — decomposition + recommended tactics.

Deterministic. On top of the high-level single/chain/rag choice, it derives a subtask
decomposition (from the stated sub-goals — never invented) and recommends execution tactics
(decompose / tool-augmented / verification-loop / ensemble) with a rationale for each. For
non-trivial work it also produces a concise "recommended approach" directive woven into the
prompt (see :func:`approach_prompt_lines`).

Honesty: these are heuristic RECOMMENDATIONS for the execution process, not guarantees, and
the executor is unchanged — ``ensemble``/``tool_augmented`` are advised, not yet run by the
runtime. The point (Ambro's north star) is to make the reliable process explicit.
"""

from __future__ import annotations

from app.schemas.catr import CanonicalAITask
from app.schemas.execution_strategy import (
    ExecutionStrategy,
    ExecutionTactic,
    SubTask,
    TacticRecommendation,
)
from app.schemas.strategize import ComplexityAssessment, Strategy

# Objectives that read like a decision/comparison (high-stakes → ensemble candidate).
_DECISION_WORDS: tuple[str, ...] = (
    "choisir",
    "choix",
    "compare",
    "comparer",
    " vs ",
    "décider",
    "recommand",
    "meilleur",
    "best option",
    "lequel",
    "choose",
    "decide",
    "which",
    "select",
)
# Language implying external actions/tools (beyond inputs/retrieval).
_TOOL_WORDS: tuple[str, ...] = (
    "api",
    "fetch",
    "récupère",
    "recupere",
    "appelle",
    "call",
    "exécute",
    "execute",
    "run",
    "requête",
    "query",
    "scrape",
    "crawl",
    "cherche sur",
    "search the web",
    "outil",
    "tool",
)

# Priority when several tactics fire — the dominant mode becomes ``primary``.
_PRIMARY_ORDER: tuple[ExecutionTactic, ...] = (
    "decomposition",
    "tool_augmented",
    "ensemble",
    "verification_loop",
)

_NOTE = (
    "Recommandations déterministes pour le PROCESSUS d'exécution (fiabilité), pas une "
    "garantie de résultat. L'exécuteur n'est pas modifié : les tactiques « ensemble » et "
    "« tool_augmented » sont conseillées, pas encore exécutées par le runtime."
)


def _hay(catr: CanonicalAITask) -> str:
    return " ".join([catr.objective, *catr.sub_goals]).lower()


def _decomposition(catr: CanonicalAITask, strategy: Strategy) -> list[SubTask]:
    linear = strategy.kind == "chain"
    tasks: list[SubTask] = []
    for i, goal in enumerate(catr.sub_goals, start=1):
        depends = [i - 1] if (linear and i > 1) else []
        rationale = (
            "Dépend de l'étape précédente (traitement en chaîne)."
            if depends
            else "Sous-objectif issu de la tâche, traitable indépendamment."
        )
        tasks.append(SubTask(id=i, goal=goal, depends_on=depends, rationale=rationale))
    return tasks


class ExecutionStrategyEngine:
    """Derive decomposition + recommended execution tactics (deterministic)."""

    def plan(
        self,
        *,
        catr: CanonicalAITask,
        complexity: ComplexityAssessment,
        strategy: Strategy,
        quality_contract: list[str] | None = None,
    ) -> ExecutionStrategy:
        quality_contract = quality_contract or []
        hay = _hay(catr)
        multi_step = (
            complexity.level in {"complex", "agentic"}
            or len(catr.sub_goals) >= 3
            or strategy.kind == "chain"
        )
        tool = strategy.kind == "rag" or bool(catr.inputs) or any(w in hay for w in _TOOL_WORDS)
        verify = (
            catr.risk in {"medium", "high"} or catr.domain == "software" or bool(quality_contract)
        )
        is_decision = any(w in catr.objective.lower() for w in _DECISION_WORDS)
        ensemble = catr.risk == "high" and (
            is_decision or complexity.level in {"complex", "agentic"}
        )

        decomposition = _decomposition(catr, strategy)
        no_subtasks = multi_step and not decomposition

        tactics: list[TacticRecommendation] = [
            TacticRecommendation(
                tactic="decomposition",
                recommended=multi_step,
                rationale=(
                    "Travail multi-étapes (complexe/agentique, ≥3 sous-objectifs ou chaîne)"
                    + (
                        " — à décomposer explicitement (non fourni dans la tâche)."
                        if no_subtasks
                        else " — traiter les sous-étapes dans l'ordre de leurs dépendances."
                    )
                    if multi_step
                    else "Tâche non multi-étapes : une décomposition n'apporte rien."
                ),
            ),
            TacticRecommendation(
                tactic="tool_augmented",
                recommended=tool,
                rationale=(
                    "Sources/outils externes impliqués — s'appuyer dessus, ne pas inventer."
                    if tool
                    else "Aucun signal d'outil/source externe."
                ),
            ),
            TacticRecommendation(
                tactic="verification_loop",
                recommended=verify,
                rationale=(
                    "Exactitude critique (risque, logiciel ou contrat qualité) — produire puis "
                    "vérifier contre les critères avant de conclure."
                    if verify
                    else "Risque faible et pas d'exigence de validation forte."
                ),
            ),
            TacticRecommendation(
                tactic="ensemble",
                recommended=ensemble,
                rationale=(
                    "Enjeu élevé (risque haut + décision/complexité) — plusieurs tentatives "
                    "indépendantes puis réconciliation."
                    if ensemble
                    else "Enjeu insuffisant pour justifier le coût d'un ensemble."
                ),
            ),
        ]

        recommended = {t.tactic for t in tactics if t.recommended}
        primary: ExecutionTactic = next((t for t in _PRIMARY_ORDER if t in recommended), "direct")

        n_reco = len(recommended)
        summary = (
            "Approche directe (une passe)."
            if primary == "direct"
            else f"Approche « {primary} » + {n_reco} tactique(s) recommandée(s)."
        )
        return ExecutionStrategy(
            primary=primary,
            tactics=tactics,
            decomposition=decomposition,
            summary=summary,
            note=_NOTE,
        )


_APPROACH_LINE: dict[ExecutionTactic, str] = {
    "decomposition": (
        "Décompose la tâche en sous-étapes et traite-les dans l'ordre de leurs dépendances."
    ),
    "tool_augmented": (
        "Appuie-toi sur les sources/outils fournis ; ne fabrique pas ce qui doit être récupéré."
    ),
    "verification_loop": (
        "Produis puis vérifie la sortie contre les critères de réussite ; "
        "corrige avant de conclure."
    ),
    "ensemble": (
        "Enjeu élevé : envisage plusieurs approches indépendantes, puis réconcilie-les avant de "
        "trancher."
    ),
}


def approach_prompt_lines(es: ExecutionStrategy) -> list[str]:
    """Concise "recommended approach" directives for the prompt (non-trivial tactics only).

    Empty when the strategy is a plain direct pass — nothing worth adding to the prompt.
    """
    if es.primary == "direct":
        return []
    ordered: list[ExecutionTactic] = [*_PRIMARY_ORDER]
    recommended = {t.tactic for t in es.tactics if t.recommended}
    return [_APPROACH_LINE[t] for t in ordered if t in recommended and t in _APPROACH_LINE]
