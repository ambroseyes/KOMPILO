---
name: kompilo-rls
description: >-
  Enforce Kompilo's strict multi-tenant isolation via PostgreSQL Row-Level
  Security (RLS). Use when adding or reviewing a tenant-scoped table or model,
  writing an Alembic migration that touches tenant data, writing or auditing an
  RLS policy, wiring a new tenant-scoped endpoint, or debugging a suspected
  cross-tenant data leak. Triggers: multi-tenant, tenant isolation, RLS,
  row-level security, tenant_id, SET LOCAL app.current_tenant, new tenant
  table / migration / policy, "can tenant A see tenant B's rows".
---

# Kompilo — Multi-tenant isolation (PostgreSQL RLS)

This skill is the single source of truth for keeping tenants isolated. Follow it
whenever tenant data is created, migrated, queried, or reviewed. A mistake here
is a **silent** cross-tenant data leak — the system keeps working while leaking.

Reference implementation already in the repo:
- `backend/app/core/tenancy.py` — the GUC helper (`apply_tenant_guc`)
- `backend/app/api/deps.py` — `get_tenant_session` (pins the tenant per request)
- `backend/app/models/tenant.py` — `PipelineRun` (example tenant-scoped model)
- `backend/app/migrations/versions/0001_initial.py` — the RLS policy
- `infra/postgres/init/01-init.sh` — the least-privilege `kompilo_app` role

---

## The invariant (NEVER break these 4 facts)

1. **The app connects as `kompilo_app`** — a role that is `NOSUPERUSER` and does
   **not own** the tables. RLS is bypassed for superusers and table owners, so
   the app must never connect as `kompilo` (superuser) or any table owner.
   Migrations (and only migrations) run as the superuser.
2. **Every request pins its tenant inside a transaction** via
   `SET LOCAL app.current_tenant = '<uuid>'` (done by `apply_tenant_guc`, called
   from `get_tenant_session`). `SET LOCAL` is transaction-scoped and resets on
   commit/rollback — this is what makes connection pooling safe.
3. **Fail-closed.** `current_setting('app.current_tenant', true)` returns `NULL`
   when unset, so a policy comparing to it matches **zero rows**. The `true`
   (missing_ok) second argument is mandatory — without it an unset GUC raises.
4. **Every tenant-scoped table has `tenant_id uuid NOT NULL`** plus a policy with
   **both** `USING` and `WITH CHECK`.

---

## Checklist — adding a TENANT-SCOPED table

Do every step. Skipping one is how leaks happen.

- [ ] Model: inherit the mixins and add `tenant_id: Mapped[uuid.UUID]`,
      `nullable=False`, `index=True`, FK to `tenants.id` with `ondelete="CASCADE"`.
- [ ] Register the model in `backend/app/models/__init__.py` (so Alembic sees it).
- [ ] Migration: create the table, then `ENABLE ROW LEVEL SECURITY` and
      `CREATE POLICY tenant_isolation ... USING (...) WITH CHECK (...)`.
- [ ] Access the table **only** through `TenantSession` (`get_tenant_session`),
      never through the plain `DbSession` / `get_db`.
- [ ] Never set `tenant_id` from client input on writes — take it from the
      authenticated tenant (`TenantId` dependency). The `WITH CHECK` is the
      backstop, not the primary guard.
- [ ] Add an isolation test (see `references/test_rls_isolation.py`).
- [ ] If the table is referenced by a FK from another tenant table, confirm the
      referenced table is also tenant-scoped (no cross-tenant FK targets).

A **control table** (like `tenants` itself: a registry not owned by one tenant)
is the exception — no `tenant_id`, no policy, accessed via `DbSession`. Keep
these few and obvious, and never put tenant business data in one.

---

## Snippets (copy, then adapt names)

### 1. Model — `backend/app/models/<entity>.py`
```python
class Artifact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """TENANT-SCOPED — RLS policy created in the migration."""
    __tablename__ = "artifacts"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # ... business columns ...
```

