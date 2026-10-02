# Contributing to Kompilo

Short, enforced conventions. The quality gates (CI + pre-commit) make most of
this automatic.

## Branches

| Branch        | Purpose                                                        |
|---------------|---------------------------------------------------------------|
| `main`        | Production-ready. Protected; only merged via PR.              |
| `develop`     | Integration branch for the next release.                      |
| `feature/*`   | One branch per feature/fix, branched off `develop`.          |

- Name feature branches `feature/<area>-<short-desc>` (e.g. `feature/auth-jwt-login`).
- Open PRs into `develop`; `develop` → `main` for releases.
- Keep branches short-lived; rebase on `develop` before opening the PR.

> Note: the current bootstrap work lives on `claude/loving-mccarthy-3p5j0f`
> (PR #1 → `main`). Once merged, adopt the flow above.

## Commit messages — Conventional Commits

Format: `type(scope): subject` — imperative, lower-case, no trailing period.

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`,
`ci`, `chore`, `revert`.

Examples:
```
feat(artifacts): add tenant-scoped CRUD with RLS
fix(health): report db=ko instead of 500 when the database is down
ci: run black and mypy on pull requests
```
Breaking changes: add `!` after the type/scope (`feat(api)!: ...`) and a
`BREAKING CHANGE:` footer.

## Local setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Python 3.12
pip install -e ".[dev]"
pre-commit install            # from the repo root; enables hooks on commit
```

## Run the quality gates locally

```bash
cd backend
ruff check .            # lint
black --check .         # format check (use `black .` to apply)
mypy app                # strict type-check
pytest tests --ignore=tests/integration -q   # unit tests (no services)
```

All green looks like: `All checks passed!` (ruff), `… files would be left
unchanged` (black), `Success: no issues found` (mypy), and `N passed` (pytest).

### Integration tests (need PostgreSQL)

```bash
docker compose up -d postgres
cd backend
# init runs automatically via docker-compose; then migrate as superuser:
ALEMBIC_DATABASE_URL=postgresql+asyncpg://kompilo:<pwd>@localhost:5432/kompilo \
  JWT_SECRET=dev-jwt-secret-0123456789abcdefg \
  DATABASE_URL=postgresql+asyncpg://kompilo_app:<pwd>@localhost:5432/kompilo \
  alembic upgrade head
DATABASE_URL=postgresql+asyncpg://kompilo_app:<pwd>@localhost:5432/kompilo \
  JWT_SECRET=dev-jwt-secret-0123456789abcdefg pytest tests/integration -q
```

## Before pushing

`pre-commit` runs ruff + black automatically. CI then re-checks ruff, black,
mypy, the unit tests, the PostgreSQL RLS integration tests, and the frontend
build. Push only once local gates are green.
