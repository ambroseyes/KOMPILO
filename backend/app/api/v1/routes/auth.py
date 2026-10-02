"""Authentication: signup, register (DEV), login, refresh, and current user.

Users are tenant-scoped, so an org is named at the auth boundary. Signup creates the
org + its owner atomically. For login/register the org is resolved by slug via the
``kompilo_resolve_org`` SECURITY DEFINER function (RLS on ``organizations`` otherwise
blocks a pre-login lookup); the tenant is then pinned transaction-local so RLS passes.

Error messages are deliberately uniform ("Invalid credentials") so the endpoints
never reveal whether an org, email, or password was the thing that was wrong.
"""

from __future__ import annotations

import uuid

import jwt
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.roles import DEFAULT_ROLE, OWNER_ROLE
from app.core.security import (
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.tenancy import apply_tenant_guc
from app.models.organization import Organization
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    SignupRequest,
    TokenResponse,
    UserRead,
)

router = APIRouter()


async def _resolve_org_id(db: AsyncSession, slug: str) -> uuid.UUID | None:
    result = await db.execute(text("SELECT kompilo_resolve_org(:slug)"), {"slug": slug})
    row = result.scalar_one_or_none()
    return None if row is None else uuid.UUID(str(row))


def _issue_tokens(user: User, org_id: uuid.UUID) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(
            subject=str(user.id), tenant_id=str(org_id), role=user.role
        ),
        refresh_token=create_refresh_token(
            subject=str(user.id), tenant_id=str(org_id), role=user.role
        ),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post(
    "/auth/signup",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an organization and its owner, and receive tokens",
)
async def signup(payload: SignupRequest, db: DbSession) -> TokenResponse:
    # SECURITY DEFINER lookup bypasses RLS to check slug availability pre-tenant.
    if await _resolve_org_id(db, payload.org_slug) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Organization slug already taken"
        )

    org_id = uuid.uuid4()
    # Pin the tenant to the new org id so both INSERTs satisfy the RLS WITH CHECK.
    await apply_tenant_guc(db, org_id)
    db.add(Organization(id=org_id, slug=payload.org_slug, name=payload.org_name))
    owner = User(
        tenant_id=org_id,
        email=payload.email.strip().lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=OWNER_ROLE,
    )
    db.add(owner)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already taken",
        ) from exc
    await db.refresh(owner)
    return _issue_tokens(owner, org_id)


@router.post(
    "/auth/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a user in an existing organization (DEV bootstrap only)",
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
    # Bootstrap: the first user of an org becomes its owner, the rest are members.
    is_first_user = (await db.execute(select(func.count(User.id)))).scalar_one() == 0
    user = User(
        tenant_id=org_id,
        email=payload.email.strip().lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=OWNER_ROLE if is_first_user else DEFAULT_ROLE,
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


@router.post("/auth/login", response_model=TokenResponse, summary="Log in and receive tokens")
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

    return _issue_tokens(user, org_id)


@router.post("/auth/refresh", response_model=TokenResponse, summary="Exchange a refresh token")
async def refresh(payload: RefreshRequest, db: DbSession) -> TokenResponse:
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        claims = decode_token(payload.refresh_token, expected_type=REFRESH_TOKEN_TYPE)
    except jwt.PyJWTError as exc:
        raise invalid from exc

    sub, tid = claims.get("sub"), claims.get("tid")
    if not sub or not tid:
        raise invalid
    try:
        user_id, org_id = uuid.UUID(str(sub)), uuid.UUID(str(tid))
    except ValueError as exc:
        raise invalid from exc

    # Reload the user under RLS to pick up the CURRENT role and revoke inactive users.
    await apply_tenant_guc(db, org_id)
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise invalid

    # Rotate: a fresh refresh token is issued alongside the new access token.
    return _issue_tokens(user, org_id)


@router.get("/auth/me", response_model=UserRead, summary="Current authenticated user")
async def me(user: CurrentUser) -> User:
    return user
