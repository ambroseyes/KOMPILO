"""Diagnostic Engine v1 — an explainable, multidimensional diagnostic (no single score).

Eight independent axes, each with a level (low/medium/high), a one-line explanation,
and — when weak (not ``high``) — the reason plus a concrete corrective action:

  clarity · completeness · specificity · robustness · executability ·
  context_quality · output_definition · ambiguity_handling

The engine is deterministic and rule-based. It reads the CATR and the strategize
outputs (ambiguity always; complexity/strategy/route when available — they are absent in
the ASK branch, handled gracefully). It NEVER collapses the axes into one score: a prompt
is strong or weak in specific, nameable ways. See the ``kompilo-solidify`` skill.
"""

from __future__ import annotations

from app.schemas.catr import CanonicalAITask
from app.schemas.compile import DiagnosticDimension, DiagnosticLevel
from app.schemas.strategize import (
    AmbiguityReport,
    ComplexityAssessment,
    RouteDecision,
    Strategy,
)

# Constraints/sub-goals mentioning any of these are treated as explicit guardrails.
_GUARDRAIL_WORDS = (
    "valid",
    "cas limite",
    "edge",
    "erreur",
    "error",
    "exception",
    "sécur",
    "secur",
    "test",
    "fallback",
    "timeout",
    "robuste",
)

_LABELS = {
    "clarity": "Clarté",
    "completeness": "Complétude",
    "specificity": "Spécificité",
    "robustness": "Robustesse",
    "executability": "Exécutabilité",
    "context_quality": "Qualité du contexte",
    "output_definition": "Définition de la sortie",
    "ambiguity_handling": "Gestion des ambiguïtés",
}


def _dim(
    key: str,
    level: DiagnosticLevel,
    detail: str,
    *,
    reason: str | None = None,
    recommendation: str | None = None,
) -> DiagnosticDimension:
    # reason/recommendation are only meaningful when the axis is weak.
    if level == "high":
        reason, recommendation = None, None
    return DiagnosticDimension(
        dimension=key,
        label=_LABELS[key],
        level=level,
        detail=detail,
        reason=reason,
        recommendation=recommendation,
    )


def _truncate(items: list[str], n: int = 3) -> str:
    head = "; ".join(items[:n])
    return head + (" …" if len(items) > n else "")


