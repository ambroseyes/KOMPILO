"""Pytest configuration.

Settings are read at import time, so provide env BEFORE the app is imported.
These values are for unit tests that touch NO external services.
"""

from __future__ import annotations

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-16-chars")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT", "test")
