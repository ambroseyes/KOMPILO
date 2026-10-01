---
name: kompilo-ci
description: >-
  Maintain Kompilo's CI so it stays green, reproducible and strict. Use when
  adding or changing a GitHub Actions workflow, adding a quality gate or a test
  job, debugging a red pipeline, adding a service container for integration
  tests, or deciding how to pin dependencies. Triggers: CI, GitHub Actions,
  workflow, pipeline red/failing, ruff, mypy, pytest in CI, service container,
  reproducible build, "why does CI fail but it passes locally".
---

# Kompilo — CI conventions

CI lives in `.github/workflows/ci.yml` with three jobs:

- **backend-quality** — `ruff check`, `ruff format --check`, `mypy --strict`,
  unit tests (`pytest tests --ignore=tests/integration`).
- **backend-integration** — a `pgvector/pgvector:pg16` service, runs the real
  `infra/postgres/init/01-init.sh`, `alembic upgrade head` (superuser), then the
  RLS tests (`pytest tests/integration`) as the least-privilege app role.
- **frontend-build** — `npm ci` + `npm run build` from the committed lockfile.

## Non-negotiable principles

1. **Never loosen a gate to get green.** A red `mypy`/`ruff`/test is a code
   problem — fix the code, not the gate. Don't add `continue-on-error`, don't
   delete assertions, don't `|| true`.
2. **Reproducible = same versions everywhere.** CI must install exactly what was
   validated locally:
   - Pin `ruff` and `mypy` to exact versions in `[project.optional-dependencies].dev`
     (formatting/lint/type results change across versions).
   - Keep runtime dependency ranges aligned with the versions actually tested.
     If you validate locally with newer versions, bump the ranges — do not ship
     ranges that resolve to something you never ran.
3. **One source of truth for DB setup.** The integration job runs the same
   `infra/postgres/init/01-init.sh` that docker-compose runs, so the app role /
   RLS setup is tested, not re-described.
4. **Tool config lives in `pyproject.toml`** (`[tool.ruff]`, `[tool.mypy]`,
   `[tool.pytest.ini_options]`), never duplicated in the workflow. The workflow
   only invokes the tools.

## Validate locally BEFORE pushing (mirror CI exactly)

```bash
cd backend
pip install -e ".[dev]"            # needs Python 3.12 (matches CI)
ruff check .
ruff format --check .
mypy app
pytest tests --ignore=tests/integration -q
```

Integration (needs Docker), reproduces the backend-integration job:
```bash
docker run -d --name ci-pg -e POSTGRES_USER=kompilo -e POSTGRES_PASSWORD=pw \
  -e POSTGRES_DB=kompilo -p 5432:5432 pgvector/pgvector:pg16
# init as a separate step, exactly like CI (psql against the running service):
PGHOST=localhost PGPASSWORD=pw POSTGRES_USER=kompilo POSTGRES_DB=kompilo \
  APP_DB_USER=kompilo_app APP_DB_PASSWORD=app_pw bash infra/postgres/init/01-init.sh
ALEMBIC_DATABASE_URL=postgresql+asyncpg://kompilo:pw@localhost:5432/kompilo \
  DATABASE_URL=postgresql+asyncpg://kompilo_app:app_pw@localhost:5432/kompilo \
  SECRET_KEY=ci-dummy-0123456789 alembic upgrade head
DATABASE_URL=postgresql+asyncpg://kompilo_app:app_pw@localhost:5432/kompilo \
  SECRET_KEY=ci-dummy-0123456789 pytest tests/integration -q
docker rm -f ci-pg
```

## Adding a new backend test job / service

- Put unit tests (no I/O) under `tests/`, integration tests under
  `tests/integration/` (the quality job ignores that dir; the integration job
  runs only that dir).
- Need Redis/another backing service? add it under `services:` with a
  `--health-cmd` and expose its port; set the matching `*_URL` env on the job.
- Every new tenant-scoped table (see the `kompilo-rls` skill) must gain an
  isolation assertion in `tests/integration/` — the integration job is what
  proves RLS, so it must grow with the schema.

## Secrets in CI

Use throwaway values as job `env:` for ephemeral CI resources (DB password,
`SECRET_KEY`). Never put a real secret in the workflow — real secrets go through
GitHub Actions **secrets** (`${{ secrets.NAME }}`) only when a job genuinely
needs to reach a protected resource.

## "Green locally, red in CI" — check in this order

1. Version drift — CI installed a different ruff/mypy/lib than you validated.
   Align the pins (principle 2). This is the most common cause.
2. Python version — CI runs 3.12; `requires-python` and `[tool.mypy] python_version`
   must say `3.12`.
3. Format — run `ruff format .` and commit; `--check` fails on any drift.
4. Integration DB — the app role must be created BEFORE `alembic upgrade`
   (init.sh first), and migrations run as the superuser URL, tests as the app URL.