### 2. Migration — enable RLS + policy (run after `create_table`)
```python
op.execute("ALTER TABLE artifacts ENABLE ROW LEVEL SECURITY")
op.execute(
    """
    CREATE POLICY tenant_isolation ON artifacts
    USING      (tenant_id = current_setting('app.current_tenant', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid)
    """
)
# downgrade(): op.execute("DROP POLICY IF EXISTS tenant_isolation ON artifacts")
```

### 3. Endpoint — tenant-scoped session + server-set tenant_id
```python
from app.api.deps import TenantSession, TenantId

@router.post("/artifacts", response_model=ArtifactRead, status_code=201)
async def create_artifact(payload: ArtifactCreate, tenant_id: TenantId,
                          db: TenantSession) -> Artifact:
    art = Artifact(tenant_id=tenant_id, **payload.model_dump())  # tenant_id from auth, NOT client
    db.add(art)
    await db.flush()
    await db.refresh(art)
    return art

@router.get("/artifacts", response_model=list[ArtifactRead])
async def list_artifacts(db: TenantSession) -> list[Artifact]:
    # RLS filters to the current tenant automatically.
    return list((await db.execute(select(Artifact))).scalars().all())
```

---

## Pitfalls that cause SILENT cross-tenant leaks

1. **App connects as superuser or table owner** → RLS skipped entirely. The app
   role must be `NOSUPERUSER` and not the owner. (Owner reads also bypass RLS
   unless `FORCE ROW LEVEL SECURITY`; our app isn't the owner, so we rely on
   that — never change the app to own the tables.)
2. **Plain `SET` instead of `SET LOCAL` / `set_config(..., true)`** → the setting
   leaks to the next request sharing the pooled connection. Always transaction-local.
3. **Committing mid-request before your reads** → the `SET LOCAL` is gone for the
   next statement. Keep the tenant's reads/writes in the one request transaction.
4. **Missing `WITH CHECK`** → `INSERT`/`UPDATE` can write a row with another
   tenant's `tenant_id`. Always include both `USING` and `WITH CHECK`.
5. **`tenant_id` nullable** → a NULL `tenant_id` interacts badly with a NULL GUC.
   Keep it `NOT NULL`.
6. **Dropping the `true` in `current_setting('app.current_tenant', true)`** → an
   unset GUC raises instead of failing closed.
7. **Querying a tenant table via `DbSession`** (no GUC set) → RLS matches zero
   rows (fail-closed, so no leak) but the feature silently returns nothing. Use
   `TenantSession`.
8. **Trusting client-supplied `tenant_id` on writes** → always derive it from the
   authenticated tenant; treat `WITH CHECK` as defense-in-depth, not the gate.
9. **New table created outside Alembic** → it won't inherit the default
   privileges granted in `01-init.sh`; grant explicitly and add the policy.

---

## Prove it (do not trust, verify)

Run the isolation test template in `references/test_rls_isolation.py`: it seeds
two tenants, writes a row under each, and asserts that a session scoped to
tenant A sees **only** A's row (and that an unset tenant sees nothing). Any new
tenant-scoped table should get an equivalent assertion.

Quick manual check against a running stack (see repo README step 7):
```bash
# As tenant A (dev header), list — must never contain tenant B's rows.
curl -s localhost:8000/api/v1/me/pipeline-runs -H 'X-Tenant-ID: <A>'
# No tenant at all → 401 (fail-closed).
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/api/v1/me/pipeline-runs
```

---

## When reviewing a diff, reject it if

- a tenant table has no policy, or a policy missing `USING` or `WITH CHECK`;
- a route reads/writes a tenant table through `DbSession`;
- `tenant_id` comes from the request body/query on a write;
- a migration enables RLS but the `downgrade()` doesn't drop the policy;
- anything makes the app role a superuser or a table owner.
