"""Authentication: register (DEV bootstrap), login (JWT), and current user.

Users are tenant-scoped, so an org must be named at the auth boundary. The org is
resolved by slug via the ``kompilo_resolve_org`` SECURITY DEFINER function (RLS on
``organizations`` otherwise blocks a pre-login lookup). The tenant is then pinned
transaction-local so INSERT/SELECT pass RLS.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.core.tenancy import apply_tenant_guc
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserRead

router = APIRouter()


async def _resolve_org_id(db: AsyncSession, slug: str) -> uuid.UUID | None:
    result = await db.execute(text("SELECT kompilo_resolve_org(:slug)"), {"slug": slug})
    row = result.scalar_one_or_none()
    return None if row is None else uuid.UUID(str(row))


@router.post(
    "/auth/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a user in an organization (DEV bootstrap only)",
)
async def register(payload: RegisterRequest, db: DbSession) -> User:
    if settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-registration is disabled in production",
        )
    org_id = await _resolve_org_id(db, payload.org_slug)
    if org_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    # Pin the tenant so the user INSERT satisfies the RLS WITH CHECK.
    await apply_tenant_guc(db, org_id)
    # Bootstrap: the first user of an org becomes its admin.
    is_first_user = (await db.execute(select(func.count(User.id)))).scalar_one() == 0
    user = User(
        tenant_id=org_id,
        email=payload.email.strip().lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        is_org_admin=is_first_user,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists in this organization",
        ) from exc
    await db.refresh(user)
    return user


@router.post("/auth/login", response_model=TokenResponse, summary="Log in and receive a JWT")
async def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    org_id = await _resolve_org_id(db, payload.org_slug)
    if org_id is None:
        raise invalid

    await apply_tenant_guc(db, org_id)
    email = payload.email.strip().lower()
    user = (await db.execute(select(User).where(User.email == email))).scalars().first()
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.hashed_password)
    ):
        raise invalid

    token = create_access_token(subject=str(user.id), tenant_id=str(org_id))
    return TokenResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get("/auth/me", response_model=UserRead, summary="Current authenticated user")
async def me(user: CurrentUser) -> User:
    return user
