"""Contract Engine (PPOA step 14) — assemble a model-neutral Task Contract.

Deterministic. Derives, from the CATR + strategy/route + the evidence layer, a portable
specification of the task: scope + explicit out-of-scope boundaries, unverified assumptions,
measurable success criteria, validation steps, decision criteria (only when the objective
is a choice), the output contract, and a CAPABILITY-based model preference (never a vendor
lock). Two derived parts — ``scope`` and ``success_criteria`` — are woven into the compiled
prompt (see :func:`scope_prompt_lines` / :func:`success_prompt_lines`), which raises the PQS
``scope_discipline`` and ``success_criteria`` axes.

Honesty: the engine derives ONLY from what the task states. It invents no requirement, and
the standing out-of-scope line ("anything not listed — do not add it without validation") is
an anti-scope-creep directive, not a fabricated constraint. Gaps remain surfaced as
assumptions/unknowns rather than silently resolved.
"""

from __future__ import annotations

from app.schemas.catr import CanonicalAITask
from app.schemas.evidence import EvidenceReport
from app.schemas.registry import ModelCapability
from app.schemas.strategize import RouteDecision, Strategy
from app.schemas.task_contract import (
    ModelPreferences,
    OutputContract,
    SuccessCriterion,
    TaskContract,
)

# Objectives that read like a decision/comparison → need explicit decision criteria.
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
# Phrases that mark an explicit exclusion the user stated (→ a real out-of-scope boundary).
_EXCLUSION_MARKERS: tuple[str, ...] = (
    "sans ",
    "ne pas ",
    "pas de ",
    "exclure",
    "hors ",
    "sauf ",
    "without ",
    "no ",
    "exclude",
    "except",
)
# Structured output signals (format token or a structure word in the expected output).
_STRUCTURED_FORMATS: tuple[str, ...] = ("json", "yaml", "xml", "csv", "toml")
_STRUCTURE_WORDS: tuple[str, ...] = (
    "json",
    "schéma",
    "schema",
    "tableau",
    "table",
    "structuré",
    "structured",
    "champs",
    "fields",
)

_STANDING_OUT_OF_SCOPE = (
    "Tout élément non listé dans le périmètre ci-dessus : ne pas l'ajouter sans validation."
)
_NOTE = (
    "Contrat dérivé de la tâche telle qu'énoncée (déterministe) : il structure et borne le "
    "travail, il ne garantit pas que l'énoncé soit complet ou correct. Les manques restent "
    "signalés (hypothèses non vérifiées, inconnus). Les préférences modèle sont fondées sur "
    "les capacités requises, pas sur un fournisseur."
)


