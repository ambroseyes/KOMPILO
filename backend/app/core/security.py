"""Security primitives: password hashing and JWT access tokens.

Passwords use bcrypt directly (the unmaintained passlib breaks with bcrypt 5.x).
bcrypt only considers the first 72 bytes of its input, so we SHA-256 the password
first and base64-encode the digest — the password's full entropy is used and no
input ever exceeds bcrypt's limit (the same construction as bcrypt_sha256).
"""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import settings


def _prehash(plain_password: str) -> bytes:
    digest = hashlib.sha256(plain_password.encode("utf-8")).digest()
    return base64.b64encode(digest)  # 44 bytes, always < bcrypt's 72-byte limit


def hash_password(plain_password: str) -> str:
    """Return a bcrypt hash (over the SHA-256 pre-hash) of the password."""
    return bcrypt.hashpw(_prehash(plain_password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plaintext password against a stored hash (constant-time)."""
    try:
        return bcrypt.checkpw(_prehash(plain_password), hashed_password.encode("utf-8"))
    except ValueError:
        return False


#: JWT ``type`` claim values — an access token must never be accepted where a
#: refresh token is required, and vice-versa.
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


def _create_token(
    *,
    subject: str,
    tenant_id: str,
    role: str,
    token_type: str,
    expires_minutes: int,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "tid": tenant_id,
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(
    subject: str, *, tenant_id: str, role: str, expires_minutes: int | None = None
) -> str:
    """Create a short-lived access JWT carrying the subject, tenant and role."""
    return _create_token(
        subject=subject,
        tenant_id=tenant_id,
        role=role,
        token_type=ACCESS_TOKEN_TYPE,
        expires_minutes=expires_minutes or settings.access_token_expire_minutes,
    )


def create_refresh_token(
    subject: str, *, tenant_id: str, role: str, expires_minutes: int | None = None
) -> str:
    """Create a longer-lived refresh JWT (exchanged for a new access token)."""
    return _create_token(
        subject=subject,
        tenant_id=tenant_id,
        role=role,
        token_type=REFRESH_TOKEN_TYPE,
        expires_minutes=expires_minutes or settings.refresh_token_expire_minutes,
    )


def decode_token(token: str, *, expected_type: str) -> dict[str, Any]:
    """Decode a JWT and enforce its ``type`` claim.

    Raises ``jwt.PyJWTError`` on an invalid/expired signature OR a token-type
    mismatch (e.g. a refresh token presented where an access token is required),
    so callers can treat every failure uniformly as "unauthorized".
    """
    claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if claims.get("type") != expected_type:
        raise jwt.InvalidTokenError("unexpected token type")
    return claims
