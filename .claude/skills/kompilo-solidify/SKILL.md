---
name: kompilo-solidify
description: >-
  Work on Kompilo's explainable diagnostic, the error taxonomy / handling strategy, and
  the test suite + single-command runner. Use when changing the 8-axis diagnostic, the
  error categories or classification, the detect→classify→repair→retry→fallback→verify
  flow, per-engine unit tests, the E2E test, or the Makefile. Triggers: diagnostic,
  DiagnosticEngine, clarity/completeness/specificity/robustness/executability/
  context_quality/output_definition/ambiguity_handling, no single score, error taxonomy,
  ErrorCategory, KompiloError, classify_exception, retry/fallback/repair, JSON repair,
  make test, test suite, deterministic tests, mock LLM.
---

# Kompilo — diagnostic, error handling & tests

Reference: `app/engines/diagnostics.py`, `app/core/errors.py`, `app/engines/gateway.py`,
`app/engines/executor.py`, `app/schemas/compile.py` (DiagnosticDimension), `Makefile`.

## Explainable diagnostic (no single score)

- `DiagnosticEngine.assess(catr, ambiguity, *, complexity?, strategy?, route?, output_format)`
  returns EXACTLY eight axes: clarity, completeness, specificity, robustness,
  executability, context_quality, output_definition, ambiguity_handling.
- Each `DiagnosticDimension` has `dimension`, `label` (French), `level`
  (`low`/`medium`/`high`), `detail`, and — only when weak (not `high`) — a `reason` and a
  concrete `recommendation`. There is NEVER an aggregate score: strengths/weaknesses are
  named per axis. `complexity`/`strategy`/`route` are absent in the ASK branch — the
  engine degrades gracefully (executability → "à évaluer après clarification").

## Error taxonomy + strategy

- `ErrorCategory`: INPUT, PROMPT, MODEL, TOOL, CONTEXT, POLICY, TIMEOUT, RATE_LIMIT,
  VALIDATION, UNKNOWN. Each maps to `retryable`, an HTTP status, and a user-facing French
  message (safe to show — `KompiloError.to_http()` never leaks `detail`/secrets).
- The six stages and where they live: **detect** (Gateway/Verifier) → **classify**
  (`classify_exception`) → **repair** (Executor: one corrective re-prompt for a JSON
  contract whose output didn't parse) → **retry** (Gateway, retryable categories only,
  with backoff) → **fallback** (Gateway, next routed model) → **verify** (Verifier).
- The Gateway stops early on a NON-retryable category (policy/context/validation) instead
  of wasting retries, and raises a `KompiloError`; `GatewayError` is a `KompiloError`
  (MODEL). `/v1/execute` catches `KompiloError` and returns its user message + category.

## Tests + single command

- Per-engine unit tests (deterministic, LLM mocked, no DB): intent, ambiguity/complexity/
  strategy/router (`test_strategize`), prompt_compiler, verifier, diagnostics, errors,
  gateway; plus a DB-free E2E `test_e2e_compile_execute` (compile → execute via a fake
  provider → verify), and the integration E2E `test_execute_flow` (real DB, Echo STUB).
- `make test` runs the FULL suite (integration skips cleanly without a DB); `make test-unit`
  needs nothing; `make check` = lint + types + tests. `test_health` is hermetic (it
  monkeypatches the DB probe down) so the full suite passes with OR without a live DB.

## When reviewing a diff, reject it if

- the diagnostic exposes a single aggregate score, or a weak axis lacks a reason/action;
- an error is surfaced to the user with internals/secrets, or a non-retryable failure is
  retried, or a classified failure returns a bare 500;
- the JSON repair runs more than once, or repair/verify is silently dropped;
- a new engine ships without a deterministic unit test, or a test needs the network/an LLM
  key, or `make test` can no longer run the whole suite in one command.
