# Kompilo

**AI Execution Intelligence** — a "compiler" that turns a human intent into an AI
execution strategy:
*understand → strategize → compile → route → execute → verify → evaluate → improve*.

You write what you want to accomplish; Kompilo figures out *how*: it understands the
intent into a canonical task, surfaces what's ambiguous or missing, picks a strategy and a
model, compiles a clean prompt, runs it through a single metered Gateway, verifies the
output, and keeps every version comparable — all multi-tenant and deterministic at its core.

- **Demo walkthrough:** [`GUIDE_DEMO.md`](GUIDE_DEMO.md) — a scripted, step-by-step tour.
- **Honest limits:** [`LIMITES_CONNUES.md`](LIMITES_CONNUES.md) — every STUB + the V1.5 plan.

## Monorepo layout

```
.
├── backend/              # FastAPI · Pydantic v2 · SQLAlchemy 2.0 async · Alembic · ARQ
│   └── app/
│       ├── main.py       # FastAPI entrypoint
│       ├── core/         # config, security (JWT/bcrypt), tenancy (RLS)
│       ├── api/v1/        # routes (health, compile, tenants) + deps
│       ├── schemas/      # Pydantic v2 request/response models
│       ├── models/       # SQLAlchemy 2.0 models
│       ├── engines/      # the pipeline: stages + orchestrator
│       ├── db/           # async engine & session factory
│       ├── workers/      # ARQ worker + tasks
│       ├── telemetry/    # structured logging
│       └── migrations/   # Alembic (async)
├── frontend/             # Vite · React · TypeScript · Tailwind · TanStack Query
├── infra/postgres/init/  # pgvector + least-privilege app role (RLS)
└── docker-compose.yml    # postgres(pgvector) · redis · backend · worker · frontend
```

> **Status (MVP):** real end to end for `understand` → `strategize` → `compile` →
> `execute` → `verify`, plus the **prompt library + versioning** and an **8-axis
> explainable diagnostic**. A model **Gateway** (semantic Redis cache, retries/fallback,
> **real** token cost, idempotency) runs the plan; an **Executor** journals each step;
> **SSE streaming** and an output **Verifier** close the loop. `evaluate` and `improve`
> are **not yet implemented** (no measurement → version diffs stay verdict-free), and
> `retrieve`/RAG is a **STUB**. When no `OPENAI_API_KEY` is set, execution runs through a
> deterministic **offline Echo STUB**, always flagged (`provider_is_real=false`). Nothing
> stubbed is ever presented as real — the full list is in
> [`LIMITES_CONNUES.md`](LIMITES_CONNUES.md). The surrounding architecture (multi-tenant
> RLS, migrations, async ARQ workers, tooling) is real.

## Prerequisites

- Docker + Docker Compose v2
- Node.js ≥ 20 (only if you run the frontend outside Docker)

---

## Démarrage en 5 minutes

### 1. Configure the environment

```bash
cp .env.example .env
python3 -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(48))"
```

Open `.env` and:
- paste the generated value into `JWT_SECRET`,
- set strong values for `POSTGRES_PASSWORD` and `APP_DB_PASSWORD`,
- make the passwords inside `DATABASE_URL` and `ALEMBIC_DATABASE_URL` match the two above.

### 2. Start database + Redis + API + worker

```bash
docker compose up --build
```

This builds the images, waits for Postgres/Redis to be healthy, runs Alembic
migrations, then serves the API on **http://localhost:8000** and the frontend on
**http://localhost:5173**.

> To run only the backend stack: `docker compose up --build postgres redis backend worker`

Then, for a ready-to-demo account + a few prompts (see [`GUIDE_DEMO.md`](GUIDE_DEMO.md)):

```bash
cd backend && python scripts/seed_demo.py   # prints the demo credentials
```

### 3. (Alternative) Run the frontend locally

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

---

## Verify it works

The exact checks (commands + expected results) are in the task summary and below:

1. **API banner**
   ```bash
   curl -s http://localhost:8000/ | python3 -m json.tool
   ```
   Expected: `{"service": "Kompilo", "status": "running", "docs": "/docs"}`

2. **Liveness**
   ```bash
   curl -s http://localhost:8000/v1/health/live
   ```
   Expected: `{"status":"ok"}`

3. **Health (status + version + db)**
   ```bash
   curl -s http://localhost:8000/v1/health | python3 -m json.tool
   ```
   Expected: `{"status": "ok", "version": "0.1.0", "db": "ok"}` (db `ko` if the
   database is unreachable).

