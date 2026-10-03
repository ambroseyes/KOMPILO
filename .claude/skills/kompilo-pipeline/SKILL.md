---
name: kompilo-pipeline
description: >-
  Work on Kompilo's single full-lifecycle pipeline (understand → strategize → compile →
  execute → verify → evaluate → improve) and run it sync or async (ARQ worker) with tenant
  isolation intact. Use when changing the orchestrator, the evaluate/improve engines, the
  shared execution persistence, the worker task, or the executions API. Triggers: pipeline,
  KompiloPipeline, orchestrator, PipelineOutcome, evaluate, improve, Evaluator, Improver,
  measured score, grounded suggestions, run_pipeline_task, enqueue_pipeline, executions,
  execution_store, persist_success, ARQ, RLS in the worker, trace.
---

# Kompilo — the single pipeline & async execution

There is ONE pipeline. Builds on `kompilo-rls` (isolation), `kompilo-crud` (routes) and
`kompilo-gateway` (execution). Reference: `app/engines/orchestrator.py`,
`app/engines/{evaluator,improver}.py`, `app/services/execution_store.py`,
`app/workers/tasks.py`, `app/core/queue.py`, `app/api/v1/routes/{execute,executions}.py`.

## One orchestrator, two thin wrappers

`KompiloPipeline.run(task, tenant_id, …) -> PipelineOutcome` is the ONLY place the full
lifecycle runs: `understand → strategize → compile → (ASK ⇒ stop) → execute → verify →
evaluate → improve`. It is PURE (no DB, no HTTP) and returns the compile response, the
execution outcome, verification, evaluation, improvements and a per-stage `trace`.

- `/v1/execute` (sync) and `run_pipeline_task` (async worker) BOTH call it, then persist
  the result the same way via `services/execution_store.persist_success` (journal steps +
  build REAL-cost metadata + store the output blob). Do not add a third orchestration or a
  second persistence path — that duplication is exactly what this consolidation removed
  (the old `engines/stages.py` / `pipeline.py` Stage machinery is gone).
- On an ambiguous task the pipeline stops after strategize and returns
  `needs_clarification` + questions (no execution row / no model call).

## evaluate & improve (real, but honest)

- `Evaluator.evaluate(output, catr, verification, quality_contract) -> EvaluationReport`:
  a MEASURED, deterministic score in [0,1] from explicit weighted criteria, each with
  evidence (`method="rules-v1"`, `measured=True`). It is a heuristic proxy, NOT an LLM
  judge — say so; never dress it up as a model's judgment.
- `Improver.suggest(catr, diagnostics, evaluation) -> ImprovementReport`: GROUNDED
  suggestions, each carrying `derived_from` (a weak diagnostic axis, a failed eval
  criterion, missing information, an ambiguity). Never invent a suggestion with no signal.
- A measurement is what lets a verdict exist — but the version diff stays neutral until a
  multi-case eval harness ranks versions (that is V1.5, not this).

## Async (ARQ) — the executions pattern

Flow: `POST /executions` → create `executions` row (`pending`) → enqueue AFTER commit →
worker runs the pipeline → row `succeeded`/`failed` → client polls `GET /executions/{id}`.

- Enqueue from `BackgroundTasks` (runs post-commit, never races the row):
  `background.add_task(enqueue_pipeline, execution.id, user.tenant_id)` → return 202.
- Pass `tenant_id` into the job as a string; the worker pins RLS with it.
- `run_pipeline_task` stores a succeeded run via `persist_success` (same shape `/execute`
  stores) and treats `needs_clarification` as a valid succeeded outcome.

### RLS inside the worker (critical)

No request session exists, so pin the tenant by hand and keep failure-recording hermetic:

```python
async with session_scope() as s:
    await apply_tenant_guc(s, tenant_id)      # from the job arg — pins RLS
    execution = await s.get(Execution, exec_id)
    if execution is None:
        return {"status": "missing"}          # invisible to this tenant → no-op
    ... run KompiloPipeline + persist_success ...
```

- A spoofed `tenant_id` can only make rows invisible (fail-closed), never cross tenants.
- On error, record `status="failed"` + `error` in a FRESH `session_scope` (the original
  rolled back and dropped the GUC). A classified `KompiloError` stores its category.
- Keep the function name in sync with the `enqueue_job` string (one constant, `PIPELINE_TASK`)
  and register it in `WorkerSettings.functions`.

## Testing

- **Unit (no infra):** each engine deterministically (`evaluator`, `improver`), and the
  orchestrator with an INJECTED fake executor (`KompiloPipeline(executor=Fake())`) — assert
  the full trace, that evaluate/improve run, and that an ambiguous task stops at strategize.
- **Integration (DB):** call `run_pipeline_task` directly to prove the logic + RLS
  confinement (wrong tenant → `missing` no-op).
- **Integration (DB + Redis):** `POST /executions` → ARQ `Worker(burst=True)` → poll
  `succeeded`. Skip only the Redis leg if Redis is down; never skip the DB leg.

## When reviewing a diff, reject it if

- a second orchestration or persistence path reappears (one pipeline, one `persist_success`);
- the evaluator is presented as an LLM judge, or an improvement has no `derived_from` signal;
- the version diff claims a "better" verdict without a measurement;
- a worker task touches tenant tables without `apply_tenant_guc`, or takes the tenant from
  anywhere but the job arg, or enqueues inside the request transaction;
- a failed task doesn't persist `status="failed"` + `error` in a fresh session, or the task
  isn't registered in `WorkerSettings.functions`.
