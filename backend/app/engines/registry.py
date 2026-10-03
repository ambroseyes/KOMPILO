"""Typed loader for the Model Capability Registry (``model_registry.yaml``).

Each entry is validated into a :class:`~app.schemas.registry.ModelCapability`; a missing
mandatory field (e.g. ``last_verified``) or an unknown ``reasoning_strength`` fails the
load loudly rather than silently degrading routing.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from app.schemas.registry import ModelCapability

_DEFAULT_PATH = Path(__file__).parent / "model_registry.yaml"


def load_model_registry(path: Path | None = None) -> list[ModelCapability]:
    source = path or _DEFAULT_PATH
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    entries = raw.get("models", []) if isinstance(raw, dict) else []
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"Model registry at {source} has no 'models' entries")
    return [ModelCapability.model_validate(entry) for entry in entries]


@lru_cache(maxsize=1)
def default_registry() -> tuple[ModelCapability, ...]:
    """Cached default registry (immutable tuple) for the router."""
    return tuple(load_model_registry())