class DiagnosticEngine:
    def assess(
        self,
        catr: CanonicalAITask,
        ambiguity: AmbiguityReport,
        *,
        complexity: ComplexityAssessment | None = None,
        strategy: Strategy | None = None,
        route: RouteDecision | None = None,
        output_format: str = "markdown",
    ) -> list[DiagnosticDimension]:
        return [
            self._clarity(ambiguity),
            self._completeness(catr),
            self._specificity(catr),
            self._robustness(catr),
            self._executability(catr, complexity, strategy, route),
            self._context_quality(catr, strategy),
            self._output_definition(catr, output_format),
            self._ambiguity_handling(catr, ambiguity),
        ]

    # ── 1. clarity ───────────────────────────────────────────────────────────────
    def _clarity(self, ambiguity: AmbiguityReport) -> DiagnosticDimension:
        by = {"CRITICAL": 0, "IMPORTANT": 0, "OPTIONAL": 0}
        for f in ambiguity.findings:
            by[f.severity] += 1
        detail = (
            f"{by['CRITICAL']} critique(s), {by['IMPORTANT']} importante(s), "
            f"{by['OPTIONAL']} optionnelle(s)"
        )
        if by["CRITICAL"]:
            return _dim(
                "clarity",
                "low",
                detail,
                reason="des ambiguïtés critiques empêchent une exécution fiable",
                recommendation=(
                    "Réponds aux questions de clarification avant de compiler : "
                    + _truncate(ambiguity.questions)
                    if ambiguity.questions
                    else "Lève les ambiguïtés critiques signalées."
                ),
            )
        if by["IMPORTANT"]:
            return _dim(
                "clarity",
                "medium",
                detail,
                reason="des points importants restent ambigus",
                recommendation="Précise les éléments importants pour réduire le risque d'erreur.",
            )
        return _dim("clarity", "high", detail)

    # ── 2. completeness ──────────────────────────────────────────────────────────
    def _completeness(self, catr: CanonicalAITask) -> DiagnosticDimension:
        missing = catr.missing_information
        labels = [m.label for m in missing]
        has_critical = any(m.importance == "high" for m in missing)
        if not missing:
            return _dim("completeness", "high", "toutes les informations clés sont présentes")
        level: DiagnosticLevel = "low" if (has_critical or len(missing) > 2) else "medium"
        return _dim(
            "completeness",
            level,
            f"{len(missing)} information(s) manquante(s)",
            reason="manque : " + _truncate(labels),
            recommendation="Fournis : " + _truncate(labels),
        )

    # ── 3. specificity ───────────────────────────────────────────────────────────
    def _specificity(self, catr: CanonicalAITask) -> DiagnosticDimension:
        present = {
            "entrées": bool(catr.inputs),
            "contraintes": bool(catr.constraints),
            "sortie attendue": bool(catr.expected_output),
        }
        score = sum(present.values())
        absent = [name for name, ok in present.items() if not ok]
        if score >= 2:
            return _dim("specificity", "high", "entrées / contraintes / sortie bien définies")
        level: DiagnosticLevel = "medium" if score == 1 else "low"
        return _dim(
            "specificity",
            level,
            f"{score}/3 éléments concrets fournis",
            reason="peu de détails concrets — absents : " + ", ".join(absent),
            recommendation="Ajoute des " + ", ".join(absent) + " concrètes.",
        )

    # ── 4. robustness ────────────────────────────────────────────────────────────
    def _robustness(self, catr: CanonicalAITask) -> DiagnosticDimension:
        blob = " ".join(catr.constraints + catr.sub_goals + ([catr.expected_output or ""])).lower()
        has_guardrails = any(w in blob for w in _GUARDRAIL_WORDS)
        if catr.risk == "low":
            return _dim("robustness", "high", "risque faible")
        if has_guardrails:
            return _dim(
                "robustness",
                "medium",
                f"risque {catr.risk}, des garde-fous sont présents",
                reason=f"risque évalué {catr.risk}",
                recommendation="Vérifie la couverture des cas limites et de la validation.",
            )
        return _dim(
            "robustness",
            "low",
            f"risque {catr.risk}, aucun garde-fou explicite",
            reason=f"risque {catr.risk} sans contraintes sur les cas limites / la validation",
            recommendation=(
                "Ajoute des contraintes sur la validation des entrées, les cas limites "
                "et la gestion d'erreurs."
            ),
        )

    # ── 5. executability ─────────────────────────────────────────────────────────
    def _executability(
        self,
        catr: CanonicalAITask,
        complexity: ComplexityAssessment | None,
        strategy: Strategy | None,
        route: RouteDecision | None,
    ) -> DiagnosticDimension:
        if route is None or complexity is None:
            return _dim(
                "executability",
                "medium",
                "à évaluer après clarification",
                reason="la tâche doit d'abord être clarifiée (aucun plan n'a été produit)",
                recommendation="Clarifie la tâche pour obtenir un plan exécutable.",
            )
        if route.primary is None:
            return _dim(
                "executability",
                "low",
                "aucun modèle éligible",
                reason="aucun modèle ne satisfait les capacités requises : "
                + _truncate(route.required_capabilities),
                recommendation=(
                    "Assouplis les capacités requises ou ajoute un modèle adéquat au registre."
                ),
            )
        needs_decomposition = complexity.level in {"complex", "agentic"} and not catr.sub_goals
        if needs_decomposition:
            return _dim(
                "executability",
                "medium",
                f"modèle {route.primary} éligible, mais tâche {complexity.level} non décomposée",
                reason="une tâche complexe/agentique sans sous-objectifs est difficile à exécuter",
                recommendation="Décompose la tâche en sous-objectifs explicites.",
            )
        strat = strategy.kind if strategy else "single"
        return _dim("executability", "high", f"modèle {route.primary} éligible, stratégie {strat}")

    # ── 6. context_quality ───────────────────────────────────────────────────────
    def _context_quality(
        self, catr: CanonicalAITask, strategy: Strategy | None
    ) -> DiagnosticDimension:
        n = len(catr.context)
        if strategy is not None and strategy.kind == "rag" and n == 0:
            return _dim(
                "context_quality",
                "low",
                "stratégie RAG mais aucune source fournie",
                reason="une stratégie RAG exige au moins une source/contexte",
                recommendation="Fournis la ou les source(s) à utiliser pour l'ancrage.",
            )
        if n == 0:
            return _dim(
                "context_quality",
                "medium",
                "aucun contexte fourni",
                reason="aucun contexte — la sortie s'appuiera uniquement sur l'objectif",
                recommendation="Ajoute du contexte (exemples, règles métier) si pertinent.",
            )
        return _dim("context_quality", "high", f"{n} élément(s) de contexte fourni(s)")

    # ── 7. output_definition ─────────────────────────────────────────────────────
    def _output_definition(self, catr: CanonicalAITask, output_format: str) -> DiagnosticDimension:
        fmt = output_format.strip().lower()
        if catr.expected_output:
            return _dim("output_definition", "high", f"sortie attendue définie (format : {fmt})")
        if fmt not in ("", "markdown", "text"):
            return _dim(
                "output_definition",
                "medium",
                f"format {fmt} demandé, mais contenu attendu non décrit",
                reason="le format est connu mais le contenu attendu ne l'est pas",
                recommendation="Décris ce que la sortie doit contenir (et un schéma si JSON).",
            )
        return _dim(
            "output_definition",
            "low",
            "aucun format ni contenu de sortie explicite",
            reason="ni format précis ni description du contenu attendu",
            recommendation="Précise le format et le contenu attendus de la sortie.",
        )

    # ── 8. ambiguity_handling ────────────────────────────────────────────────────
    def _ambiguity_handling(
        self, catr: CanonicalAITask, ambiguity: AmbiguityReport
    ) -> DiagnosticDimension:
        n = len(catr.ambiguities)
        if n == 0:
            return _dim("ambiguity_handling", "high", "aucune ambiguïté résiduelle")
        surfaced = ambiguity.decision == "ASK"
        level: DiagnosticLevel = "low" if n > 2 else "medium"
        state = "signalées pour clarification" if surfaced else "non bloquantes mais présentes"
        return _dim(
            "ambiguity_handling",
            level,
            f"{n} ambiguïté(s) {state}",
            reason="ambiguïtés : " + _truncate(catr.ambiguities),
            recommendation="Clarifie ou documente ces ambiguïtés avant l'exécution.",
        )
