"""Model Adapter Engine (bloc F) — per-family portability layer.

Deterministic. The compiled prompt is model-INDEPENDENT (the Task Contract guarantees it).
On top of it, this engine adds a thin, *swappable* set of family-specific directives for the
chosen target model, and reports how to port the same prompt to every family it knows —
operationalising Ambro's rule: **never hardcode a vendor**.

Family conventions are DATA (``_FAMILIES``, a table keyed by family). The logic reads the
table; it never branches on a specific vendor in an if/else. Family detection reads the
registry ``provider`` field first, then the model name as tokens, then falls back to a
portable ``generic`` default (fail-safe).

Honesty (Ambro's north star — fiabiliser le processus, jamais promettre l'infaillibilité):
these are GENERAL, broadly-documented family conventions, not model-specific guarantees.
They tune only how the model is addressed (delimiters, system message, reasoning hints),
never WHAT the prompt asks for, and must be re-verified against each model's current docs.
"""

from __future__ import annotations

from app.schemas.model_adapter import FamilyPort, ModelAdapterReport
from app.schemas.registry import ModelCapability

# ── Family conventions table (DATA — read, never hardcoded into branching logic) ─────
# Each entry: human label, the directives that would be woven for that family, and a
# one-line porting note. `directives` MUST NOT contain a forced chain-of-thought ("step
# by step" / "étape par étape") — that is an efficiency anti-pattern on a strong reasoner
# (see prompt_scorer.forced_cot) and the adapter must stay consistent with it.
_FAMILIES: dict[str, FamilyPort] = {
    "anthropic": FamilyPort(
        family="anthropic",
        label="Anthropic (Claude)",
        directives=[
            "Délimite le contexte et les données avec des balises XML "
            "(`<context>…</context>`) : Claude suit fidèlement des sections balisées."
        ],
        porting_note="Préfère des sections balisées en XML et des rôles explicites.",
    ),
    "openai": FamilyPort(
        family="openai",
        label="OpenAI (GPT)",
        directives=[
            "Place les instructions de rôle dans un message système concis ; pour une "
            "sortie structurée, exige un JSON strict conforme au schéma."
        ],
        porting_note="Message système court ; mode JSON strict pour le structuré.",
    ),
    "google": FamilyPort(
        family="google",
        label="Google (Gemini)",
        directives=[
            "Donne des instructions explicites et numérotées, et précise sans ambiguïté "
            "le format de sortie attendu."
        ],
        porting_note="Instructions numérotées explicites ; format de sortie non ambigu.",
    ),
    "deepseek": FamilyPort(
        family="deepseek",
        label="DeepSeek",
        directives=[
            "Garde le prompt concis ; pour un modèle de raisonnement (série R), ne "
            "sur-spécifie pas le raisonnement — il raisonne nativement."
        ],
        porting_note="Prompt concis ; ne pas sur-piloter le raisonnement des modèles R.",
    ),
    "qwen": FamilyPort(
        family="qwen",
        label="Qwen",
        directives=[
            "Fournis un prompt système clair et des marqueurs d'instruction explicites ; "
            "indique la langue de sortie attendue."
        ],
        porting_note="Prompt système clair ; préciser la langue de sortie.",
    ),
    "mistral": FamilyPort(
        family="mistral",
        label="Mistral",
        directives=[
            "Donne des instructions directes et concises, en séparant clairement les "
            "consignes des données."
        ],
        porting_note="Instructions directes ; séparer nettement consignes et données.",
    ),
    "meta": FamilyPort(
        family="meta",
        label="Meta (Llama)",
        directives=[
            "Respecte le gabarit système/instruction du modèle et sois explicite sur le "
            "format de sortie attendu."
        ],
        porting_note="Respecter le gabarit de prompt ; être explicite sur le format.",
    ),
    "generic": FamilyPort(
        family="generic",
        label="Générique / portable",
        directives=[],  # nothing family-specific — the portable base stands on its own
        porting_note="Portable tel quel ; aucune convention de famille spécifique requise.",
    ),
}

