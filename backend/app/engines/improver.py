"""Improver v1 — deterministic, GROUNDED improvement suggestions.

Every suggestion is derived from a named signal the pipeline already produced — a weak
diagnostic axis, a failed evaluation criterion, missing information, or a residual
ambiguity — and records that provenance in ``derived_from``. Nothing is invented. See the
``kompilo-pipeline`` skill.
"""

from __future__ import annotations

from app.schemas.catr import CanonicalAITask
from app.schemas.compile import DiagnosticDimension
from app.schemas.evaluate import EvaluationReport
from app.schemas.improve import Improvement, ImprovementReport

# Concrete actions for a failed evaluation criterion.
_EVAL_SUGGESTION: dict[str, tuple[str, str]] = {
    "format_valid": (
        "Corriger la sortie pour respecter le format/contrat demandé.",
        "la vérification a échoué",
    ),
    "non_empty": (
        "Produire une sortie non vide et substantielle.",
        "sortie vide ou trop courte",
    ),
    "objective_coverage": (
        "Reformuler l'instruction pour traiter explicitement l'objectif.",
        "l'objectif est peu couvert par la sortie",
    ),
    "constraints_adherence": (
        "Rendre les contraintes demandées explicites dans l'instruction.",
        "des contraintes ne sont pas reflétées dans la sortie",
    ),
}


def _truncate(items: list[str], n: int = 3) -> str:
    return "; ".join(items[:n]) + (" …" if len(items) > n else "")


class Improver:
    def suggest(
        self,
        *,
        catr: CanonicalAITask,
        diagnostics: list[DiagnosticDimension],
        evaluation: EvaluationReport,
    ) -> ImprovementReport:
        improvements: list[Improvement] = []
        seen: set[tuple[str, str]] = set()

        def add(target: str, suggestion: str, rationale: str, derived_from: str) -> None:
            key = (target, derived_from)
            if key in seen:
                return
            seen.add(key)
            improvements.append(
                Improvement(
                    target=target,
                    suggestion=suggestion,
                    rationale=rationale,
                    derived_from=derived_from,
                )
            )

        # 1. Weak diagnostic axes carry their own reason + corrective action.
        for d in diagnostics:
            if d.level != "high" and d.recommendation:
                add(
                    target=d.dimension,
                    suggestion=d.recommendation,
                    rationale=d.reason or d.detail,
                    derived_from=f"diagnostic:{d.dimension}={d.level}",
                )

        # 2. Failed evaluation criteria.
        for c in evaluation.criteria:
            if not c.passed and c.name in _EVAL_SUGGESTION:
                suggestion, rationale = _EVAL_SUGGESTION[c.name]
                add(
                    target=c.name,
                    suggestion=suggestion,
                    rationale=f"{rationale} ({c.detail})",
                    derived_from=f"eval:{c.name}",
                )

        # 3. Missing information (from the CATR).
        if catr.missing_information:
            labels = [m.label for m in catr.missing_information]
            add(
                target="inputs",
                suggestion="Fournir les informations manquantes : " + _truncate(labels),
                rationale="des informations nécessaires ne sont pas encore fournies",
                derived_from="missing_information",
            )

        # 4. Residual ambiguities.
        if catr.ambiguities:
            add(
                target="ambiguities",
                suggestion="Clarifier : " + _truncate(catr.ambiguities),
                rationale="des ambiguïtés résiduelles subsistent",
                derived_from="ambiguity",
            )

        summary = (
            "aucune amélioration prioritaire — la sortie satisfait les critères mesurés"
            if not improvements
            else f"{len(improvements)} amélioration(s) suggérée(s), dérivées de signaux mesurés"
        )
        return ImprovementReport(improvements=improvements, summary=summary)
