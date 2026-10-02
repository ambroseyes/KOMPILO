"""Version Manager v1 — persist a compilation as a prompt version, and diff two versions.

Responsibilities:
- allocate the next monotonic version number for a prompt (gap-free, never reused);
- ``save_compilation``: run Kompilo Core server-side and snapshot the result
  (``catr`` / ``ir`` / ``renders`` / ``diagnostics``) into a new ``PromptVersion``;
- ``history``: the ordered list of a prompt's live versions;
- ``diff``: a NEUTRAL, structural comparison of two versions.

The diff never declares a version "better": a quality verdict needs a measurement (an
eval), which the MVP does not have. The diff only states *what changed* (see the
``kompilo-library`` skill). Tenant isolation is enforced by RLS on the session.
"""

from __future__ import annotations

import difflib
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.kompilo_core import KompiloCore
from app.models.prompt import PromptVersion
from app.schemas.compile import CompileResponse
from app.schemas.version import (
    DiagnosticDelta,
    FieldChange,
    RenderDiff,
    SaveCompilationRequest,
    ScalarDelta,
    VersionDiff,
)

_RENDER_MODES = ("compact", "professional", "expert")


@dataclass(frozen=True, slots=True)
class VersionSnapshot:
    """The diff-relevant projection of a version (keeps the diff logic DB-free)."""

    version: int
    source_intent: str | None
    model_target: str | None
    catr: dict[str, Any]
    renders: dict[str, Any]
    diagnostics: list[dict[str, Any]]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[dict[str, Any]]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def snapshot_of(pv: PromptVersion) -> VersionSnapshot:
    return VersionSnapshot(
        version=pv.version,
        source_intent=pv.source_intent,
        model_target=pv.model_target,
        catr=_as_dict(pv.catr),
        renders=_as_dict(pv.renders),
        diagnostics=_as_list(pv.diagnostics),
    )


def _scalar_delta(before: str | None, after: str | None) -> ScalarDelta:
    return ScalarDelta(before=before, after=after, changed=before != after)


def _catr_field_changes(a: dict[str, Any], b: dict[str, Any]) -> list[FieldChange]:
    """Top-level key-by-key comparison of two CATR snapshots (stable, sorted)."""
    changes: list[FieldChange] = []
    for key in sorted(set(a) | set(b)):
        in_a, in_b = key in a, key in b
        if in_a and not in_b:
            changes.append(FieldChange(path=key, change="removed", before=a[key], after=None))
        elif in_b and not in_a:
            changes.append(FieldChange(path=key, change="added", before=None, after=b[key]))
        elif a[key] != b[key]:
            changes.append(FieldChange(path=key, change="changed", before=a[key], after=b[key]))
    return changes


def _render_diffs(a: dict[str, Any], b: dict[str, Any]) -> list[RenderDiff]:
    diffs: list[RenderDiff] = []
    for mode in _RENDER_MODES:
        before = str(a.get(mode, "") or "")
        after = str(b.get(mode, "") or "")
        if before == after:
            diffs.append(RenderDiff(mode=mode, changed=False, unified_diff=""))
            continue
        unified = "\n".join(
            difflib.unified_diff(
                before.splitlines(),
                after.splitlines(),
                fromfile=f"{mode}@from",
                tofile=f"{mode}@to",
                lineterm="",
            )
        )
        diffs.append(RenderDiff(mode=mode, changed=True, unified_diff=unified))
    return diffs


