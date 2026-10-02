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


def create_access_token(
    subject: str,
    *,
    tenant_id: str,
    expires_minutes: int | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT carrying the subject and tenant scope (``tid``)."""
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=expires_minutes or settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "tid": tenant_id,
        "iat": now,
        "exp": expire,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT. Raises ``jwt.PyJWTError`` on invalid/expired tokens."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
