"""Adversarial review (PPOA step 15) — deterministic critical challenge of a compiled
prompt.

Applies the Framework's critical-challenge questions (§7.2), the preflight gate (§17.1)
and the anti-patterns (§19) as rules, producing actionable findings. It reuses the signal
helpers from ``prompt_scorer`` so a finding and its matching low PQS axis never disagree.
Findings drive the repair stage; they are the "what to fix" list behind the score.
"""

from __future__ import annotations

from app.engines import prompt_scorer as sig
from app.schemas.catr import CanonicalAITask
from app.schemas.prompt_quality import AdversarialFinding
from app.schemas.registry import ModelCapability

# Objectives that read like a decision/comparison and therefore need explicit criteria.
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
)


def review(
    *,
    catr: CanonicalAITask,
    prompt_text: str,
    section_names: list[str],
    profile: ModelCapability | None,
    output_format: str,
    quality_contract: list[str],
) -> list[AdversarialFinding]:
    findings: list[AdversarialFinding] = []

    if catr.ambiguities:
        findings.append(
            AdversarialFinding(
                kind="unresolved_ambiguity",
                severity="medium",
                label="Ambiguïtés résiduelles",
                detail="; ".join(catr.ambiguities[:3]),
                recommendation="Clarifie ou documente ces ambiguïtés avant l'exécution.",
            )
        )

    if not sig.has_success_signal(catr, quality_contract, section_names):
        findings.append(
            AdversarialFinding(
                kind="missing_success_criteria",
                severity="medium",
                label="Critères de succès absents",
                detail="rien ne définit ce qui rend le résultat acceptable",
                recommendation="Ajoute des critères de succès observables (mesurables).",
            )
        )

    if not sig.has_validation(prompt_text, section_names, quality_contract):
        findings.append(
            AdversarialFinding(
                kind="missing_validation",
                severity="high" if catr.risk == "high" else "medium",
                label="Validation absente",
                detail="aucun moyen de vérifier la sortie n'est prévu",
                recommendation="Ajoute une étape de validation / auto-vérification de la sortie.",
            )
        )

    if not sig.has_evidence_policy(prompt_text):
        findings.append(
            AdversarialFinding(
                kind="missing_evidence_policy",
                severity="medium",
                label="Politique de preuve absente",
                detail="le prompt ne distingue pas faits / inférences / hypothèses / inconnus",
                recommendation=(
                    "Injecte une consigne d'étiquetage des preuves et de citation des sources ; "
                    "interdis de présenter une hypothèse comme un fait."
                ),
            )
        )

    vt = sig.vague_terms(catr)
    if vt:
        findings.append(
            AdversarialFinding(
                kind="vague_term",
                severity="low",
                label="Termes vagues non définis",
                detail="; ".join(vt[:5]),
                recommendation="Donne une définition mesurable de chaque terme vague.",
            )
        )

    if not sig.output_contract_ok(catr, output_format):
        findings.append(
            AdversarialFinding(
                kind="missing_output_contract",
                severity="medium",
                label="Contrat de sortie absent",
                detail="ni format précis ni contenu de sortie décrit",
                recommendation="Précise le format et le contenu attendus (schéma si JSON).",
            )
        )

    if sig.forced_cot(profile, prompt_text):
        findings.append(
            AdversarialFinding(
                kind="forced_cot_on_reasoner",
                severity="low",
                label="Chain-of-thought forcé",
                detail="« étape par étape » imposé à un modèle déjà fort en raisonnement",
                recommendation="Retire l'instruction de raisonnement explicite (anti-pattern §19).",
            )
        )

    obj = catr.objective.lower()
    looks_like_decision = any(w in obj for w in _DECISION_WORDS)
    has_criteria = bool(catr.constraints) or any(
        w in " ".join(quality_contract).lower() for w in ("critère", "criteria")
    )
    if looks_like_decision and not has_criteria:
        findings.append(
            AdversarialFinding(
                kind="no_decision_criteria",
                severity="low",
                label="Critères de décision absents",
                detail="la tâche demande un choix sans critères de décision explicites",
                recommendation="Définis les critères (et leur pondération) avant de recommander.",
            )
        )

    return findings
