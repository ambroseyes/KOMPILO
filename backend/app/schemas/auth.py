"""Auth schemas (signup / register / login / refresh / token / current user).

``tenant_id`` is never accepted from the client on data operations. At the auth
boundary the caller names the organization (``org_slug``) to act on — created by
signup, validated by the password on login — and the issued tokens carry ``tid`` and
``role``; everything after is token-derived.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.roles import Role

_SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]*$"


class SignupRequest(BaseModel):
    """Create a brand-new organization and its first (owner) user."""

    org_slug: str = Field(..., min_length=1, max_length=63, pattern=_SLUG_PATTERN)
    org_name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class RegisterRequest(BaseModel):
    org_slug: str = Field(..., min_length=1, max_length=63)
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    org_slug: str = Field(..., min_length=1, max_length=63)
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until the ACCESS token expires


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    full_name: str | None
    is_active: bool
    role: Role
    is_org_admin: bool  # derived (owner/admin); kept for convenience
    created_at: datetime
