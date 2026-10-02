"""Pytest configuration.

Settings are read at import time, so provide env BEFORE the app is imported.
These values are for unit tests that touch NO external services.
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-secret-key-at-least-16-chars")
# Unreachable port on purpose: unit tests must never hit a real DB, so
# /v1/health deterministically reports db="ko" here.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://app:app@127.0.0.1:59999/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT", "test")
