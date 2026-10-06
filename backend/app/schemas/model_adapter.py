"""Model Adapter schema (bloc F) — per-family portability layer.

The compiled prompt is model-INDEPENDENT (the Task Contract guarantees it). The Model
Adapter adds a thin, *swappable* set of family-specific directives for the chosen target
model, and reports how to port the same prompt to every family it knows — so the output is
explicitly portable, never locked to one vendor.

Honesty: the directives are GENERAL, broadly-documented family conventions, not
model-specific guarantees; they tune only formatting/addressing, never WHAT the prompt
asks for, and must be re-verified against each model's current documentation.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FamilyPort(BaseModel):
    """How the compiled prompt ports to one model family (DATA, swappable)."""

    # `model`-prefixed field names are fine here; silence Pydantic's protected namespace.
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    family: str  # machine key, e.g. "anthropic"
    label: str  # human label, e.g. "Anthropic (Claude)"
    directives: list[str]  # family-tuned directives that WOULD be woven for this family
    porting_note: str  # one line: what this family prefers


class ModelAdapterReport(BaseModel):
    """The adaptation applied to the chosen target + the full portability map."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    target_model: str | None  # the chosen model id (None if none resolved)
    provider: str | None  # its provider, read from the registry (DATA)
    family: str  # detected family of the target (or "generic")
    label: str  # human label of that family
    reasoning_native: bool  # the target reasons natively → never force chain-of-thought
    directives: list[str]  # directives actually woven into the prompt for the target
    injected: bool  # whether a `## Adaptation modèle` section was added to the prompt
    # The BASE prompt is portable as-is; the adapter is a thin layer that can be swapped.
    model_independent: bool = True
    portability_note: str
    known_families: list[FamilyPort]  # every family the engine knows → explicit portability
    note: str  # honesty: conventions, not guarantees; re-verify per model
