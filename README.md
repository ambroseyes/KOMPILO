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

> **Status:** project skeleton. The pipeline stages are **STUB** implementations
> (responses carry `is_stub: true`). The surrounding architecture — database,
> multi-tenant RLS isolation, migrations, workers, tooling — is real, not mocked.

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
   # Create a dev tenant, grab its id:
   curl -s -X POST http://localhost:8000/v1/tenants \
        -H 'Content-Type: application/json' \
        -d '{"slug":"acme","name":"Acme"}' | python3 -m json.tool
   # List runs scoped to that tenant (empty list, RLS-filtered):
   curl -s http://localhost:8000/v1/me/pipeline-runs \
        -H 'X-Tenant-ID: <paste-tenant-id>'
   ```
   Expected: tenant created; the scoped list returns `[]` (and 401 without a tenant).

---

## Architecture notes

- **Multi-tenant RLS.** The API connects as a least-privilege Postgres role
  (`kompilo_app`, `NOSUPERUSER`) that is subject to Row-Level Security. Each
  request pins the active tenant via `SET LOCAL app.current_tenant`; the
  `pipeline_runs` table has an RLS policy filtering by `tenant_id`, so tenants
  cannot read each other's rows. Migrations run as the superuser (`kompilo`),
  which owns the tables.
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
