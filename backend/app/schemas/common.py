"""Shared Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    version: str
    db: str  # "ok" | "ko"
