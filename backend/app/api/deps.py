"""Shared FastAPI dependencies: DB sessions and tenant resolution."""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_access_token
from app.core.tenancy import apply_tenant_guc, set_current_tenant
from app.db.session import async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Plain session with no tenant scope (admin/system/control-table use)."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tenant identifier",
        ) from exc


async def get_current_tenant_id(
    authorization: Annotated[str | None, Header()] = None,
    x_tenant_id: Annotated[str | None, Header()] = None,
) -> uuid.UUID:
    """Resolve the active tenant from a Bearer JWT (``tid`` claim).

    DEV-ONLY fallback: outside production, an ``X-Tenant-ID`` header is accepted
    so tenant isolation can be exercised before the auth endpoints exist.
    """
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            claims = decode_access_token(token)
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            ) from exc
        tid = claims.get("tid")
        if not tid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing tenant scope",
            )
        return _parse_uuid(str(tid))

    # DEV-ONLY fallback — never allowed in production.
    if not settings.is_production and x_tenant_id:
        return _parse_uuid(x_tenant_id)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing authentication",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_tenant_session(
    tenant_id: Annotated[uuid.UUID, Depends(get_current_tenant_id)],
) -> AsyncGenerator[AsyncSession, None]:
    """Tenant-scoped DB session: pins ``app.current_tenant`` so RLS applies."""
    set_current_tenant(tenant_id)
    async with async_session_factory() as session:
        await apply_tenant_guc(session, tenant_id)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Convenience aliases for route signatures.
DbSession = Annotated[AsyncSession, Depends(get_db)]
TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]
TenantId = Annotated[uuid.UUID, Depends(get_current_tenant_id)]