4. **Compile pipeline (Kompilo Core — deterministic)**
   ```bash
   curl -s -X POST http://localhost:8000/v1/compile \
        -H 'Content-Type: application/json' \
        -d '{"task":"Rédige un message de bienvenue chaleureux pour un nouveau client",
             "mode":"professional"}' | python3 -m json.tool
   ```
   Expected: `understood{objective, domain}` first, then (when the task is clear enough to
   proceed) `execution_plan`, `compiled_prompt`, `renders` (compact/professional/expert),
   a multi-dimensional `diagnostics`, and `metadata.engine:"kompilo-core-v1"` with
   `deterministic:true` and `costs_estimated:true` (costs here are **estimated**; real
   costs come from `/v1/execute`, step 12). An ambiguous task returns `questions` instead
   and leaves `execution_plan/compiled_prompt/renders` null. See the `kompilo-compile` skill.

5. **OpenAPI docs** — open http://localhost:8000/docs

6. **Frontend** — open http://localhost:5173 (shows Kompilo + backend health: status/db/version)

7. **Tenant isolation (RLS) quick check**
   ```bash
   # Create a dev organization (= tenant), grab its id:
   curl -s -X POST http://localhost:8000/v1/organizations \
        -H 'Content-Type: application/json' \
        -d '{"slug":"acme","name":"Acme"}' | python3 -m json.tool
   # Its own org is visible when scoped to it:
   curl -s http://localhost:8000/v1/organizations/me \
        -H 'X-Tenant-ID: <paste-org-id>'
   # Artifacts scoped to that tenant (empty list, RLS-filtered):
   curl -s http://localhost:8000/v1/artifacts -H 'X-Tenant-ID: <paste-org-id>'
   ```
   Expected: org created; the scoped artifacts list returns `[]` (and 401 without a tenant).

8. **Auth (signup → token-scoped access → refresh → RBAC)**
   ```bash
   # Signup creates a brand-new organization + its OWNER user, returning both tokens:
   TOKENS=$(curl -s -X POST http://localhost:8000/v1/auth/signup -H 'Content-Type: application/json' \
        -d '{"org_slug":"acme","org_name":"Acme","email":"owner@acme.io","password":"s3cret-pass"}')
   TOKEN=$(echo "$TOKENS"   | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
   REFRESH=$(echo "$TOKENS" | python3 -c "import sys,json;print(json.load(sys.stdin)['refresh_token'])")
   # Use the access token — tenant is derived from it, no X-Tenant-ID needed:
   curl -s http://localhost:8000/v1/auth/me   -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
   curl -s http://localhost:8000/v1/artifacts -H "Authorization: Bearer $TOKEN"
   # Exchange the refresh token for a fresh access token (rotation):
   curl -s -X POST http://localhost:8000/v1/auth/refresh -H 'Content-Type: application/json' \
        -d "{\"refresh_token\":\"$REFRESH\"}" | python3 -m json.tool
   ```
   Expected: `/auth/me` returns the user with `role: "owner"`; the token response is
   `{access_token, refresh_token, token_type:"bearer", expires_in:1800}`. The signup user
   is the org **owner**; `DELETE` routes and `GET /v1/organizations/members` return **403**
   for a plain `member`. (`/v1/auth/register` still adds extra users to an existing org in
   dev.) See the `kompilo-auth` skill.

   **Test it in Swagger (`/docs`):** open http://localhost:8000/docs → run
   `POST /v1/auth/signup` → copy `access_token` from the response → click **Authorize**
   (top-right), paste the token, **Authorize** → now every 🔒 endpoint is called with the
   bearer token. Example token response:
   ```json
   {
     "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
     "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
     "token_type": "bearer",
     "expires_in": 1800
   }
   ```

