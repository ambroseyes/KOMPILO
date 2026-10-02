# Kompilo — one-command developer tasks.
#
# The backend commands prefer the project venv (backend/.venv) when present, and fall
# back to the ambient `python` otherwise. The single command to run EVERYTHING is:
#
#     make test
#
# which runs the full backend suite (unit tests always; integration tests run when a
# migrated Postgres + Redis are reachable, and skip cleanly otherwise).

BACKEND := backend
PYBIN   := if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python; fi

# Safe defaults so the suite imports and unit tests run out of the box. A real shell
# env (or .env via docker compose) overrides these; the placeholder DB is simply
# unreachable, so integration tests skip cleanly unless a real Postgres is provided.
DATABASE_URL ?= postgresql+asyncpg://user:pass@localhost:5432/placeholder
JWT_SECRET   ?= insecure-dev-secret-change-me-0123456789abcdef
export DATABASE_URL JWT_SECRET

.PHONY: help test test-unit test-integration lint fmt typecheck check frontend-build

help:  ## List the available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

test:  ## Run the FULL backend test suite (unit + integration when a DB is reachable)
	cd $(BACKEND) && $$( $(PYBIN) ) -m pytest

test-unit:  ## Unit tests only — no database needed
	cd $(BACKEND) && $$( $(PYBIN) ) -m pytest --ignore=tests/integration

test-integration:  ## Integration tests — needs a migrated Postgres + Redis
	cd $(BACKEND) && $$( $(PYBIN) ) -m pytest tests/integration

lint:  ## Ruff lint
	cd $(BACKEND) && $$( $(PYBIN) ) -m ruff check app tests

fmt:  ## Black format (in place)
	cd $(BACKEND) && $$( $(PYBIN) ) -m black app tests

typecheck:  ## mypy (strict, on app)
	cd $(BACKEND) && $$( $(PYBIN) ) -m mypy app

check: lint typecheck test  ## All backend gates (lint + types + tests)

frontend-build:  ## Typecheck + production build of the frontend
	cd frontend && npm run build
