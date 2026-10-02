"""Auth schemas (register / login / token / current user).

``tenant_id`` is never accepted from the client on data operations. At the auth
boundary the caller names the organization (``org_slug``) to log into — validated
by the password — and the issued token carries ``tid``; everything after is
token-derived.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RegisterRequest(BaseModel):
    org_slug: str = Field(..., min_length=1, max_length=63)
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    org_slug: str = Field(..., min_length=1, max_length=63)
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until expiry


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    full_name: str | None
    is_active: bool
    is_org_admin: bool
    created_at: datetime
