"""Deterministic prompt repair (PPOA step 17 / OPTIMIZE) — a measured keep-if-it-helps loop.

Given a compiled prompt that scored below the release gate, apply ONLY the fixes a prompt
can honestly make on its own — inject an evidence/uncertainty policy, a validation block,
and remove a forced chain-of-thought on a strong reasoner — re-scoring after each and
keeping a change only when the PQS actually rises. It stops at the gate or when no further
structural gain is possible.

Honesty: this is structural enrichment, not an LLM rewrite. It invents no facts and does
NOT fix CATR-level gaps (residual ambiguity, vague terms, a missing output contract) —
those need the *task* clarified, which the findings/recommendations say explicitly.
"""

from __future__ import annotations

from app.engines import prompt_scorer as sig
from app.engines.prompt_scorer import composite, score_dimensions
from app.schemas.catr import CanonicalAITask
from app.schemas.prompt_quality import RELEASE_GATE, PromptRepairResult
from app.schemas.registry import ModelCapability
from app.schemas.strategize import AmbiguityReport, ComplexityAssessment, RouteDecision

_EVIDENCE_BLOCK = (
    "\n\n## Preuve & incertitude\n"
    "- Distingue les faits, les inférences, les hypothèses et les inconnus.\n"
    "- Cite les sources quand elles existent ; ne présente jamais une hypothèse comme un fait.\n"
    "- Signale ce qui est inconnu plutôt que d'inventer."
)
_VALIDATION_BLOCK = (
    "\n\n## Validation\n"
    "- Avant de finaliser, vérifie : objectif atteint, contraintes respectées, "
    "hypothèses explicites.\n"
    "- Auto-vérifie la sortie contre la Mission et corrige les écarts."
)
_NOTE = (
    "Réparation déterministe et structurelle : enrichit le prompt (politique de preuve, bloc "
    "de validation, retrait d'un CoT forcé). N'invente aucun fait et ne corrige pas les manques "
    "du CATR (ambiguïtés, termes vagues, contrat de sortie) — ceux-là exigent de préciser la tâche."
)


def repair(
    *,
    catr: CanonicalAITask,
    base_prompt_text: str,
    section_names: list[str],
    route: RouteDecision,
    complexity: ComplexityAssessment,
    profile: ModelCapability | None,
    ambiguity: AmbiguityReport,
    output_format: str,
    quality_contract: list[str],
) -> PromptRepairResult:
    def measure(text: str, sections: list[str]) -> int:
        dims = score_dimensions(
            catr=catr,
            prompt_text=text,
            section_names=sections,
            route=route,
            complexity=complexity,
            profile=profile,
            ambiguity=ambiguity,
            output_format=output_format,
            quality_contract=quality_contract,
        )
        return composite(dims)[0]

    def fix_evidence(t: str, s: list[str]) -> tuple[str, list[str], str] | None:
        if sig.has_evidence_policy(t):
            return None
        return t + _EVIDENCE_BLOCK, s, "Ajout d'une politique de preuve & incertitude"

    def fix_validation(t: str, s: list[str]) -> tuple[str, list[str], str] | None:
        if "validation" in s:
            return None
        return t + _VALIDATION_BLOCK, [*s, "validation"], "Ajout d'un bloc de validation"

    def fix_cot(t: str, s: list[str]) -> tuple[str, list[str], str] | None:
        if not sig.forced_cot(profile, t):
            return None
        nt = t.replace(
            "Reason step by step before answering; state assumptions explicitly.",
            "Work carefully and state your assumptions explicitly.",
        ).replace("étape par étape", "avec rigueur")
        if nt == t:
            return None
        return nt, s, "Retrait du chain-of-thought forcé (anti-pattern sur fort raisonneur)"

    text = base_prompt_text
    sections = list(section_names)
    pqs_before = measure(text, sections)

    changes: list[str] = []
    iterations = 0
    pqs_current = pqs_before
    for fix in (fix_evidence, fix_validation, fix_cot):
        if pqs_current >= RELEASE_GATE:
            break
        res = fix(text, sections)
        if res is None:
            continue
        new_text, new_sections, desc = res
        new_pqs = measure(new_text, new_sections)
        iterations += 1
        if new_pqs <= pqs_current:
            continue  # no measurable gain → don't add noise to the prompt
        text, sections, pqs_current = new_text, new_sections, new_pqs
        changes.append(desc)

    applied = bool(changes)
    return PromptRepairResult(
        applied=applied,
        pqs_before=pqs_before,
        pqs_after=pqs_current,
        iterations=iterations,
        converged=pqs_current >= RELEASE_GATE,
        changes=changes,
        repaired_prompt=text if applied else "",
        note=_NOTE,
    )
