"""Prompt Quality Score (PQS) — a deterministic, explainable *readiness* score of a
compiled prompt (PPOA step 16).

Eleven weighted axes (weights sum to 100), each scored in [0, 1] from measurable signals
on the CATR + the compiled prompt + the route. Every axis keeps the diagnostic's
contract: a level (low/medium/high) and, when weak, a reason + a concrete recommendation.
The composite is a *readiness* score, NOT a prediction of answer correctness — see
``schemas.prompt_quality``.

The signal helpers (``has_evidence_policy``, ``vague_terms``, …) are the single source of
truth for "what the prompt already contains"; the review and repair engines import them so
the three stages never drift apart.
"""

from __future__ import annotations

from app.schemas.catr import CanonicalAITask
from app.schemas.prompt_quality import (
    BAND_EXECUTION_READY,
    BAND_STRONG,
    BAND_USABLE,
    RELEASE_GATE,
    PqsBand,
    PqsDimension,
    ReadinessLevel,
)
from app.schemas.registry import ModelCapability
from app.schemas.strategize import AmbiguityReport, ComplexityAssessment, RouteDecision

# ── Weights (sum = 100). Reconciles Framework §18 + CDC Appendix C. ──────────────────
WEIGHTS: dict[str, int] = {
    "intent_clarity": 18,
    "context_sufficiency": 14,
    "evidence_discipline": 14,
    "constraint_completeness": 10,
    "success_criteria": 10,
    "validation_strength": 12,
    "instruction_clarity": 8,
    "output_fitness": 6,
    "scope_discipline": 4,
    "model_fit": 2,
    "efficiency": 2,
}
assert sum(WEIGHTS.values()) == 100  # a wrong total would silently skew every PQS

_LABELS: dict[str, str] = {
    "intent_clarity": "Clarté de l'intention",
    "context_sufficiency": "Suffisance du contexte",
    "evidence_discipline": "Discipline de preuve",
    "constraint_completeness": "Complétude des contraintes",
    "success_criteria": "Critères de succès",
    "validation_strength": "Force de validation",
    "instruction_clarity": "Clarté des instructions",
    "output_fitness": "Adéquation de la sortie",
    "scope_discipline": "Discipline de périmètre",
    "model_fit": "Adéquation du modèle",
    "efficiency": "Efficacité",
}

# Vague qualifiers that must be given a measurable/operational meaning (Framework §3.3).
_VAGUE_TERMS: tuple[str, ...] = (
    "temps réel",
    "real-time",
    "realtime",
    "scalable",
    "évolutif",
    "sécurisé",
    "secure",
    "production-ready",
    "prêt pour la production",
    "exact",
    "précis",
    "accurate",
    "autonome",
    "autonomous",
    "optimal",
    "optimale",
    "meilleur",
    "couverture complète",
    "full coverage",
)
_EVIDENCE_WORDS: tuple[str, ...] = (
    "fait",
    "inférence",
    "hypothèse",
    "incertitude",
    "source",
    "cite",
    "citation",
    "inconnu",
    "ne pas inventer",
    "sans inventer",
    "preuve",
)
_VALIDATION_WORDS: tuple[str, ...] = (
    "valid",
    "vérifi",
    "verify",
    "test",
    "contrôle",
    "auto-vérif",
)
_SUCCESS_WORDS: tuple[str, ...] = (
    "critère",
    "succès",
    "acceptation",
    "acceptance",
    "success",
    "objectif atteint",
)
_MIN_RANK_BY_LEVEL: dict[str, int] = {"simple": 1, "moderate": 2, "complex": 3, "agentic": 4}


# ── Shared signal helpers (single source of truth; reused by review + repair) ────────
def context_count(catr: CanonicalAITask) -> int:
    return len(catr.context) + len(catr.inputs)


def _blob(catr: CanonicalAITask, quality_contract: list[str]) -> str:
    return " ".join([catr.objective, *catr.constraints, *catr.sub_goals, *quality_contract]).lower()


def has_evidence_policy(prompt_text: str) -> bool:
    low = prompt_text.lower()
    return any(w in low for w in _EVIDENCE_WORDS)


def has_validation(prompt_text: str, section_names: list[str], quality_contract: list[str]) -> bool:
    if "validation" in section_names:
        return True
    low = prompt_text.lower() + " " + " ".join(quality_contract).lower()
    return any(w in low for w in _VALIDATION_WORDS)


def has_success_signal(
    catr: CanonicalAITask, quality_contract: list[str], section_names: list[str]
) -> bool:
    if catr.expected_output or quality_contract or "validation" in section_names:
        return True
    return any(w in _blob(catr, quality_contract) for w in _SUCCESS_WORDS)


