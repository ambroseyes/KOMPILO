---
name: kompilo-strategize
description: >-
  Work on Kompilo's strategize stage: the Ambiguity, Complexity, Strategy engines and
  the Model Router + capability registry. Use when changing ASK/PROCEED logic, the
  complexity scoring, strategy selection (single/chain/rag), model routing, or the model
  capability registry. Triggers: ambiguity, ASK/PROCEED, CRITICAL/IMPORTANT/OPTIONAL,
  complexity, simple/moderate/complex/agentic, strategy, single/chain/rag, model router,
  capability registry, model_registry.yaml, reasoning_strength, last_verified, fallback.
---

# Kompilo — strategize stage (ambiguity · complexity · strategy · routing)

The strategize stage consumes a CATR (`CanonicalAITask`) and produces a
`StrategizeResult`. Builds on `kompilo-intent` (the CATR) and `kompilo-pipeline` (the
stage wraps these engines). Reference: `app/engines/{ambiguity,complexity,strategy,
router,registry}.py`, `app/engines/model_registry.yaml`, `app/schemas/{strategize,
registry}.py`, wired in `app/engines/stages.py::StrategizeStage`.

## Non-negotiable rules

1. **Never invent missing information.** Engines surface gaps (from the CATR), they
   never fill them. The Ambiguity Engine only *asks* for what's missing.
2. **Ask the minimum.** `decision == "ASK"` **only** if at least one `CRITICAL` exists;
   then 1–3 targeted questions, one per unresolved CRITICAL. `IMPORTANT`/`OPTIONAL`
   findings are surfaced but never force a question. Otherwise `PROCEED`.
3. **Capabilities are DATA, never hardcoded.** The router reads every capability from
   the registry (`ModelCapability`); routing logic must never mention a model by name.
   An unconfirmed/false capability is treated as absent (fail-closed → excluded).
4. **`last_verified` is mandatory** on every registry entry (the loader rejects a
   missing one). Cost/context/latency drift — keep the YAML current, not the code.
5. **No needless escalation.** The Strategy Engine never picks a heavier strategy when
   a simpler one suffices: a `simple` task with no external source stays `single`;
   `rag`/`chain` require an explicit signal (a retrieval source, or genuine multi-step).

## Severity & decision (Ambiguity)

- CATR `missing_information` importance maps to severity: high→CRITICAL, medium→
  IMPORTANT, low→OPTIONAL. A mutually-exclusive **contradiction** (e.g. output in both
  French and English; "concise" + "exhaustive") is CRITICAL. Vague terms and the CATR's
  own `ambiguities` are IMPORTANT.
- ASK ⇔ any CRITICAL. Questions are generated per CRITICAL finding, deduped, capped at 3.

## Complexity (rules v1; ML is STUB)

- Level ∈ {simple, moderate, complex, agentic} from normalized features: `length`,
  `sub_goals`, `domain_weight`, `tools`. Score = weighted sum; thresholds decide the
  band. **Agentic override**: ≥4 sub-goals AND a tool signal.
- The `tools` signal = external inputs, OR software/data domain, OR explicit tool/agentic
  language (agent, outil, orchestrate, workflow, escalate, …). Keep it a feature, not a
  special case elsewhere.
- `_ml_complexity_stub` is the explicit seam for the future PyTorch model — marked STUB,
  unused in v1 (`method == "rules-v1"`). Return the `features` for transparency.

## Strategy (single / chain / rag)

- `rag` when the CATR inputs reference a real source (file/URL/provided content).
- else `chain` when complexity ∈ {complex, agentic} OR ≥3 sub-goals.
- else `single`. Always record `rationale` + the `signals` that fired. Apply the
  guardrail (rule 5) first.

## Router (filter → rank)

- **Filter** survivors by required capabilities derived from CATR/strategy/complexity:
  min `reasoning_rank` by level, min `context_window` (larger for `rag`), `supports_tools`
  (agentic or rag), `supports_vision` (image inputs/words), `structured_output`
  (expected_output asks for it). Every check reads a registry field.
- **Rank** survivors by a complexity-weighted blend of quality (reasoning rank), cost and
  latency (simple → favor cheap/fast; agentic → favor quality). Deterministic tie-break
  (score, then cheaper, then faster, then name). Return `primary` (or `None` if nothing
  qualifies) + ordered `fallbacks` + the `required_capabilities` list.

## Testing

Pure/offline/deterministic — no DB. Cover: clear CATR → PROCEED; a CRITICAL → ASK with
the right question(s); each complexity band; strategy per rule incl. the guardrail;
router simple→cheap/fast, complex→advanced+fallback, agentic→frontier-only; a custom
registry proving capabilities are read (a model lacking a required capability is
excluded); `last_verified` missing → ValidationError.

## When reviewing a diff, reject it if

- the router references a model by name, or treats an unknown capability as present;
- an engine fills in missing info instead of surfacing it, or ASKs without a CRITICAL,
  or asks more than 3 / more than one-per-CRITICAL questions;
- a registry entry lacks `last_verified`, or capabilities live in code not the YAML;
- the Strategy Engine escalates a simple, source-less task beyond `single`;
- the complexity `method` claims anything other than `rules-v1` while the ML model is
  still a STUB.