9. **Projects / Prompts / Versions (CRUD + versioning)** — reuse `$TOKEN` from step 8.
   ```bash
   # Create a project, then a prompt inside it:
   PROJECT=$(curl -s -X POST http://localhost:8000/v1/projects -H "Authorization: Bearer $TOKEN" \
        -H 'Content-Type: application/json' -d '{"slug":"alpha","name":"Alpha"}' \
        | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
   PROMPT=$(curl -s -X POST http://localhost:8000/v1/projects/$PROJECT/prompts \
        -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
        -d '{"slug":"greeting","name":"Greeting"}' \
        | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
   # Append two versions — numbers auto-increment (1, then 2):
   curl -s -X POST http://localhost:8000/v1/prompts/$PROMPT/versions -H "Authorization: Bearer $TOKEN" \
        -H 'Content-Type: application/json' -d '{"model_target":"claude","catr":{"n":1}}' | python3 -m json.tool
   curl -s -X POST http://localhost:8000/v1/prompts/$PROMPT/versions -H "Authorization: Bearer $TOKEN" \
        -H 'Content-Type: application/json' -d '{"model_target":"claude","catr":{"n":2}}' | python3 -m json.tool
   # List the version history (oldest first):
   curl -s http://localhost:8000/v1/prompts/$PROMPT/versions -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
   ```
   Expected: the two versions report `"version": 1` then `"version": 2`; the list returns both.
   Deleting a project/prompt is a **soft delete** (org admin only) that cascades to child
   prompts/versions; a slug can be reused after its owner is soft-deleted. See the
   `kompilo-crud` skill.

10. **Understand stage (async via ARQ worker)** — analyze an intent into a CATR.
    ```bash
    # Create a version carrying the raw intent to analyze:
    VERSION=$(curl -s -X POST http://localhost:8000/v1/prompts/$PROMPT/versions \
         -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
         -d '{"source_intent":"Implémente une fonction Python qui parse un CSV"}' \
         | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
    # Kick off the understand run (async → 202 Accepted, status pending):
    EXEC=$(curl -s -X POST http://localhost:8000/v1/executions -H "Authorization: Bearer $TOKEN" \
         -H 'Content-Type: application/json' -d "{\"prompt_version_id\":\"$VERSION\"}" \
         | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
    # Poll until the worker finishes (status: pending → succeeded):
    curl -s http://localhost:8000/v1/executions/$EXEC -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
    ```
    Expected: the execution moves to `"status": "succeeded"` and `output.catr` holds the
    **CanonicalAITask** (CATR): `objective`, `sub_goals`, `domain`, `inputs`, `context`,
    `constraints`, `expected_output`, `audience`, `complexity`, `missing_information`,
    `ambiguities`, `risk`, and `meta.method` (`heuristic-v1`, or `heuristic-v1+llm` when
    the LLM refined it). The same CATR is written onto the prompt version. The worker must
    be running (`docker compose up worker`). The CATR is produced by the **Intent Engine**
    (heuristics first; a light LLM is consulted **only** when confidence is low **and**
    `OPENAI_API_KEY` is set) — see the `kompilo-intent` skill.

    **Enable the LLM fallback / test your own phrases.** Paste your key in `.env`
    (`OPENAI_API_KEY=sk-...`; optionally `OPENAI_BASE_URL`, `INTENT_LLM_MODEL`,
    `INTENT_CONFIDENCE_THRESHOLD`). Try the engine on any sentence, offline or with the
    LLM, from the backend venv:
    ```bash
    cd backend && python -c "import asyncio,json; from app.engines.intent import IntentEngine; \
      print(json.dumps(asyncio.run(IntentEngine().run('VOTRE PHRASE ICI')).model_dump(), ensure_ascii=False, indent=2))"
    ```
    With no key it stays on the deterministic heuristic path (`meta.enriched_by_llm:false`);
    with a key, a low-confidence (vague) phrase triggers one LLM call to refine the
    objective/expected output (`meta.method:"heuristic-v1+llm"`).

11. **Strategize stage (ambiguity · complexity · strategy · routing)** — consumes the CATR.
    Runs inside the pipeline after `understand`; try the engines directly on any phrase:
    ```bash
    cd backend && python -c "import asyncio; \
      from app.engines.intent import IntentEngine; from app.engines.ambiguity import AmbiguityEngine; \
      from app.engines.complexity import ComplexityEngine; from app.engines.strategy import StrategyEngine; \
      from app.engines.router import ModelRouter; \
      c=asyncio.run(IntentEngine().run('VOTRE PHRASE')); x=ComplexityEngine().assess(c); s=StrategyEngine().decide(c,x); \
      print(AmbiguityEngine().analyze(c).decision, x.level, s.kind, ModelRouter().route(c,s,x).primary)"
    ```
    Expected shape: a decision `ASK` (1–3 questions, only if a CRITICAL is missing) or
    `PROCEED`; a complexity `simple|moderate|complex|agentic`; a strategy
    `single|chain|rag`; and a primary model + fallbacks. Examples: a clear 1-liner →
    `PROCEED simple single gpt-4o-mini`; `"truc"` → `ASK …`; a task citing a document →
    `rag`; a 4-step agent task → `agentic chain claude-sonnet-5-5`.

    **Model Capability Registry.** Model choices are driven by
    `backend/app/engines/model_registry.yaml` (model, provider, context_window, tools,
    vision, structured_output, reasoning_strength, cost, latency, **last_verified**).
    Edit the YAML to add/retune models — never the routing code — and keep `last_verified`
    fresh. See the `kompilo-strategize` skill.

