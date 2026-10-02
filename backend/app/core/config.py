"""Application configuration.

Settings load from environment variables (and a local .env during development)
via pydantic-settings. No secret ever lives in the codebase.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── App ──────────────────────────────────────────────────────────
    app_name: str = "Kompilo"
    environment: str = "development"
    log_level: str = "INFO"
    api_v1_prefix: str = "/v1"

    # ── Security ─────────────────────────────────────────────────────
    # Read from the JWT_SECRET environment variable (never hardcoded).
    # >= 32 bytes: the minimum recommended HS256 key length (RFC 7518 §3.2).
    jwt_secret: str = Field(..., min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    # Stored as a comma-separated string (avoids pydantic-settings JSON parsing);
    # use `cors_origins_list` where a list is needed.
    cors_origins: str = "http://localhost:5173"

    # ── Database ─────────────────────────────────────────────────────
    # Runtime connection uses the least-privilege app role (RLS enforced).
    database_url: str
    # Admin/superuser connection, used by Alembic migrations only.
    alembic_database_url: str | None = None

    # ── Redis / ARQ ──────────────────────────────────────────────────
    redis_url: str = "redis://redis:6379/0"

    # ── LLM providers (optional; read from the env, never hardcoded) ──
    # Kompilo targets Claude; keys are only required once real stages call out.
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # ── LLM pipeline tuning ──────────────────────────────────────────
    # Model used by the lightweight "understand" analysis stage.
    understand_model: str = "claude-haiku-4-5-20251001"
    # Per-call client timeout (seconds) and bounded retry budget.
    llm_timeout_s: float = 30.0
    llm_max_retries: int = 2
    llm_max_tokens: int = 2048
    # Below this confidence (or with a high-severity ambiguity) the understand
    # stage flags needs_clarification. Derived deterministically by our code.
    understand_confidence_threshold: float = 0.5

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


settings = get_settings()
