---
name: kompilo-crud
description: >-
  Build a tenant-scoped CRUD resource module in Kompilo the correct way:
  authenticated routes, server-set ownership, soft-delete, slug reuse, and
  monotonic versioning. Use when adding or reviewing REST endpoints for a
  tenant-owned entity (projects, prompts, prompt_versions, executions, …), when
  wiring create/list/get/update/delete, when a resource needs soft-delete or an
  auto-incrementing version, or when choosing a uniqueness constraint for a
  slug/name. Triggers: CRUD, endpoint, route module, soft-delete, deleted_at,
  slug uniqueness, "reuse a slug after delete", versioning, next version number,
  append-only history, cascade delete, 409 conflict, created_by/author_id.
---

# Kompilo — tenant-scoped CRUD, soft-delete & versioning

This skill is the pattern for every tenant-owned REST resource. It sits ON TOP of
`kompilo-rls` (read that first): RLS isolates tenants; this skill says how to shape
the routes, ownership, deletion and versioning. Reference implementation in the
repo: `backend/app/api/v1/routes/projects.py` and `.../prompts.py`, schemas in
`backend/app/schemas/project.py` / `prompt.py`, migration
`0006_partial_unique_slugs.py`.

## The 6 rules (never break these)

1. **Router-level auth.** `router = APIRouter(dependencies=[Depends(get_current_user)])`.
   Every route then runs inside the tenant-scoped session (RLS active) and has a
   real user. Use `TenantSession` for the DB, never the plain `DbSession`.
2. **Ownership is server-set.** On create, take `tenant_id=user.tenant_id` and
   `created_by`/`author_id`=`user.id` from `CurrentUser` — NEVER from the request
   body/path. Keep these fields out of the `*Create` schema entirely.
3. **Parent id from the PATH, not the body.** For nested resources
   (`/projects/{project_id}/prompts`) the `project_id` comes from the URL; validate
   the parent is live-and-owned first (`_get_active_*` → 404) before inserting.
4. **404, never 403, for a foreign/missing row.** RLS makes other tenants' rows
   invisible, so "not found in my tenant" and "doesn't exist" are indistinguishable
   — return 404. Reserve 403 for a role gate (`OrgAdmin`) that fires BEFORE the DB.
5. **Deletion is soft + admin-only + cascading.** See below.
6. **Translate `IntegrityError` to 409.** A unique-constraint hit on create is a
   client conflict, not a 500. Catch it at `flush()` and raise
   `HTTPException(409, ...)`; the session dependency rolls back.

## Soft-delete (content tables)

Content models carry `SoftDeleteMixin` (`deleted_at`). Soft-delete means the DELETE
endpoint sets `deleted_at`, it does not remove the row.

- **Filter every read** with `.where(Model.deleted_at.is_(None))`. `db.get(pk)`
  bypasses this (PK lookup), so use a `select(...).where(id==, deleted_at IS NULL)`
  helper (`_get_active_*`) for the active-or-404 fetch — not `db.get`.
- **Cascade by hand.** FK `ON DELETE CASCADE` only fires on a HARD delete. For a
  soft delete, cascade with bulk `update()` statements to the children first, then
  the parent, all sharing one `deleted_at = func.now()` (now() is transaction-stable
  in Postgres, so timestamps match). RLS scopes each `update()` to the tenant.
- **Gate it.** Deletion takes `admin: OrgAdmin` (destructive). Read/create/update
  are open to any authenticated member unless the product says otherwise.

### Slug reuse after soft-delete → PARTIAL unique index

A full `UNIQUE (tenant_id, slug)` keeps a soft-deleted slug reserved forever (a
footgun). Use a **partial** unique index scoped to live rows so a slug frees up on
delete:

```python
# model __table_args__:
Index("uq_projects_tenant_id_slug", "tenant_id", "slug",
      unique=True, postgresql_where=text("deleted_at IS NULL"))
# migration (swap the old constraint, keep the name):
op.drop_constraint("uq_projects_tenant_id_slug", "projects", type_="unique")
op.create_index("uq_projects_tenant_id_slug", "projects", ["tenant_id", "slug"],
                unique=True, postgresql_where=sa.text("deleted_at IS NULL"))
```

Two LIVE rows still can't share a slug; any number of soft-deleted ones can. Keep
the model's `__table_args__` and the migration head in sync (no autogenerate drift).

## Monotonic versioning (append-only history)

For a numbered child (e.g. `prompt_versions` with `UNIQUE (tenant_id, prompt_id,
version)`):

- Allocate the next number as `max(version) + 1` **over ALL rows, including
  soft-deleted ones** — so a number is never reused and never collides with the
  FULL unique constraint. Keep that constraint FULL (not partial), unlike slugs.
  ```python
  select(func.coalesce(func.max(PromptVersion.version), 0)).where(
      PromptVersion.prompt_id == prompt_id)  # RLS adds tenant_id
  ```
- Versions are **append-only**: no update of payloads in place, no delete endpoint.
  Soft-delete reaches them only via the parent's cascade.
- Concurrency: two simultaneous creates can pick the same number; the unique
  constraint guarantees only one wins, the loser gets `IntegrityError` → 409
  "please retry". Correct over clever — do not silently reorder or skip numbers.

## PATCH schema rule

All update fields optional with defaults; apply with `model_dump(exclude_unset=True)`
so omitted = unchanged and explicit `null` = clear (for nullable columns). For a
NOT NULL column (e.g. `name`), add a `field_validator` that rejects an explicit
`null` → 422 instead of a 500 at flush. `slug` is immutable: leave it out of
`*Update` entirely.

## Checklist for a new resource

- [ ] Model: `kompilo-rls` checklist done (TenantMixin, registered, RLS migration).
- [ ] Schemas: `*Create` (no tenant_id/owner/parent-id), `*Update` (optional + null
      guards, no slug), `*Read` (`from_attributes=True`).
- [ ] Route module: router-level `get_current_user`; `_get_active_*` helpers;
      server-set ownership; 404 for misses; 409 on IntegrityError.
- [ ] Soft-delete: admin-gated, cascading, reads filtered; partial unique index for
      any reusable slug.
- [ ] Register the router in `app/api/v1/router.py`.
- [ ] Tests: a no-DB unit test (401 on every route) + an integration test (CRUD,
      cross-tenant isolation = 404/empty, role gate = 403, versioning increments,
      cascade + slug reuse). Run the gates: ruff, black, mypy, pytest.

## When reviewing a diff, reject it if

- a tenant resource route reads/writes without `get_current_user` / `TenantSession`;
- `tenant_id`, `created_by`, `author_id`, or a parent id is taken from client input;
- a read of a soft-deletable table doesn't filter `deleted_at IS NULL`
  (or uses `db.get` for an active-or-404 fetch);
- a soft-delete leaves children live (no cascade);
- a reusable slug uses a full unique constraint instead of a partial one;
- a version number is computed ignoring soft-deleted rows (collision risk);
- an `IntegrityError` surfaces as a 500 instead of a 409.
