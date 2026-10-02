---
name: kompilo-auth
description: >-
  Implement or review Kompilo authentication, JWT handling, RBAC and tenant-context
  injection. Use when adding/changing signup, login, refresh, password hashing, JWT
  claims or token types, the current-principal dependency, role checks (owner/admin/
  member), or how the tenant GUC is set from the token. Triggers: auth, JWT, access
  token, refresh token, token type, signup, login, password hashing, bcrypt, argon2,
  current_principal, require_role, RBAC, owner/admin/member, SET LOCAL app.tenant_id,
  tenant from token, safe error messages, /docs Authorize button.
---

# Kompilo — authentication, RBAC & tenant context

How identity, roles and the tenant GUC fit together. Builds on `kompilo-rls`
(isolation) and `kompilo-crud` (routes). Reference: `app/core/security.py`,
`app/core/roles.py`, `app/api/deps.py`, `app/api/v1/routes/auth.py`,
`app/models/user.py`, `app/schemas/auth.py`.

## The invariants (never break)

1. **Tenant comes from the signed token, never the body/query.** Login/signup/refresh
   put `tid` (and `role`) in the JWT; `get_current_tenant_id` reads `tid` and
   `get_tenant_session` sets it transaction-local (`set_config('app.tenant_id', tid,
   true)` = `SET LOCAL`), so RLS applies. A client-supplied tenant is only ever a
   DEV `X-Tenant-ID` fallback, disabled in production.
2. **Secrets from the env.** `JWT_SECRET` (>=32 bytes) via settings; never hardcoded.
3. **Passwords hashed.** bcrypt over a SHA-256 pre-hash (`app/core/security.py`) —
   full entropy, never exceeds bcrypt's 72-byte limit. Never store or log plaintext.
4. **Uniform auth errors.** Login/refresh return one generic message ("Invalid
   credentials" / "Invalid refresh token") for every failure mode (unknown org,
   unknown email, wrong password, inactive) — no account/enumeration leak.
5. **Role is the single source of truth** (`users.role`, owner/admin/member). Derive
   conveniences from it (`User.is_org_admin` is a property), never a second column.

## Tokens (access + refresh)

- Two token types, distinguished by a `type` claim: `access` (short exp,
  `access_token_expire_minutes`) and `refresh` (long exp,
  `refresh_token_expire_minutes`). Both carry `sub`, `tid`, `role`, `iat`, `exp`.
- `decode_token(token, expected_type=...)` enforces the type: an access token is
  rejected at `/auth/refresh` and a refresh token can't be used as an API bearer —
  both raise `jwt.PyJWTError`, surfaced as 401. Always decode with the expected type.
- **Refresh reloads the user** (under RLS) to pick up the current role and reject
  deactivated users, then **rotates** (issues a new refresh alongside the new access).
- Stateless (no server-side revocation list yet). If you add revocation/reuse
  detection, do it here behind the same endpoints.

## Dependencies (two complementary gates)

- `get_current_principal` → `Principal{user_id, tenant_id, role}` built from the access
  token's claims (no DB). Fast identity + role for RBAC.
- `get_current_user` → the `User` loaded under the tenant session (re-checks
  `is_active`). Use where freshness/the full row matters (mutations).
- `get_tenant_session` → opens the transaction and pins `app.tenant_id` from the
  token. Tenant-owned tables are reached ONLY through it (see `kompilo-rls`).

## RBAC

- `require_role(*allowed)` builds a dependency that 403s unless `principal.role` is
  allowed: `principal: Annotated[Principal, Depends(require_role("owner", "admin"))]`.
- `require_org_admin` (DB-backed, owner/admin) stays for mutating routes that already
  load the user. Enforce roles SERVER-SIDE on the route — never trust the client.
- Bootstrap: signup's user is the `owner`; `register` makes the first org user owner,
  the rest members.

## Swagger (/docs) usability

Auth reads the raw `Authorization` header, so declare an `HTTPBearer(auto_error=False)`
dependency (`bearer_scheme` in `deps.py`) on the entry deps. It does NOT enforce auth
(the code still does), it only makes OpenAPI advertise the scheme so `/docs` shows the
**Authorize** button and 🔒 icons. Flow: run `POST /auth/signup` or `/auth/login` →
copy `access_token` → Authorize → call protected endpoints.

## Checklist for an auth change

- [ ] Secrets via settings/env; `JWT_SECRET` length enforced.
- [ ] New claims added to BOTH token builders and read via `decode_token(expected_type)`.
- [ ] Tenant taken from `tid`, pinned via `get_tenant_session`; never from the body.
- [ ] Role checks server-side (`require_role` / `require_org_admin`).
- [ ] Uniform error messages; no enumeration.
- [ ] Migration if the user/role shape changes (revision id <= 32 chars; use the
      metadata naming convention — pass the SHORT constraint name, e.g. `name="role"`
      → `ck_users_role`).
- [ ] Tests: no-DB (validation, token-type rejection) + integration (signup, login,
      refresh, 401 without token, 200 with token, 403 for the wrong role).

## When reviewing a diff, reject it if

- tenant/role is taken from the request body/query instead of the token;
- a secret is hardcoded, or a password is stored/logged in plaintext;
- access and refresh tokens aren't type-separated (a refresh token works as a bearer);
- login/refresh leak which factor failed (distinct messages / status for unknown
  user vs wrong password);
- a role is checked only client-side, or `is_org_admin` is reintroduced as a column;
- a new JWT claim is added to one token builder but not read with the expected type.