# Provider (registry field) → family. Read as DATA.
_FAMILY_BY_PROVIDER: dict[str, str] = {
    "anthropic": "anthropic",
    "openai": "openai",
    "azure-openai": "openai",
    "google": "google",
    "google-vertex": "google",
    "vertex": "google",
    "deepseek": "deepseek",
    "qwen": "qwen",
    "alibaba": "qwen",
    "mistral": "mistral",
    "meta": "meta",
}
# Fallback: a token in the model name → family (only when the provider is unknown).
_FAMILY_BY_NAME_TOKEN: tuple[tuple[str, str], ...] = (
    ("claude", "anthropic"),
    ("gpt", "openai"),
    ("o1", "openai"),
    ("o3", "openai"),
    ("gemini", "google"),
    ("deepseek", "deepseek"),
    ("qwen", "qwen"),
    ("mixtral", "mistral"),
    ("mistral", "mistral"),
    ("llama", "meta"),
)
# Name tokens that signal a native-reasoning variant (never force chain-of-thought).
_REASONING_NAME_TOKENS: tuple[str, ...] = ("o1", "o3", "-r1", "r1-", "reasoner", "thinking")

_NOTE = (
    "Conventions de famille GÉNÉRALES et déterministes, pas des garanties propres à un "
    "modèle : elles ajustent seulement la façon d'adresser le modèle (délimiteurs, message "
    "système, indices de raisonnement), jamais CE que le prompt demande. À re-vérifier dans "
    "la documentation à jour de chaque modèle. Le prompt de base reste indépendant du modèle."
)
_PORTABILITY = (
    "Le prompt compilé est indépendant du modèle ; cette couche d'adaptation est fine et "
    "interchangeable — porter vers une autre famille ne change que ces quelques directives."
)


def _detect_family(profile: ModelCapability) -> str:
    provider = (profile.provider or "").strip().lower()
    if provider in _FAMILY_BY_PROVIDER:
        return _FAMILY_BY_PROVIDER[provider]
    name = profile.model.lower()
    for token, family in _FAMILY_BY_NAME_TOKEN:
        if token in name:
            return family
    return "generic"


def _is_reasoning_native(profile: ModelCapability) -> bool:
    # Consistent with prompt_scorer.forced_cot: a strong reasoner (rank >= 3) should not be
    # told to "think step by step"; so should a model whose name marks a reasoning variant.
    if profile.reasoning_rank >= 3:
        return True
    name = profile.model.lower()
    return any(tok in name for tok in _REASONING_NAME_TOKENS)


class ModelAdapterEngine:
    """Pick the target's family adaptation + the full portability map (deterministic)."""

    def adapt(self, profile: ModelCapability | None) -> ModelAdapterReport:
        known = list(_FAMILIES.values())
        if profile is None:
            # No model resolved → nothing to adapt; stay portable and say so.
            generic = _FAMILIES["generic"]
            return ModelAdapterReport(
                target_model=None,
                provider=None,
                family="generic",
                label=generic.label,
                reasoning_native=False,
                directives=[],
                injected=False,
                portability_note=_PORTABILITY,
                known_families=known,
                note=_NOTE,
            )

        family = _detect_family(profile)
        port = _FAMILIES[family]
        return ModelAdapterReport(
            target_model=profile.model,
            provider=profile.provider,
            family=family,
            label=port.label,
            reasoning_native=_is_reasoning_native(profile),
            directives=list(port.directives),
            injected=False,  # set by the core once the compiler confirms the section landed
            portability_note=_PORTABILITY,
            known_families=known,
            note=_NOTE,
        )


def adapter_prompt_lines(report: ModelAdapterReport) -> list[str]:
    """The family-tuned directives woven into the prompt for the chosen target.

    Empty for the portable ``generic`` family (and when no model is resolved) — nothing
    family-specific worth adding. Kept short so the PQS ``efficiency`` axis is unaffected.
    """
    return list(report.directives)
