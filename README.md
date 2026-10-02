# Kompilo

**AI Execution Intelligence** — a "compiler" that turns a human intent into an AI
execution strategy:
*understand → strategize → compile → route → execute → verify → evaluate → improve*.

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

> **Status:** project skeleton. The **`understand`** stage is now a real
> deterministic analyzer (heuristic, `method="heuristic-v1"` — not an LLM); the
> remaining pipeline stages are still **STUB** (the `/v1/compile` response carries
> `is_stub: true` for the pipeline as a whole, but the `understand` trace entry is
> no longer marked STUB). The surrounding architecture — database, multi-tenant RLS
> isolation, migrations, async ARQ workers, tooling — is real, not mocked.

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

4. **Compile pipeline (STUB)**
   ```bash
   curl -s -X POST http://localhost:8000/v1/compile \
        -H 'Content-Type: application/json' \
        -d '{"intent":"ship a feature"}' | python3 -m json.tool
   ```
   Expected: `is_stub: true` and a `trace` of 8 stages.

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

8. **Auth (register → login → token-scoped access)**
   ```bash
   # Register a user in that org (DEV bootstrap), then log in:
   curl -s -X POST http://localhost:8000/v1/auth/register -H 'Content-Type: application/json' \
        -d '{"org_slug":"acme","email":"you@acme.io","password":"s3cret-pass"}'
   TOKEN=$(curl -s -X POST http://localhost:8000/v1/auth/login -H 'Content-Type: application/json' \
        -d '{"org_slug":"acme","email":"you@acme.io","password":"s3cret-pass"}' \
        | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
   # Use the token — tenant is derived from it, no X-Tenant-ID needed:
   curl -s http://localhost:8000/v1/auth/me        -H "Authorization: Bearer $TOKEN"
   curl -s http://localhost:8000/v1/artifacts      -H "Authorization: Bearer $TOKEN"
   ```
   Expected: user created; `/auth/me` returns it; artifact calls are scoped to the token's tenant.
   Business routes require a token (members); the first user of an org is its admin, and
   admin-only operations (e.g. `DELETE /v1/artifacts/{id}`, `GET /v1/organizations/members`)
   return 403 for non-admins.

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
    structured understanding (`task_type`, `entities`, `constraints`, `open_questions`,
    `confidence`, `method: "heuristic-v1"`); the same CATR is written onto the prompt
    version. The worker must be running (`docker compose up worker`). The analysis is a
    deterministic heuristic, **not** an LLM — see the `kompilo-pipeline` skill.

---

## Architecture notes

- **Multi-tenant RLS.** `organizations` is the tenant root. The API connects as a
  least-privilege Postgres role (`kompilo_app`, `NOSUPERUSER`) subject to Row-Level
  Security. Each request pins the active tenant via `SET LOCAL app.tenant_id`; every
  tenant-owned table has an `ENABLE`+`FORCE` RLS policy filtering by `tenant_id`, so
  tenants cannot read each other's rows. Migrations run as the superuser (`kompilo`),
  which owns the tables. See the `kompilo-rls` skill.
- **Secrets.** Never committed; everything flows through `.env` (git-ignored).
- **STUB stages.** `backend/app/engines/stages.py` returns placeholder output
  until real reasoning is implemented. Nothing stubbed is presented as real.

## Useful commands

```bash
# Backend unit tests (no external services needed)
cd backend && pip install -e ".[dev]" && pytest

# New migration after changing models
docker compose exec backend alembic revision --autogenerate -m "describe change"
docker compose exec backend alembic upgrade head

# Lint / format / type-check
cd backend && ruff check . && black --check . && mypy app

# Frontend production build
cd frontend && npm run build
```

## Continuous Integration

`.github/workflows/ci.yml` runs on every push and pull request:

- **backend-quality** — `ruff check` (lint), `black --check` (format), `mypy --strict`, unit tests.
- **backend-integration** — spins up PostgreSQL (pgvector), runs the real
  `infra/postgres/init/01-init.sh`, applies migrations as the superuser, then runs
  the RLS isolation tests as the least-privilege app role.
- **frontend-build** — `npm ci` + typecheck + `vite build` from the committed lockfile.

Conventions for changing CI (reproducibility, adding jobs/services, debugging a
red pipeline) are captured in the `kompilo-ci` skill.
