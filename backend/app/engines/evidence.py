"""Evidence Engine — classify a task's material into evidence classes (deterministic).

Reads the CATR (+ the chosen strategy) and sorts every known piece of material into an
evidence class with its source, builds the canonical source-of-truth hierarchy and the
evidence policy the Prompt Compiler weaves into the prompt. See ``schemas.evidence`` for
the honesty stance: conservative by design — it promotes nothing to a verified fact.

The policy it emits is content-aware: it always carries the four labelling/citation
rules, adds a "lean on the sources" line when the task is grounded (RAG or user context),
and names the task's actual unknowns so the model knows exactly what NOT to fabricate.
Weaving this into the prompt is also the measurable payoff: ``has_evidence_policy`` then
holds, so the PQS ``evidence_discipline`` axis rises on the professional/expert renders.
"""

from __future__ import annotations

from app.schemas.catr import CanonicalAITask
from app.schemas.evidence import EvidenceItem, EvidenceReport
from app.schemas.strategize import Strategy

# The canonical source-of-truth order (highest trust first). Stated in full on every
# report — it is the policy, independent of what this particular task happens to contain.
_HIERARCHY: tuple[str, ...] = (
    "1. Sources externes récupérées et citées (corpus RAG) — vérifiables, à citer.",
    "2. Éléments fournis par l'utilisateur — tenus pour acquis (hypothèses de travail), "
    "non vérifiés par le moteur.",
    "3. Connaissances propres du modèle — à étiqueter comme inférence/hypothèse, "
    "jamais présentées comme un fait.",
    "4. Lacunes connues — à signaler comme inconnues, jamais à inventer.",
)

# The four rules that hold for every compiled prompt.
_BASE_POLICY: tuple[str, ...] = (
    "Étiquette chaque affirmation : fait / inférence / hypothèse / inconnu.",
    "Cite la source de tout fait ; une affirmation non sourcée est une inférence, pas un fait.",
    "Ne présente jamais une hypothèse ou une inférence comme un fait établi.",
    "Signale explicitement ce qui est inconnu ou manquant plutôt que de l'inventer.",
)

_NOTE = (
    "Classification déterministe et conservatrice : le moteur ne promeut rien au rang de "
    "fait vérifié. Les éléments fournis sont des hypothèses de travail (non vérifiées), les "
    "lacunes sont des inconnues à ne pas combler par invention. Aucun algorithme ne garantit "
    "l'exactitude si l'information source est fausse, incomplète ou ambiguë."
)

_MAX_UNKNOWNS_IN_PROMPT = 3  # keep the injected list short; the full list is in the report


def _trim(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class EvidenceEngine:
    """Classify CATR material into evidence classes and emit the evidence policy."""

    def assess(self, catr: CanonicalAITask, strategy: Strategy | None = None) -> EvidenceReport:
        grounded = bool(catr.context) or bool(catr.inputs)
        is_rag = strategy is not None and strategy.kind == "rag"

        items: list[EvidenceItem] = []

        # The model's own knowledge is the default source for everything not grounded — it
        # must be labelled, never asserted. One explicit item keeps that source visible.
        items.append(
            EvidenceItem(
                statement=_trim(f"Traitement de : « {catr.objective} »"),
                evidence_class="inference",
                source="model_knowledge",
                confidence="low",
                note="À étiqueter comme inférence/hypothèse ; ne jamais présenter comme un fait.",
            )
        )

        # User-provided context and inputs are operating ASSUMPTIONS — we did not verify them.
        ctx_note = (
            "Donnée fournie, tenue pour acquise mais non vérifiée ; à citer si réutilisée."
            if not is_rag
            else "Donnée fournie ; la récupération RAG fournira des sources citables à l'exécution."
        )
        for raw in [*catr.context, *catr.inputs]:
            items.append(
                EvidenceItem(
                    statement=_trim(raw),
                    evidence_class="assumption",
                    source="user_provided",
                    confidence="medium",
                    note=ctx_note,
                )
            )

        # Known gaps: missing information + unresolved ambiguities are explicit UNKNOWNs.
        unknowns: list[str] = []
        for mi in catr.missing_information:
            label = _trim(mi.label)
            unknowns.append(label)
            items.append(
                EvidenceItem(
                    statement=label,
                    evidence_class="unknown",
                    source="gap",
                    confidence="low",
                    note=f"Information manquante (importance {mi.importance}) — à ne pas inventer.",
                )
            )
        for amb in catr.ambiguities:
            label = _trim(amb)
            unknowns.append(label)
            items.append(
                EvidenceItem(
                    statement=label,
                    evidence_class="unknown",
                    source="gap",
                    confidence="low",
                    note="Ambiguïté non levée — à clarifier, pas à trancher par invention.",
                )
            )

        # Build the policy: the four base rules, a grounding line when relevant, and the
        # task's actual unknowns so the model knows precisely what not to fabricate.
        policy: list[str] = list(_BASE_POLICY)
        if is_rag:
            policy.append(
                "Appuie-toi en priorité sur les sources récupérées et cite-les ; "
                "à défaut de source, dis-le."
            )
        elif grounded:
            policy.append(
                "Appuie-toi d'abord sur les éléments fournis ; "
                "ne les contredis pas sans le signaler."
            )
        if unknowns:
            shown = "; ".join(unknowns[:_MAX_UNKNOWNS_IN_PROMPT])
            policy.append(f"Éléments actuellement inconnus, à ne pas inventer : {shown}.")

        n_assume = sum(1 for i in items if i.evidence_class == "assumption")
        summary = (
            f"{len(items)} élément(s) classés "
            f"({n_assume} hypothèse(s) de travail, {len(unknowns)} inconnue(s)) ; "
            "politique de preuve tissée dans le prompt."
        )

        return EvidenceReport(
            items=items,
            hierarchy=list(_HIERARCHY),
            policy=policy,
            unknowns=unknowns,
            injected=bool(policy),
            summary=summary,
            note=_NOTE,
        )
