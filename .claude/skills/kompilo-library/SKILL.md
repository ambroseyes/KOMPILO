---
name: kompilo-library
description: >-
  Work on Kompilo's prompt library and version manager. Use when changing the prompt
  CRUD/library routes (tags, filtering, pagination), the Version Manager (save a
  compilation as a version, history, diff), or the frontend Library page. Triggers:
  prompt library, /v1/prompts, tags, tag filter, pagination, Page, version_manager,
  save_compilation, prompt version, version diff, compute_version_diff, VersionDiff,
  no verdict without measurement, library page, PromptDetail.
---

# Kompilo — prompt library & version manager

Reference: `app/api/v1/routes/prompts.py`, `app/engines/version_manager.py`,
`app/schemas/{prompt,version,common}.py`, `app/models/prompt.py`,
`frontend/src/components/{LibraryPage,PromptDetail,SignInBar}.tsx`, `frontend/src/lib/auth.tsx`.

## Data model

- A `Prompt` belongs to a `Project`; it carries `tags: text[]` (GIN-indexed, migration
  0010). Tags are normalized on write: lowercased, trimmed, de-duplicated, ≤20, each ≤63
  chars. A `PromptVersion` is append-only and monotonically numbered; it snapshots
  `catr` / `ir` / `renders` / `diagnostics` (opaque JSON — typed `Any`, objects OR arrays).
- Version numbers are `max(version)+1` over ALL rows (soft-deleted counted) so a number is
  never reused and never collides with `UNIQUE (tenant_id, prompt_id, version)`.

## Routes (authenticated, tenant-scoped via RLS)

- `POST /v1/prompts` (flat; `project_id` in body) and `POST /projects/{id}/prompts` both
  create — they share `_insert_prompt`.
- `GET /v1/prompts` — the library list: filters `project_id`, repeatable `tag` (AND via
  `tags @> ARRAY[...]`), `q` (ILIKE over name/slug/description), and `limit`/`offset`
  pagination. Returns a `Page[PromptRead]` (`items`, `total`, `limit`, `offset`).
- `POST /v1/prompts/{id}/compilations` — compiles the task **server-side** (Kompilo Core,
  never trusting a client payload) and saves the snapshot as the next version.
- `GET /v1/prompts/{id}/versions` — history; `GET …/versions/diff?from_version=&to_version=`
  — the diff. The diff route is declared BEFORE `…/versions/{version}` so the literal
  `diff` segment is not coerced to an int.

## Version Manager

- `save_compilation` runs `KompiloCore.compile_with_catr` (the CATR is absent from the
  public `CompileResponse`, so the core exposes it to the persister) and snapshots
  catr/ir/renders/diagnostics.
- `compute_version_diff(a, b)` is a PURE, deterministic diff (DB-free, unit-tested):
  scalar deltas (source_intent, model_target), top-level CATR field changes
  (added/removed/changed), per-mode render `difflib` unified diffs, and diagnostic level
  deltas aligned by dimension.
- **Never declare a version "better".** A quality verdict needs a measurement (an eval),
  which the MVP does not have. The diff states WHAT changed and the `note` says so
  explicitly ("aucun verdict sans mesure"). Keep the summary neutral too.

## Frontend

- Auth token is held IN MEMORY only (`lib/auth.tsx`) — no browser storage. `SignInBar`
  logs in via `/v1/auth/login`. `LibraryPage` lists with search/tags/project + pagination;
  `PromptDetail` shows versions, saves a compilation, and renders a neutral diff.

## When reviewing a diff, reject it if

- tags are stored unnormalized, or tag filtering is not tenant-scoped / not index-friendly;
- the list has no pagination, or `total` is the page length rather than the full count;
- a saved version trusts a client-provided catr/ir/renders instead of compiling server-side;
- the version diff (or its UI) implies which version is "better" / "improved";
- the diff route is ordered after `/versions/{version}` (so `diff` 422s as a bad int);
- the auth token is persisted to localStorage/sessionStorage.