def _diagnostic_deltas(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> list[DiagnosticDelta]:
    a_levels = {str(d.get("dimension")): d.get("level") for d in a if d.get("dimension")}
    b_levels = {str(d.get("dimension")): d.get("level") for d in b if d.get("dimension")}
    deltas: list[DiagnosticDelta] = []
    for dim in sorted(set(a_levels) | set(b_levels)):
        before = a_levels.get(dim)
        after = b_levels.get(dim)
        deltas.append(
            DiagnosticDelta(
                dimension=dim,
                before=None if before is None else str(before),
                after=None if after is None else str(after),
                changed=before != after,
            )
        )
    return deltas


def compute_version_diff(
    prompt_id: uuid.UUID, a: VersionSnapshot, b: VersionSnapshot
) -> VersionDiff:
    """Pure, deterministic diff between two snapshots (``a`` = from, ``b`` = to)."""
    catr_fields = _catr_field_changes(a.catr, b.catr)
    renders = _render_diffs(a.renders, b.renders)
    diagnostics = _diagnostic_deltas(a.diagnostics, b.diagnostics)

    n_renders_changed = sum(1 for r in renders if r.changed)
    n_diag_changed = sum(1 for d in diagnostics if d.changed)
    summary = (
        f"v{a.version} → v{b.version} : {len(catr_fields)} champ(s) CATR, "
        f"{n_renders_changed} rendu(s), {n_diag_changed} axe(s) de diagnostic modifié(s)."
    )
    return VersionDiff(
        prompt_id=prompt_id,
        from_version=a.version,
        to_version=b.version,
        source_intent=_scalar_delta(a.source_intent, b.source_intent),
        model_target=_scalar_delta(a.model_target, b.model_target),
        catr_fields=catr_fields,
        renders=renders,
        diagnostics=diagnostics,
        summary=summary,
    )


class VersionManager:
    def __init__(self, core: KompiloCore | None = None) -> None:
        self._core = core or KompiloCore()

    async def next_version(self, db: AsyncSession, prompt_id: uuid.UUID) -> int:
        """``max(version) + 1`` over ALL rows (soft-deleted included) so numbers are
        gap-free and never collide with ``UNIQUE (tenant_id, prompt_id, version)``.
        RLS scopes the aggregate to the caller's tenant."""
        stmt = select(func.coalesce(func.max(PromptVersion.version), 0)).where(
            PromptVersion.prompt_id == prompt_id
        )
        return int((await db.execute(stmt)).scalar_one()) + 1

    async def save_compilation(
        self,
        db: AsyncSession,
        *,
        prompt_id: uuid.UUID,
        tenant_id: uuid.UUID,
        author_id: uuid.UUID | None,
        req: SaveCompilationRequest,
    ) -> tuple[PromptVersion, CompileResponse]:
        """Compile ``req.task`` server-side, then persist the snapshot as a new version.

        The snapshot is derived from Kompilo Core's own output — never trusted from the
        client — so a stored version always reflects a real, reproducible compilation.
        """
        response, catr = await self._core.compile_with_catr(
            req.task,
            target_model=req.target_model,
            mode=req.mode,
            output_format=req.output_format,
            quality_contract=req.quality_contract,
        )

        ir_snapshot = (
            [section.model_dump() for section in response.compiled_prompt.ir]
            if response.compiled_prompt is not None
            else None
        )
        renders_snapshot = response.renders.model_dump() if response.renders is not None else None

        version_num = await self.next_version(db, prompt_id)
        pv = PromptVersion(
            tenant_id=tenant_id,
            prompt_id=prompt_id,
            author_id=author_id,
            version=version_num,
            source_intent=req.source_intent or req.task,
            catr=catr.model_dump(mode="json"),
            ir=ir_snapshot,
            renders=renders_snapshot,
            diagnostics=[d.model_dump() for d in response.diagnostics],
            model_target=response.metadata.target_model,
        )
        db.add(pv)
        try:
            await db.flush()
        except IntegrityError as exc:  # lost the race to allocate this number
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Version allocation conflict; please retry",
            ) from exc
        await db.refresh(pv)
        return pv, response

    async def history(self, db: AsyncSession, prompt_id: uuid.UUID) -> list[PromptVersion]:
        stmt = (
            select(PromptVersion)
            .where(PromptVersion.prompt_id == prompt_id, PromptVersion.deleted_at.is_(None))
            .order_by(PromptVersion.version)
        )
        return list((await db.execute(stmt)).scalars().all())

    async def _get_version(
        self, db: AsyncSession, prompt_id: uuid.UUID, version: int
    ) -> PromptVersion:
        stmt = select(PromptVersion).where(
            PromptVersion.prompt_id == prompt_id,
            PromptVersion.version == version,
            PromptVersion.deleted_at.is_(None),
        )
        pv = (await db.execute(stmt)).scalars().first()
        if pv is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version {version} not found for this prompt",
            )
        return pv

    async def diff(
        self, db: AsyncSession, prompt_id: uuid.UUID, from_version: int, to_version: int
    ) -> VersionDiff:
        a = await self._get_version(db, prompt_id, from_version)
        b = await self._get_version(db, prompt_id, to_version)
        return compute_version_diff(prompt_id, snapshot_of(a), snapshot_of(b))
