"""Multi-tenant isolation via PostgreSQL Row-Level Security (RLS).

Isolation model
---------------
* Every tenant-scoped table carries a ``tenant_id`` column and an RLS policy:
      USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
* The app connects as a least-privilege role (``kompilo_app``) which is NOT the
  table owner and NOT a superuser, so RLS is always enforced for it.
* At the start of each request's transaction we pin the active tenant with the
  parameterised equivalent of ``SET LOCAL app.current_tenant = '<uuid>'``.
  ``SET LOCAL`` is transaction-scoped and resets automatically, so tenants can
  never leak across requests on a pooled connection.

If no tenant is set, ``current_setting('app.current_tenant', true)`` returns
NULL and the policy matches no rows — the system fails CLOSED.
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
    """Pin the tenant for the current transaction (enables RLS filtering).

    Uses ``set_config(key, value, is_local => true)`` — the parameterised,
    injection-safe equivalent of ``SET LOCAL``.
    """
    await session.execute(
        text("SELECT set_config('app.current_tenant', :tid, true)"),
        {"tid": str(tenant_id)},
    )