def _trim(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _dedup(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        key = it.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(it.strip())
    return out


def _scope(catr: CanonicalAITask) -> list[str]:
    scope = [f"Livrer : {_trim(catr.objective)}"]
    scope += [f"Couvrir : {_trim(g)}" for g in catr.sub_goals]
    return _dedup(scope)


def _out_of_scope(catr: CanonicalAITask) -> list[str]:
    explicit: list[str] = []
    for c in catr.constraints:
        low = c.lower()
        if any(m in low for m in _EXCLUSION_MARKERS):
            explicit.append(f"Exclusion énoncée : {_trim(c)}")
    return _dedup([*explicit, _STANDING_OUT_OF_SCOPE])


def _assumptions(catr: CanonicalAITask, evidence: EvidenceReport) -> list[str]:
    assumptions = [
        f"On suppose (non vérifié) : {_trim(i.statement)}"
        for i in evidence.items
        if i.evidence_class == "assumption"
    ]
    # Non-critical gaps the user did not have to resolve, surfaced as working assumptions.
    assumptions += [
        f"À confirmer : {_trim(m.label)}"
        for m in catr.missing_information
        if m.importance != "high"
    ]
    return _dedup(assumptions)[:6]


def _success_criteria(
    catr: CanonicalAITask, output_format: str, quality_contract: list[str]
) -> list[SuccessCriterion]:
    crit: list[SuccessCriterion] = [
        SuccessCriterion(
            statement=f"La sortie répond à l'objectif : {_trim(catr.objective)}",
            measurable=False,
            verification="Relire la sortie au regard de l'objectif énoncé.",
        )
    ]
    if catr.expected_output:
        expected = _trim(catr.expected_output)
        crit.append(
            SuccessCriterion(
                statement=f"La sortie respecte le format/contenu attendu : {expected}",
                measurable=True,
                verification="Comparer la sortie à la description du résultat attendu.",
            )
        )
    for c in catr.constraints:
        crit.append(
            SuccessCriterion(
                statement=f"Contrainte respectée : {_trim(c)}",
                measurable=True,
                verification="Vérifier explicitement la conformité à cette contrainte.",
            )
        )
    if catr.domain == "software":
        crit.append(
            SuccessCriterion(
                statement="Le code s'exécute et passe les tests associés.",
                measurable=True,
                verification="Exécuter le code et sa suite de tests.",
            )
        )
    if catr.risk in {"medium", "high"}:
        crit.append(
            SuccessCriterion(
                statement="Exactitude et effets de bord vérifiés avant livraison.",
                measurable=True,
                verification="Revue ciblée + contrôle des cas limites.",
            )
        )
    for q in quality_contract:
        crit.append(
            SuccessCriterion(
                statement=f"Exigence qualité satisfaite : {_trim(q)}",
                measurable=True,
                verification="Contrôle explicite de cette exigence.",
            )
        )
    # Dedup by statement, keep order, cap to avoid prompt bloat.
    seen: set[str] = set()
    out: list[SuccessCriterion] = []
    for sc in crit:
        key = sc.statement.lower()
        if key not in seen:
            seen.add(key)
            out.append(sc)
    return out[:8]


def _validation(catr: CanonicalAITask, quality_contract: list[str]) -> list[str]:
    checks = ["Auto-vérifier la sortie contre la Mission et les critères de réussite."]
    if catr.domain == "software":
        checks.append("Exécuter et valider les tests avant de conclure.")
    if catr.risk in {"medium", "high"}:
        checks.append("Double-contrôler l'exactitude et les effets de bord.")
    checks += [f"Contrôler : {_trim(q)}" for q in quality_contract]
    return _dedup(checks)


def _decision_criteria(catr: CanonicalAITask) -> list[str] | None:
    if not any(w in catr.objective.lower() for w in _DECISION_WORDS):
        return None
    if catr.constraints:
        return _dedup([f"Pondérer selon : {_trim(c)}" for c in catr.constraints])
    return [
        "Critères de décision à expliciter (coût, risque, délai, adéquation) avant toute "
        "recommandation ; justifier le choix au regard de ces critères."
    ]


def _output_contract(catr: CanonicalAITask, output_format: str) -> OutputContract:
    fmt = (output_format or "markdown").strip()
    low = fmt.lower()
    expected_low = (catr.expected_output or "").lower()
    structured = low in _STRUCTURED_FORMATS or any(w in expected_low for w in _STRUCTURE_WORDS)
    return OutputContract(
        format=fmt,
        structured=structured,
        schema_hint=_trim(catr.expected_output) if (structured and catr.expected_output) else None,
        model_independent=True,
    )


def _model_preferences(route: RouteDecision, profile: ModelCapability | None) -> ModelPreferences:
    caps = route.required_capabilities
    caps_txt = ", ".join(caps) if caps else "aucune capacité spécifique requise"
    rationale = (
        f"Sélection fondée sur les capacités requises ({caps_txt}), via le registre de "
        "modèles — pas sur un fournisseur imposé."
    )
    return ModelPreferences(
        primary=route.primary,
        fallbacks=list(route.fallbacks),
        required_capabilities=list(caps),
        rationale=rationale,
        portability_note=(
            "Contrat model-neutral : toute famille de modèles satisfaisant ces capacités "
            "peut l'exécuter ; le modèle primaire n'est qu'une suggestion du routeur."
        ),
    )


class ContractEngine:
    """Assemble a model-neutral Task Contract from the pipeline's deterministic outputs."""

    def build(
        self,
        *,
        catr: CanonicalAITask,
        strategy: Strategy,
        route: RouteDecision,
        profile: ModelCapability | None,
        evidence: EvidenceReport,
        output_format: str,
        quality_contract: list[str],
    ) -> TaskContract:
        return TaskContract(
            objective=catr.objective,
            domain=catr.domain,
            scope=_scope(catr),
            out_of_scope=_out_of_scope(catr),
            assumptions=_assumptions(catr, evidence),
            success_criteria=_success_criteria(catr, output_format, quality_contract),
            validation=_validation(catr, quality_contract),
            decision_criteria=_decision_criteria(catr),
            constraints=list(catr.constraints),
            output_contract=_output_contract(catr, output_format),
            model_preferences=_model_preferences(route, profile),
            note=_NOTE,
        )


def scope_prompt_lines(contract: TaskContract) -> list[str]:
    """The scope section woven into the compiled prompt (in-scope + explicit boundaries)."""
    lines: list[str] = ["Dans le périmètre :"]
    lines += [f"- {s}" for s in contract.scope]
    if contract.out_of_scope:
        lines.append("Hors périmètre :")
        lines += [f"- {s}" for s in contract.out_of_scope]
    return lines


def success_prompt_lines(contract: TaskContract) -> list[str]:
    """The success-criteria (acceptance) section woven into the compiled prompt."""
    lines: list[str] = []
    for sc in contract.success_criteria:
        tag = " (mesurable)" if sc.measurable else ""
        lines.append(f"- {sc.statement}{tag} — vérif. : {sc.verification}")
    if contract.decision_criteria:
        lines.append("Critères de décision :")
        lines += [f"- {c}" for c in contract.decision_criteria]
    return lines