12. **Execute a plan (REAL cost · semantic cache · idempotency)** — reuse `$TOKEN` from
    step 8. `/v1/execute` compiles the task, runs each step through the **Gateway**, and
    returns the output plus **real** cost/latency metadata. With no `OPENAI_API_KEY` it
    uses the offline Echo STUB (`provider_is_real:false`) — the flow is identical, the
    cost is tiny but real (tokens × registry price).
    ```bash
    # First call — runs the plan (cached:false, a real non-zero cost):
    curl -s -X POST http://localhost:8000/v1/execute -H "Authorization: Bearer $TOKEN" \
         -H 'Content-Type: application/json' \
         -d '{"task":"Rédige un message de bienvenue chaleureux pour un nouveau client"}' \
         | python3 -m json.tool
    # Second IDENTICAL call — served by the semantic cache (cached:true, cost 0):
    curl -s -X POST http://localhost:8000/v1/execute -H "Authorization: Bearer $TOKEN" \
         -H 'Content-Type: application/json' \
         -d '{"task":"Rédige un message de bienvenue chaleureux pour un nouveau client"}' \
         | python3 -m json.tool
    ```
    Expected: the **first** response has `metadata.cached:false` and
    `metadata.actual_cost.cost_usd > 0` (and `actual:true`); the **second**, identical,
    has `metadata.cached:true` and `cost_usd:0` — **the 2nd call is free**. The cache
    fingerprint is `sha256(tenant + normalized request + json_mode)` (model-agnostic) and
    is strictly tenant-scoped. Add an **`Idempotency-Key`** header to make a retry replay
    the very same execution instead of running again:
    ```bash
    curl -s -X POST http://localhost:8000/v1/execute -H "Authorization: Bearer $TOKEN" \
         -H 'Idempotency-Key: demo-key-123' -H 'Content-Type: application/json' \
         -d '{"task":"Rédige un message de bienvenue chaleureux pour un nouveau client"}' \
         | python3 -c "import sys,json;print(json.load(sys.stdin)['execution_id'])"
    # Same key again → same execution_id (replayed, metadata.idempotent_replay:true).
    ```
    If the task is ambiguous (a CRITICAL is missing), `/v1/execute` does **not** run — it
    returns `status:"needs_clarification"` with `questions` instead. No prompt or secret is
    ever logged. See the `kompilo-gateway` skill.

13. **Live streaming (SSE) + output Verifier** — stream an execution token by token.
    ```bash
    # Start an execution, capture its id:
    EXEC=$(curl -s -X POST http://localhost:8000/v1/execute -H "Authorization: Bearer $TOKEN" \
         -H 'Content-Type: application/json' \
         -d '{"task":"Rédige un message de bienvenue chaleureux pour un nouveau client"}' \
         | python3 -c "import sys,json;print(json.load(sys.stdin)['execution_id'])")
    # Stream it over SSE. EventSource cannot set headers, so the token goes in the query:
    curl -N "http://localhost:8000/v1/executions/$EXEC/stream?token=$TOKEN"
    ```
    Expected: an `text/event-stream` emitting `event: step`, then progressive
    `event: token` chunks, then a terminal `event: done`. Without a token → **401**; an
    unknown/foreign execution id (RLS) → **404**. The stream loads its data up front (no DB
    session held open) and closes cleanly on client disconnect. In the UI, open
    **http://localhost:5173**, compile a task, expand **« Exécution en direct (avancé) »**,
    paste an `access_token`, and click **Exécuter en streaming** (hook:
    `frontend/src/hooks/useExecutionStream.ts`).

    **Verifier.** Every `/v1/execute` response carries a `verification` report. Request a
    structured output and a schema to see it validate:
    ```bash
    curl -s -X POST http://localhost:8000/v1/execute -H "Authorization: Bearer $TOKEN" \
         -H 'Content-Type: application/json' -d '{
           "task":"Rédige la fiche d un client fictif nommé Dupont, avec son nom et son âge, au format JSON",
           "output_format":"json",
           "output_schema":{"required":["name","age"],
                            "properties":{"name":{"type":"string"},"age":{"type":"integer"}}}
         }' | python3 -c "import sys,json;print(json.load(sys.stdin)['verification'])"
    ```
    Expected: a `VerificationReport` with `valid` plus, when invalid, a precise list of
    `issues[{kind, detail, path}]`. With the offline STUB the JSON lacks `name`/`age`, so
    `valid:false` with `kind:"missing_field"` on `path:"name"` then `"age"` (a wrong type
    would be `kind:"type_mismatch"`) — never a bare pass/fail. The JSON-Schema subset is
    `required` + property `type`, recursive into nested objects and array items. See the
    `kompilo-gateway` skill.

