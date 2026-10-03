---
name: kompilo-intent
description: >-
  Work on Kompilo's Intent Engine and the CATR (CanonicalAITask): the heuristics-first,
  cost-gated extraction of a human sentence into a strictly-typed canonical task. Use
  when changing the CATR shape, the heuristic rules (domain/complexity/risk/missing_info),
  the LLM fallback, the provider adapter, or the confidence threshold. Triggers: CATR,
  CanonicalAITask, IntentEngine, intent extraction, heuristics, domain/complexity/risk,
  missing_information, ambiguities, confidence, LLM fallback, provider, OpenAI-compatible,
  gateway, cost control, OPENAI_API_KEY.
---

# Kompilo — Intent Engine & CATR

How a sentence becomes a `CanonicalAITask` (CATR). Builds on `kompilo-pipeline` (the
`understand` stage wraps this). Reference: `app/schemas/catr.py`,
`app/engines/heuristics.py`, `app/engines/intent.py`, `app/engines/providers/`.

## The CATR (single canonical model)

`CanonicalAITask` (`app/schemas/catr.py`) is THE task representation — one model, no
drift. Fields: `objective`, `sub_goals[]`, `domain`, `inputs[]`, `context[]`,
`constraints[]`, `expected_output?`, `audience?`, `complexity` (low/med/high),
`missing_information[{label, importance}]`, `ambiguities[]`, `risk` (low/med/high), and
`meta{method, confidence, enriched_by_llm}`. `extra="forbid"` so the shape can't drift.

- **Partial is valid.** Optional fields stay empty when unknown; that's what
  `missing_information` and `ambiguities` are for — surface gaps, don't invent values.
- **Business fields vs provenance.** Keep the spec fields clean; provenance lives in
  `meta`. `method` is `heuristic-v1` or `heuristic-v1+llm`; `enriched_by_llm` says
  whether the LLM actually contributed. Never present heuristic output as model
  reasoning.

## The engine (heuristics first, LLM only if needed)

`IntentEngine.run(sentence) -> CanonicalAITask`:
1. `build_heuristic_catr` (deterministic, offline) fills the whole CATR and a
   `meta.confidence`.
2. **Cost control:** call the LLM ONLY when `confidence < threshold`
   (`settings.intent_confidence_threshold`) AND a provider is configured. Otherwise
   return the heuristic CATR untouched.
3. The LLM refines just `objective` + `expected_output` (narrow, cheap), parsed from
   strict JSON; on ANY failure (no key, network, bad JSON) fall back to the heuristic
   CATR. Success sets `meta.enriched_by_llm=True`, `method="heuristic-v1+llm"`.

Keep the heuristic layer **deterministic**: no randomness/dict-order reliance, dedupe
preserving first-seen order, clamp/round `confidence`. Same input → same CATR.

## Provider (seed of the Gateway)

`app/engines/providers/` is the minimal base of the future Gateway:
- `base.py` — the narrow `LLMProvider` Protocol (`complete_json`) + `ProviderError`.
- `openai_compatible.py` — one JSON-mode call to `{base_url}/chat/completions`; no
  retries/routing/budgets yet; wraps all failures as `ProviderError` (never leaks the key).
- `get_default_provider()` returns the adapter ONLY when `OPENAI_API_KEY` is set, else
  `None` — this is what keeps the engine free/offline by default.

Key + endpoint come from the env (`OPENAI_API_KEY`, `OPENAI_BASE_URL`,
`INTENT_LLM_MODEL`), never hardcoded. Egress to the endpoint must be allowed by the
environment's network policy.

## Testing

- Heuristics: deterministic unit tests (domain classification, extraction, risk,
  missing_information, a vague sentence → low confidence + ambiguities). No infra.
- LLM path: inject a FAKE provider (records calls, returns canned JSON) — assert the
  refine updates `objective`/`expected_output` and flips `meta`, AND the cost-control
  rule (a high-confidence sentence makes `provider.calls == 0`), AND that a failing/bad
  provider falls back. Never hit a real API in tests (no key → provider None).

## When reviewing a diff, reject it if

- a second "CATR" model is introduced instead of extending `CanonicalAITask`;
- the LLM is called unconditionally (ignores the confidence gate) or on the happy path;
- an LLM/provider failure isn't caught and downgraded to the heuristic CATR;
- heuristic output is non-deterministic, or claims `heuristic-v1+llm`/`enriched_by_llm`
  without the LLM having contributed;
- the API key is hardcoded, logged, or leaked through an error message;
- provider selection doesn't degrade to `None` when no key is configured.
