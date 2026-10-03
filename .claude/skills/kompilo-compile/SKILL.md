---
name: kompilo-compile
description: >-
  Work on Kompilo's Prompt Compiler and the Kompilo Core orchestration exposed by
  POST /v1/compile. Use when changing how a CATR becomes a compiled prompt (IR,
  section selection, render variants), the end-to-end compile orchestration, the
  /v1/compile request/response contract, the execution plan, estimated costs, or the
  multidimensional diagnostic. Triggers: prompt compiler, IR, render, compact/
  professional/expert, kompilo core, /v1/compile, execution_plan, compiled_prompt,
  diagnostics, estimated cost, ASK vs PROCEED, compile response.
---

# Kompilo — Prompt Compiler & Kompilo Core (/v1/compile)

The compile endpoint turns a task into an execution plan + a compiled prompt. Builds on
`kompilo-intent` (CATR), `kompilo-strategize` (ambiguity/complexity/strategy/router).
Reference: `app/engines/prompt_compiler.py`, `app/engines/kompilo_core.py`,
`app/api/v1/routes/compile.py`, `app/schemas/compile.py`, tests in `tests/test_compile.py`.

## Rules

1. **Deterministic core.** The only non-deterministic step is the Intent Engine's
   optional LLM refine; reflect it in `metadata.deterministic` / `metadata.llm_used`.
   The compiler, plan and diagnostic are pure functions of the CATR + registry.
2. **ASK stops the pipeline.** Order is intent → ambiguity → (ASK ⇒ return
   `understood` + `questions`, everything else null | PROCEED) → complexity → strategy
   → router → prompt_compiler. Never compile a prompt when the ambiguity decision is ASK.
3. **Dynamic sections, no decoration.** The IR includes a section ONLY when it has real
   content. `role` and `mission` are always present; `context`, `steps`, `constraints`,
   `audience`, `output_format`, `validation` appear only when the CATR/request provide
   them. Never pad with empty or boilerplate sections.
4. **One IR, three renders.** `compact` (terse block), `professional` (markdown
   sections — the default), `expert` (professional + a rigor section tuned to the target
   model: step-by-step for strong reasoners, strict-JSON when it supports structured
   output and JSON is requested). `compiled_prompt.text` is the render chosen by `mode`.
5. **Costs are ESTIMATES.** `cost.estimated` is always true; derive tokens from a
   heuristic and price from the registry; keep the disclaimer. Never present a billed
   amount. `metadata.costs_estimated` stays true.
6. **Diagnostic is multidimensional and explainable** — a list of
   `{dimension, level, detail}` (clarity, specificity, confidence, risk, and on PROCEED
   complexity + strategy_fit), never a single score.
7. **Target model** = the forced `target_model` if given and in the registry, else the
   router's primary, else none (render generically + a note; cost can't be estimated).

## Contract (POST /v1/compile — public, stateless, no DB)

Request: `{task, context?, target_model?, mode?, output_format?, quality_contract?}`.
Response: `{understood{objective,domain}, execution_plan?, compiled_prompt?, renders?,
diagnostics[], questions[], metadata}` — the `?` fields are null on ASK. Keep it
unauthenticated (a pure compute endpoint); if abuse is a concern, rate-limit rather than
adding auth, and keep it DB-free.

## Testing

E2E over ASGITransport (no DB): PROCEED (plan + compiled prompt + all three renders +
multidimensional diagnostics + estimated cost), ASK (questions, null prompt/plan),
`mode` selects the matching render, `target_model` forcing. The Intent Engine stays on
its heuristic path (no key), so assertions are deterministic.

## When reviewing a diff, reject it if

- a prompt is compiled while the decision is ASK, or `understood` is dropped;
- the IR adds empty/decorative sections, or role/mission go missing;
- a cost is presented as anything but an estimate, or `costs_estimated` is cleared;
- the diagnostic collapses to a single score;
- capabilities/model names leak into the compiler (it takes a resolved profile);
- the endpoint gains DB/tenant coupling or becomes non-deterministic without flagging it.
