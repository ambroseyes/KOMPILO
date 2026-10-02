---
name: kompilo-pipeline
description: >-
  Implement or review a Kompilo pipeline stage (understand, strategize, compile,
  route, execute, verify, evaluate, improve) and run it asynchronously through the
  ARQ worker with tenant isolation intact. Use when turning a STUB stage into a real
  one, adding a stage, shaping a stage's output schema, dispatching work to the ARQ
  worker, writing a worker task that touches tenant data, or wiring the executions
  API. Triggers: pipeline stage, understand/strategize/compile/route/execute/verify,
  CATR, is_stub, Stage.run, analyze_intent, ARQ, worker task, enqueue_job, executions,
  background task, RLS in the worker, "make a stage real", heuristic vs LLM.
---

# Kompilo — pipeline stages & async execution

How to make a pipeline stage real and run it off the request path without breaking
tenant isolation or honesty about what is real. Builds on `kompilo-rls` (isolation)
and `kompilo-crud` (resource routes). Reference implementation:
`backend/app/engines/understand.py` (the first real stage), `app/engines/stages.py`,
`app/workers/tasks.py`, `app/core/queue.py`, `app/api/v1/routes/executions.py`.

## The pipeline shape (don't fight it)

`intent → understand → strategize → compile → route → execute → verify → evaluate
→ improve`. Each stage is a `Stage` (`app/engines/base.py`) with `async run(ctx)
-> StageResult`; the orchestrator (`app/engines/pipeline.py`) threads one
`PipelineContext` through them and isolates failures. Stage output lands in
`ctx.artifacts[stage.name]` and a `StageResult(status, note, output)` in the trace.

## Making a stage real — the 5 rules

1. **Core logic lives in its own module, not in the Stage.** Put the real work in a
   pure function with a stable signature (e.g. `analyze_intent(intent, context) ->
   Catr`). The `Stage.run` is a thin adapter that calls it and wraps the result.
   The same core is then reused by the worker task and is unit-testable alone.
2. **Type the output with a Pydantic model** in `app/schemas/` (e.g. `Catr`). Store
   it as `model.model_dump()` into the JSONB column / artifact. Use
   `ConfigDict(extra="forbid")` so the shape can't silently drift.
3. **Never present not-real as real** (rule 2 of the project). A heuristic carries a
   `method="heuristic-v1"` marker and a `StageResult.note` saying "heuristic, not an
   LLM". A STUB stage keeps the `_STUB_NOTE`. An LLM stage records the model used.
   `is_stub` on the compile response stays true until ALL stages are real.
4. **Deterministic when heuristic.** No randomness, no reliance on dict ordering or
   set iteration for output; de-dup preserving first-seen order; clamp/round numeric
   scores. Same input → identical output, so it is testable without mocks.
5. **Swappable engine.** A heuristic and an LLM implementation share the one core
   signature, so swapping (or selecting by `ANTHROPIC_API_KEY` presence) changes no
   caller. Keep provider/network/key handling behind that function, never in routes.

## Running a stage async (ARQ) — the executions pattern

A stage that is slow or external runs off the request path and is tracked in the
`executions` table (a generic job record: status/input/output/error/timestamps,
tied to a `prompt_version`).

Flow: `POST /executions` → create `executions` row (`pending`) → enqueue → ARQ
worker runs it → row becomes `succeeded`/`failed` → client polls `GET
/executions/{id}`.

- **Enqueue AFTER commit, from `BackgroundTasks`.** FastAPI background tasks run
  after the response (and the dependency's commit), so the worker never races the
  row's creation. Do NOT `enqueue_job` inside the request transaction.
  ```python
  db.add(execution); await db.flush(); await db.refresh(execution)
  background.add_task(enqueue_understand, execution.id, user.tenant_id)
  return execution  # 202 Accepted, status "pending"
  ```
- **Pass `tenant_id` into the job**, as a string, next to the row id. The worker
  needs it to pin RLS — it can't read the row to discover its own tenant.
- **Return 202** and let the client poll. Validate cheaply up front (404 for a
  missing/soft-deleted parent, 422 for missing required input like `source_intent`)
  so the caller gets immediate feedback instead of an async failure.

### RLS inside the worker (critical)

The worker connects as the app role (RLS-enforced) and runs OUTSIDE a request, so
there is no `get_tenant_session` to pin the tenant. Pin it by hand:

```python
async with session_scope() as s:
    await apply_tenant_guc(s, tenant_id)      # from the job arg — pins RLS
    execution = await s.get(Execution, exec_id)
    if execution is None:                     # invisible to this tenant → no-op
        return {"status": "missing"}
    ... do work ...  # every read/write is now tenant-confined
```

- A mismatched/spoofed `tenant_id` can only make rows invisible (fail-closed no-op),
  never cross tenants — RLS is the backstop, the job arg is the pin.
- **On error, record the failure in a FRESH session** (`session_scope` +
  `apply_tenant_guc` again): the original transaction rolled back, and a full
  rollback drops the GUC, so reuse of the poisoned session would run tenant-less.
- Register the task in `app/workers/settings.py` `WorkerSettings.functions`, and keep
  the function name in sync with the `enqueue_job(...)` string (one constant).

## Testing

- **Unit (no infra):** the core function — classification, extraction, determinism
  (`f(x).model_dump() == f(x).model_dump()`), score bounds, the honesty marker. Plus
  a 401 auth-gate test for the executions routes.
- **Integration (DB):** call the worker task function directly against the real DB
  to prove the logic and its RLS confinement (run it under the wrong tenant → no-op).
- **Integration (DB + Redis):** the full path — `POST /executions` → run an ARQ
  `Worker(functions=[...], burst=True)` to drain the queue → poll `succeeded`. Skip
  this leg if Redis is unreachable; never skip the DB leg.

## When reviewing a diff, reject it if

- a real stage still carries the STUB note, or a heuristic/stub is presented as an
  LLM (no `method`/note marker), or `is_stub` is cleared while a stage is still STUB;
- stage core logic is inlined in `Stage.run` or a route instead of a reusable, typed,
  deterministic function;
- a worker task touches tenant tables without `apply_tenant_guc`, or takes the tenant
  from anywhere but the job arg;
- a job is enqueued inside the request transaction (races the row), or the tenant id
  is omitted from the job;
- a failed task doesn't persist `status="failed"` + `error` in a fresh session;
- the task function isn't registered in `WorkerSettings.functions`.