def output_contract_ok(catr: CanonicalAITask, output_format: str) -> bool:
    if catr.expected_output:
        return True
    return output_format.strip().lower() not in ("", "markdown", "text")


def vague_terms(catr: CanonicalAITask) -> list[str]:
    """Vague qualifiers used WITHOUT a nearby number (i.e. not operationalized)."""
    found: list[str] = []
    for src in [catr.objective, *catr.constraints]:
        low = src.lower()
        has_number = any(ch.isdigit() for ch in src)
        for term in _VAGUE_TERMS:
            if term in low and not has_number and term not in found:
                found.append(term)
    return found


def forced_cot(profile: ModelCapability | None, prompt_text: str) -> bool:
    """A forced chain-of-thought instruction on a strong reasoner is an anti-pattern
    (Framework §19): the model already reasons; the instruction adds noise."""
    if profile is None or profile.reasoning_rank < 3:
        return False
    low = prompt_text.lower()
    return "step by step" in low or "étape par étape" in low


# ── Dimension assembly ───────────────────────────────────────────────────────────────
def _level(score: float) -> ReadinessLevel:
    if score >= 0.75:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


def _dim(
    key: str,
    score: float,
    detail: str,
    *,
    reason: str | None = None,
    recommendation: str | None = None,
) -> PqsDimension:
    score = max(0.0, min(1.0, score))
    weight = WEIGHTS[key]
    level = _level(score)
    if level == "high":
        reason, recommendation = None, None
    return PqsDimension(
        dimension=key,
        label=_LABELS[key],
        weight=weight,
        score=round(score, 3),
        points=round(weight * score, 2),
        level=level,
        detail=detail,
        reason=reason,
        recommendation=recommendation,
    )


