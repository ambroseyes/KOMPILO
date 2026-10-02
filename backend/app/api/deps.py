"""Shared FastAPI dependencies: DB sessions and tenant resolution."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.roles import Role
from app.core.security import ACCESS_TOKEN_TYPE, decode_token
from app.core.tenancy import apply_tenant_guc, set_current_tenant
from app.db.session import async_session_factory
from app.models.user import User

# Declared only so Swagger (/docs) shows an "Authorize" button and lock icons.
# auto_error=False: it does NOT enforce auth (we read the header ourselves below and
# keep the dev X-Tenant-ID fallback); it just advertises the bearer scheme in OpenAPI.
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Paste the access_token returned by /v1/auth/login or /v1/auth/signup.",
)
BearerCreds = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


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
    _credentials: BearerCreds = None,
) -> uuid.UUID:
    """Resolve the active tenant from a Bearer JWT (``tid`` claim).

    DEV-ONLY fallback: outside production, an ``X-Tenant-ID`` header is accepted
    so tenant isolation can be exercised before the auth endpoints exist.
    """
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            claims = decode_token(token, expected_type=ACCESS_TOKEN_TYPE)
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
    """Tenant-scoped DB session: pins ``app.tenant_id`` so RLS applies."""
    set_current_tenant(tenant_id)
    async with async_session_factory() as session:
        await apply_tenant_guc(session, tenant_id)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_tenant_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Load the authenticated user from the Bearer token's ``sub`` claim.

    Runs inside the tenant-scoped session, so RLS guarantees the user belongs to
    the token's tenant. Requires a real Bearer token (the dev ``X-Tenant-ID``
    fallback carries no user).
    """
    if not (authorization and authorization.lower().startswith("bearer ")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = decode_token(token, expected_type=ACCESS_TOKEN_TYPE)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc

    subject = claims.get("sub")
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing subject"
        )
    user = await db.get(User, _parse_uuid(str(subject)))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive"
        )
    return user


async def require_org_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Require the authenticated user to be an organization admin (owner/admin).

    DB-backed (loads the user, re-checks ``is_active``), used by mutating routes
    where freshness matters. For lightweight, claims-based gating use ``require_role``.
    """
    if not user.is_org_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization admin role required",
        )
    return user


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller, derived from the access token's claims."""

    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str


async def get_current_principal(
    authorization: Annotated[str | None, Header()] = None,
    _credentials: BearerCreds = None,
) -> Principal:
    """Decode the access token and return ``{user_id, tenant_id, role}``.

    Claims-based (no DB round-trip): fast identity + role for RBAC. The tenant is
    taken from the signed token (``tid``), NEVER from the request body/query.
    """
    if not (authorization and authorization.lower().startswith("bearer ")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = decode_token(token, expected_type=ACCESS_TOKEN_TYPE)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc

    sub, tid, role = claims.get("sub"), claims.get("tid"), claims.get("role")
    if not sub or not tid or not role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")
    return Principal(user_id=_parse_uuid(str(sub)), tenant_id=_parse_uuid(str(tid)), role=str(role))


def require_role(*allowed: Role) -> Callable[[Principal], Awaitable[Principal]]:
    """Build a dependency that allows only the given roles (server-side RBAC).

    Usage: ``principal: Annotated[Principal, Depends(require_role("owner", "admin"))]``.
    """

    async def _dependency(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if principal.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role for this operation",
            )
        return principal

    return _dependency


# Convenience aliases for route signatures.
DbSession = Annotated[AsyncSession, Depends(get_db)]
TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]
TenantId = Annotated[uuid.UUID, Depends(get_current_tenant_id)]
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
OrgAdmin = Annotated[User, Depends(require_org_admin)]
