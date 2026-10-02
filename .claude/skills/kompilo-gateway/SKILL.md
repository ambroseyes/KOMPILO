---
name: kompilo-gateway
description: >-
  Work on Kompilo's model Gateway, real plan execution, SSE streaming and the output
  Verifier. Use when changing the provider abstraction, the semantic cache,
  retries/fallback, the executor, POST /v1/execute, the SSE stream endpoint, or output
  validation. Triggers: gateway, LLMProvider, complete/capabilities, OpenAI-compatible,
  Ollama, LM Studio, echo stub, semantic cache, fingerprint, retries, fallback,
  executor, execution_steps, /v1/execute, real cost, idempotency, SSE, EventSource,
  streaming, verifier, output contract, JSON schema.
---

# Kompilo — Gateway, execution, streaming & verification

Builds on `kompilo-strategize` (route/plan) and `kompilo-compile`. Reference:
`app/engines/providers/*`, `app/engines/gateway.py`, `app/engines/executor.py`,
`app/engines/verifier.py`, `app/api/v1/routes/{execute,stream}.py`, `app/core/redis.py`,
`frontend/src/hooks/useExecutionStream.ts`.

## Providers (Model Abstraction Layer)

- One interface: `LLMProvider` with `complete(...) -> CompletionResult` and
  `capabilities() -> ProviderCapabilities`. The OpenAI-compatible adapter covers OpenAI /
  Ollama / LM Studio (same `/chat/completions` schema); the key + base URL come from env.
- `get_default_provider()` → real provider or **None** (Intent Engine stays heuristic).
  `get_execution_provider()` → real provider or the deterministic **EchoProvider STUB**
  (`capabilities().is_real == False`). NEVER present stub output as real: flag it in
  responses (`provider_is_real`, a `note`).

## Gateway (single exit point)

- **Cache**: fingerprint = `sha256(tenant + normalized(system+prompt) + json_mode)` —
  model-agnostic, per the contract. A hit returns the stored text with ZERO new
  cost/tokens (`cached=True`). Best-effort: if Redis is down, skip the cache.
- **Retries + fallback**: up to N attempts per model with backoff, then the next model in
  the route; `GatewayError` only when all fail.
- **Cost is REAL**: `tokens × registry price` (0 on cache / unpriced model) — distinct
  from the compile-time estimate. Trace tokens/cost/latency; NEVER log the prompt or key.

## Executor + /v1/execute

- The Executor runs the plan step by step through the Gateway; each step is journaled in
  `execution_steps` (input, output, tokens, cost, cached, latency). `retrieve` is a STUB.
- `/v1/execute` is authenticated + tenant-scoped. It compiles (ASK ⇒ return questions, no
  run), creates an execution (prompt_version_id nullable for raw tasks), runs it, verifies
  the output, and returns the result + `actual_cost` (REAL) + the verification report.
  **Idempotent** via an `Idempotency-Key` header (Redis map → execution id; replays).

## SSE streaming

- `GET /v1/executions/{id}/stream`: auth via a `token` query param (EventSource can't set
  headers) or a Bearer header; load tenant-scoped (RLS → 404 for others). Load the data
  UP FRONT (no DB session held open), then emit `step` events, `token` events
  (progressive), and a terminal `done` event; on failure emit `error`. Clean close on
  client disconnect (CancelledError propagates).
- Frontend `useExecutionStream(executionId, token)`: opens an EventSource, accumulates
  tokens into `text`, closes on `done`/error/unmount. Non-blocking, robust.

## Verifier

- `verify_output(output, output_format, output_schema?)` → a `VerificationReport`
  (`valid`, `issues[{kind, detail, path}]`, `summary`). JSON output is parsed; with a
  schema (a small JSON-Schema subset: `required` + property `type`, recursive), it reports
  exactly what is missing or type-mismatched — never a bare pass/fail.

## When reviewing a diff, reject it if

- stub output is returned without `provider_is_real=False` / a note;
- the Gateway logs the prompt or a secret, or the cache key includes the model;
- a cache hit is charged (cost must be 0), or real cost is conflated with the estimate;
- `/execute` isn't tenant-scoped, or steps aren't journaled, or idempotency is dropped;
- the SSE endpoint holds a DB session open while streaming, or never closes on
  disconnect, or authenticates only via a header (EventSource can't send one);
- the Verifier returns valid/invalid with no explanation of what failed.