---

## Architecture notes

- **Multi-tenant RLS.** `organizations` is the tenant root. The API connects as a
  least-privilege Postgres role (`kompilo_app`, `NOSUPERUSER`) subject to Row-Level
  Security. Each request pins the active tenant via `SET LOCAL app.tenant_id`; every
  tenant-owned table has an `ENABLE`+`FORCE` RLS policy filtering by `tenant_id`, so
  tenants cannot read each other's rows. Migrations run as the superuser (`kompilo`),
  which owns the tables. See the `kompilo-rls` skill.
- **Gateway (single exit point).** Every model call goes through
  `backend/app/engines/gateway.py`: a semantic Redis cache (fingerprint =
  `sha256(tenant + normalized request + json_mode)`, model-agnostic, tenant-scoped),
  retries with backoff then fallback to the next routed model, and **real** cost from
  `tokens × registry price`. It never logs the prompt or a secret. Providers sit behind
  one `LLMProvider` interface (OpenAI / Ollama / LM Studio, or the offline Echo STUB).
  See the `kompilo-gateway` skill.
- **Explainable diagnostic.** `backend/app/engines/diagnostics.py` scores a compilation on
  **8 independent axes** (clarity, completeness, specificity, robustness, executability,
  context quality, output definition, ambiguity handling). Each axis is `low`/`medium`/`high`
  with — when weak — the reason and a corrective action. There is **no single aggregate
  score**: a prompt is strong or weak in nameable ways. See the `kompilo-solidify` skill.
- **Error handling.** `backend/app/core/errors.py` defines a taxonomy
  (INPUT/PROMPT/MODEL/TOOL/CONTEXT/POLICY/TIMEOUT/RATE_LIMIT/VALIDATION/UNKNOWN) and the
  strategy **detect → classify → repair → retry → fallback → verify**. Each category maps
  to a user-safe French message + HTTP status; the Gateway retries only retryable
  categories (stopping early on policy/validation) then falls back; the Executor repairs a
  malformed JSON output once; the Verifier has the final say. Internals/secrets are never
  shown to the user.
- **Secrets.** Never committed; everything flows through `.env` (git-ignored).
- **STUB stages.** `backend/app/engines/stages.py` returns placeholder output
  until real reasoning is implemented. Nothing stubbed is presented as real.

## Useful commands

```bash
# Run the WHOLE backend test suite in ONE command (from the repo root).
# Unit tests always run; integration tests run when a migrated Postgres + Redis are
# reachable and skip cleanly otherwise. `make check` adds lint + types.
make test          # full suite        │  make test-unit   # unit only, zero setup
make check         # lint + types + tests
make frontend-build

# Or directly:
cd backend && pip install -e ".[dev]" && pytest

# New migration after changing models
docker compose exec backend alembic revision --autogenerate -m "describe change"
docker compose exec backend alembic upgrade head

# Lint / format / type-check
cd backend && ruff check . && black --check . && mypy app

# Frontend production build
cd frontend && npm run build
```

When all tests pass you see a single green line like
`108 passed in 12s` (full suite) or `99 passed in 2s` (unit only) — no failures, no errors.

## Continuous Integration

`.github/workflows/ci.yml` runs on every push and pull request:

- **backend-quality** — `ruff check` (lint), `black --check` (format), `mypy --strict`, unit tests.
- **backend-integration** — spins up PostgreSQL (pgvector), runs the real
  `infra/postgres/init/01-init.sh`, applies migrations as the superuser, then runs
  the RLS isolation tests as the least-privilege app role.
- **frontend-build** — `npm ci` + typecheck + `vite build` from the committed lockfile.

Conventions for changing CI (reproducibility, adding jobs/services, debugging a
red pipeline) are captured in the `kompilo-ci` skill.
