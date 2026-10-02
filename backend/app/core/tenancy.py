"""Multi-tenant isolation via PostgreSQL Row-Level Security (RLS).

Isolation model
---------------
* ``organizations`` is the tenant root; ``organizations.id`` IS the tenant id.
* Every tenant-owned table carries a non-null ``tenant_id`` and an RLS policy
  ``USING (tenant_id = current_setting('app.tenant_id', true)::uuid)``.
* The app connects as a least-privilege role (``kompilo_app``) that is NOT a
  table owner and NOT a superuser, so RLS is always enforced for it.
* At the start of each request's transaction we pin the active tenant with
  ``set_config('app.tenant_id', '<uuid>', true)``.

Why TRANSACTION-LOCAL (the ``true`` = is_local flag), never session-level
---------------------------------------------------------------------------
``set_config(key, value, true)`` (equivalent to ``SET LOCAL``) scopes the value
to the CURRENT TRANSACTION and PostgreSQL resets it automatically at COMMIT or
ROLLBACK. The API runs behind a connection pool: one physical connection serves
many requests/tenants over its lifetime. A SESSION-level ``SET`` (is_local=false)
would persist on the connection after the request returns; the next request to
borrow that connection would inherit the previous tenant's id and read or write
its data — a silent cross-tenant leak. Transaction-local scoping guarantees the
setting cannot outlive the request, so pooling is safe.

If no tenant is set, the policy matches no rows — the system fails CLOSED. The
policies wrap the GUC in ``NULLIF(current_setting('app.tenant_id', true), '')``
because on a pooled connection a prior ``SET LOCAL`` leaves the custom GUC as an
empty string after reset (not NULL), and a bare ``''::uuid`` cast would raise
instead of returning zero rows.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Request-scoped current tenant, set by the API dependency layer.
_current_tenant: ContextVar[uuid.UUID | None] = ContextVar("current_tenant", default=None)


def set_current_tenant(tenant_id: uuid.UUID | None) -> None:
    _current_tenant.set(tenant_id)


def get_current_tenant() -> uuid.UUID | None:
    return _current_tenant.get()


async def apply_tenant_guc(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Pin the tenant for the CURRENT TRANSACTION (enables RLS filtering).

    Uses ``set_config('app.tenant_id', value, true)`` — the parameterised,
    injection-safe, transaction-local equivalent of ``SET LOCAL`` (see the module
    docstring for why session-level would leak across pooled connections).
    """
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": str(tenant_id)},
    )
