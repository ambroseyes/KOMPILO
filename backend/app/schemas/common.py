"""Shared Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel


class HealthComponent(BaseModel):
    name: str
    ok: bool
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: str  # "ok" | "degraded"
    components: list[HealthComponent]