def score_dimensions(
    *,
    catr: CanonicalAITask,
    prompt_text: str,
    section_names: list[str],
    route: RouteDecision,
    complexity: ComplexityAssessment,
    profile: ModelCapability | None,
    ambiguity: AmbiguityReport,
    output_format: str,
    quality_contract: list[str],
) -> list[PqsDimension]:
    dims: list[PqsDimension] = []

    # 1. intent_clarity — penalize residual IMPORTANT ambiguities + a thin objective.
    important = sum(1 for f in ambiguity.findings if f.severity == "IMPORTANT")
    s = 1.0 - 0.2 * important - 0.1 * len(catr.ambiguities)
    if len(catr.objective.strip()) < 15:
        s = min(s, 0.5)
    dims.append(
        _dim(
            "intent_clarity",
            s,
            f"{important} point(s) important(s) ambigu(s), {len(catr.ambiguities)} ambiguïté(s)",
            reason="des ambiguïtés abaissent la clarté de l'objectif",
            recommendation="Précise l'objectif et lève les ambiguïtés importantes.",
        )
    )

    # 2. context_sufficiency — relative to complexity.
    n_ctx = context_count(catr)
    need = {"simple": 0, "moderate": 1, "complex": 2, "agentic": 2}.get(complexity.level, 1)
    s = 1.0 if n_ctx >= need else (0.6 if n_ctx >= 1 else (0.7 if need == 0 else 0.3))
    dims.append(
        _dim(
            "context_sufficiency",
            s,
            f"{n_ctx} élément(s) de contexte pour une tâche {complexity.level}",
            reason="peu de contexte pertinent pour le niveau de complexité",
            recommendation="Ajoute le contexte/les entrées que la tâche suppose.",
        )
    )

    # 3. evidence_discipline — the honest gap: the compiled prompt rarely labels
    #    fact/inference/assumption/unknown or cites sources today.
    s = 0.2
    if has_evidence_policy(prompt_text):
        s += 0.45
    if any(w in _blob(catr, quality_contract) for w in ("source", "cite", "référence", "preuve")):
        s += 0.35
    dims.append(
        _dim(
            "evidence_discipline",
            s,
            "présence d'une politique de preuve/incertitude dans le prompt",
            reason="le prompt ne distingue pas faits / inférences / hypothèses / inconnus",
            recommendation=(
                "Injecte une consigne : étiqueter faits/inférences/hypothèses, citer les "
                "sources, ne jamais présenter une hypothèse comme un fait."
            ),
        )
    )

    # 4. constraint_completeness.
    if catr.constraints:
        s = 1.0
    elif catr.risk == "low":
        s = 0.6
    else:
        s = 0.3
    dims.append(
        _dim(
            "constraint_completeness",
            s,
            f"{len(catr.constraints)} contrainte(s), risque {catr.risk}",
            reason="peu ou pas de contraintes pour un risque non faible",
            recommendation="Ajoute les contraintes (temps, techno, règles, cas limites).",
        )
    )

    # 5. success_criteria.
    s = 0.0
    if catr.expected_output:
        s += 0.4
    if quality_contract:
        s += 0.4
    if "validation" in section_names:
        s += 0.2
    dims.append(
        _dim(
            "success_criteria",
            s,
            "présence d'une sortie attendue / d'un contrat qualité",
            reason="aucun critère de succès observable n'est défini",
            recommendation="Définis ce qui rend le résultat acceptable (mesurable si possible).",
        )
    )

    # 6. validation_strength.
    s = 0.2
    if "validation" in section_names:
        s += 0.5
    if any(
        w in (" ".join(quality_contract) + " " + " ".join(catr.constraints)).lower()
        for w in _VALIDATION_WORDS
    ):
        s += 0.3
    dims.append(
        _dim(
            "validation_strength",
            s,
            "présence d'une consigne de validation",
            reason="aucun moyen de vérifier le résultat n'est prévu",
            recommendation="Ajoute une étape de validation / auto-vérification de la sortie.",
        )
    )

    # 7. instruction_clarity — unoperationalized vague terms.
    vt = vague_terms(catr)
    s = 1.0 - 0.25 * len(vt)
    detail = "aucun terme vague non défini" if not vt else "termes vagues : " + ", ".join(vt[:4])
    dims.append(
        _dim(
            "instruction_clarity",
            s,
            detail,
            reason="des termes vagues ne sont pas définis de façon mesurable",
            recommendation="Donne une définition mesurable des termes vagues (ex. « rapide »).",
        )
    )

    # 8. output_fitness.
    if catr.expected_output:
        s = 1.0
    elif output_format.strip().lower() not in ("", "markdown", "text"):
        s = 0.7
    else:
        s = 0.5
    out_state = "définie" if catr.expected_output else "non décrite"
    dims.append(
        _dim(
            "output_fitness",
            s,
            f"format « {output_format} », sortie attendue {out_state}",
            reason="le contenu attendu de la sortie n'est pas décrit",
            recommendation="Décris le contenu attendu (et un schéma si JSON).",
        )
    )

    # 9. scope_discipline — thin today (CATR has no out_of_scope): honest low ceiling.
    s = 0.4 + (0.3 if catr.sub_goals else 0.0) + (0.1 if catr.constraints else 0.0)
    dims.append(
        _dim(
            "scope_discipline",
            s,
            "périmètre borné par des sous-objectifs/contraintes",
            reason="les limites (hors-périmètre) ne sont pas explicites",
            recommendation="Énonce ce qui est hors périmètre pour éviter la dérive.",
        )
    )

    # 10. model_fit.
    min_rank = _MIN_RANK_BY_LEVEL.get(complexity.level, 2)
    if profile is None:
        s = 0.2
    elif profile.reasoning_rank >= min_rank:
        s = 1.0
    else:
        s = 0.5
    dims.append(
        _dim(
            "model_fit",
            s,
            f"modèle {route.primary or 'aucun'} pour une tâche {complexity.level}",
            reason="aucun modèle éligible ne couvre le niveau requis",
            recommendation="Ajoute un modèle adéquat au registre ou assouplis les exigences.",
        )
    )

    # 11. efficiency — penalize forced CoT on a strong reasoner + prompt bloat.
    s = 1.0
    if forced_cot(profile, prompt_text):
        s -= 0.5
    if len(prompt_text) > 4000 and complexity.level in ("simple", "moderate"):
        s -= 0.3
    dims.append(
        _dim(
            "efficiency",
            s,
            "pas d'anti-pattern d'efficacité détecté" if s >= 0.75 else "anti-pattern détecté",
            reason="chain-of-thought forcé sur un fort raisonneur, ou prompt trop long",
            recommendation="Évite « étape par étape » sur un fort raisonneur ; resserre le prompt.",
        )
    )

    return dims


def composite(dimensions: list[PqsDimension]) -> tuple[int, PqsBand, bool]:
    """Weighted composite in [0, 100], its band, and whether it passes the release gate."""
    pqs = round(sum(d.points for d in dimensions))
    pqs = max(0, min(100, pqs))
    if pqs >= BAND_EXECUTION_READY:
        band: PqsBand = "execution_ready"
    elif pqs >= BAND_STRONG:
        band = "strong"
    elif pqs >= BAND_USABLE:
        band = "usable"
    else:
        band = "insufficient"
    return pqs, band, pqs >= RELEASE_GATE
