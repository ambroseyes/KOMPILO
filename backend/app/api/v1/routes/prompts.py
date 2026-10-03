"""Tenant-scoped CRUD for prompts and their versions — authenticated + RLS.

A prompt belongs to a project (created/listed under ``/projects/{id}/prompts``);
individual prompts are addressed flatly (``/prompts/{id}``). Prompt versions are an
append-only, monotonically-numbered history under ``/prompts/{id}/versions``.

Invariants (see the ``kompilo-rls`` / ``kompilo-crud`` skills):
- ``tenant_id`` / ``author_id`` / ``created_by`` / ``project_id`` are server-set.
- the next ``version`` is ``max(version) + 1`` computed over ALL rows (including
  soft-deleted ones), so numbers are never reused and never collide with the full
  ``UNIQUE (tenant_id, prompt_id, version)`` constraint.
- deletion is a soft delete (org admin only); versions are never deleted.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, OrgAdmin, TenantSession, get_current_user
from app.engines.version_comparator import ComparatorError, VersionComparator, VersionUnderTest
from app.engines.version_manager import VersionManager
from app.models.project import Project
from app.models.prompt import Prompt, PromptVersion
from app.schemas.benchmark import CompareRequest, VersionComparison
from app.schemas.common import Page
from app.schemas.prompt import (
    PromptCreate,
    PromptCreateFlat,
    PromptRead,
    PromptUpdate,
    PromptVersionCreate,
    PromptVersionRead,
)
from app.schemas.version import (
    SaveCompilationRequest,
    SaveCompilationResponse,
    VersionDiff,
)

router = APIRouter(dependencies=[Depends(get_current_user)])
_versions = VersionManager()
_comparator = VersionComparator()


async def _load_version_under_test(
    db: AsyncSession, prompt_id: uuid.UUID, version: int
) -> VersionUnderTest:
    """Load a version and project it to the compiled prompt a comparison executes.

    Prefers the stored ``content`` (the render selected at save time); falls back to any
    available render. A version with no compiled prompt (e.g. created before the compiler)
    cannot be executed, so the comparison is refused with a 422 rather than guessing.
    """
    stmt = select(PromptVersion).where(
        PromptVersion.prompt_id == prompt_id,
        PromptVersion.version == version,
        PromptVersion.deleted_at.is_(None),
    )
    pv = (await db.execute(stmt)).scalars().first()
    if pv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Version {version} not found"
        )
    text = pv.content
    if not text and isinstance(pv.renders, dict):
        text = (
            pv.renders.get("professional") or pv.renders.get("compact") or pv.renders.get("expert")
        )
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Version {version} has no compiled prompt to execute",
        )
    return VersionUnderTest(version=pv.version, prompt_text=text, source_intent=pv.source_intent)


async def _get_active_project(db: AsyncSession, project_id: uuid.UUID) -> Project:
    stmt = select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    project = (await db.execute(stmt)).scalars().first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def _get_active_prompt(db: AsyncSession, prompt_id: uuid.UUID) -> Prompt:
    stmt = select(Prompt).where(Prompt.id == prompt_id, Prompt.deleted_at.is_(None))
    prompt = (await db.execute(stmt)).scalars().first()
    if prompt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found")
    return prompt


# ── Prompts ────────────────────────────────────────────────────────────────────
async def _insert_prompt(
    db: AsyncSession, *, user: CurrentUser, project_id: uuid.UUID, payload: PromptCreate
) -> Prompt:
    await _get_active_project(db, project_id)  # 404 if missing / cross-tenant / deleted
    prompt = Prompt(
        tenant_id=user.tenant_id,
        project_id=project_id,
        created_by=user.id,
        slug=payload.slug,
        name=payload.name,
        description=payload.description,
        tags=payload.tags,
    )
    db.add(prompt)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A prompt with slug '{payload.slug}' already exists in this project",
        ) from exc
    await db.refresh(prompt)
    return prompt


@router.post(
    "/projects/{project_id}/prompts",
    response_model=PromptRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a prompt in a project",
)
async def create_prompt(
    project_id: uuid.UUID, payload: PromptCreate, user: CurrentUser, db: TenantSession
) -> Prompt:
    return await _insert_prompt(db, user=user, project_id=project_id, payload=payload)


@router.post(
    "/prompts",
    response_model=PromptRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a prompt (flat — project_id in the body)",
)
async def create_prompt_flat(
    payload: PromptCreateFlat, user: CurrentUser, db: TenantSession
) -> Prompt:
    create = PromptCreate(
        slug=payload.slug, name=payload.name, description=payload.description, tags=payload.tags
    )
    return await _insert_prompt(db, user=user, project_id=payload.project_id, payload=create)


@router.get(
    "/prompts",
    response_model=Page[PromptRead],
    summary="List prompts (library) — filter by project/tags/text, paginated",
)
async def list_prompts_library(
    db: TenantSession,
    project_id: Annotated[uuid.UUID | None, Query(description="Restrict to one project.")] = None,
    tag: Annotated[
        list[str] | None, Query(description="Repeatable; a prompt must carry ALL given tags (AND).")
    ] = None,
    q: Annotated[str | None, Query(max_length=255, description="Search name/slug/desc.")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[PromptRead]:
    """Tenant-scoped via RLS. Tag filtering uses the GIN-indexed ``tags @> ARRAY[...]``
    containment operator; text search is a case-insensitive ILIKE over name/slug/desc."""
    conditions: list[ColumnElement[bool]] = [Prompt.deleted_at.is_(None)]
    if project_id is not None:
        conditions.append(Prompt.project_id == project_id)
    if tag:
        wanted = [t.strip().lower() for t in tag if t.strip()]
        if wanted:
            conditions.append(Prompt.tags.contains(wanted))  # tags @> ARRAY[...]
    if q:
        like = f"%{q.strip()}%"
        conditions.append(
            Prompt.name.ilike(like) | Prompt.slug.ilike(like) | Prompt.description.ilike(like)
        )

    total = int(
        (await db.execute(select(func.count()).select_from(Prompt).where(*conditions))).scalar_one()
    )
    stmt = (
        select(Prompt)
        .where(*conditions)
        .order_by(Prompt.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).scalars().all()
    items = [PromptRead.model_validate(p) for p in rows]
    return Page[PromptRead](items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/projects/{project_id}/prompts",
    response_model=list[PromptRead],
    summary="List prompts in a project",
)
async def list_prompts(project_id: uuid.UUID, db: TenantSession) -> list[Prompt]:
    await _get_active_project(db, project_id)  # 404 if the project is gone
    stmt = (
        select(Prompt)
        .where(Prompt.project_id == project_id, Prompt.deleted_at.is_(None))
        .order_by(Prompt.created_at)
    )
    return list((await db.execute(stmt)).scalars().all())


@router.get("/prompts/{prompt_id}", response_model=PromptRead, summary="Get a prompt")
async def get_prompt(prompt_id: uuid.UUID, db: TenantSession) -> Prompt:
    return await _get_active_prompt(db, prompt_id)


@router.patch("/prompts/{prompt_id}", response_model=PromptRead, summary="Update a prompt")
async def update_prompt(prompt_id: uuid.UUID, payload: PromptUpdate, db: TenantSession) -> Prompt:
    prompt = await _get_active_prompt(db, prompt_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(prompt, field, value)
    await db.flush()
    await db.refresh(prompt)
    return prompt


@router.delete(
    "/prompts/{prompt_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a prompt and its versions (org admin only)",
)
async def delete_prompt(prompt_id: uuid.UUID, admin: OrgAdmin, db: TenantSession) -> Response:
    prompt = await _get_active_prompt(db, prompt_id)
    deleted_at = func.now()
    await db.execute(
        update(PromptVersion)
        .where(PromptVersion.prompt_id == prompt_id, PromptVersion.deleted_at.is_(None))
        .values(deleted_at=deleted_at)
    )
    prompt.deleted_at = deleted_at
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Prompt versions (append-only history) ───────────────────────────────────────
async def _next_version(db: AsyncSession, prompt_id: uuid.UUID) -> int:
    """Next version number for a prompt: ``max(version) + 1`` over ALL rows.

    Soft-deleted versions are intentionally counted so a number is never reused and
    never collides with the full ``UNIQUE (tenant_id, prompt_id, version)``
    constraint. RLS scopes the aggregate to the caller's tenant.
    """
    stmt = select(func.coalesce(func.max(PromptVersion.version), 0)).where(
        PromptVersion.prompt_id == prompt_id
    )
    return int((await db.execute(stmt)).scalar_one()) + 1


@router.post(
    "/prompts/{prompt_id}/versions",
    response_model=PromptVersionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create the next version of a prompt",
)
async def create_prompt_version(
    prompt_id: uuid.UUID, payload: PromptVersionCreate, user: CurrentUser, db: TenantSession
) -> PromptVersion:
    await _get_active_prompt(db, prompt_id)  # 404 if missing / cross-tenant / deleted
    version = await _next_version(db, prompt_id)
    prompt_version = PromptVersion(
        tenant_id=user.tenant_id,
        prompt_id=prompt_id,
        author_id=user.id,
        version=version,
        source_intent=payload.source_intent,
        content=payload.content,
        catr=payload.catr,
        ir=payload.ir,
        renders=payload.renders,
        diagnostics=payload.diagnostics,
        model_target=payload.model_target,
    )
    db.add(prompt_version)
    try:
        await db.flush()
    except IntegrityError as exc:
        # Lost a race to allocate this version number; the client should retry.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Version allocation conflict; please retry",
        ) from exc
    await db.refresh(prompt_version)
    return prompt_version


@router.post(
    "/prompts/{prompt_id}/compilations",
    response_model=SaveCompilationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Compile a task server-side and save it as the prompt's next version",
)
async def save_compilation(
    prompt_id: uuid.UUID, payload: SaveCompilationRequest, user: CurrentUser, db: TenantSession
) -> SaveCompilationResponse:
    """The compile is run by Kompilo Core here (not trusted from the client), so the
    stored snapshot (catr / ir / renders / diagnostics) always reflects a real run."""
    await _get_active_prompt(db, prompt_id)  # 404 if missing / cross-tenant / deleted
    version, compiled = await _versions.save_compilation(
        db, prompt_id=prompt_id, tenant_id=user.tenant_id, author_id=user.id, req=payload
    )
    await db.refresh(version)
    return SaveCompilationResponse(
        version=PromptVersionRead.model_validate(version), compile=compiled
    )


@router.get(
    "/prompts/{prompt_id}/versions",
    response_model=list[PromptVersionRead],
    summary="List a prompt's versions (oldest first)",
)
async def list_prompt_versions(prompt_id: uuid.UUID, db: TenantSession) -> list[PromptVersion]:
    await _get_active_prompt(db, prompt_id)
    stmt = (
        select(PromptVersion)
        .where(PromptVersion.prompt_id == prompt_id, PromptVersion.deleted_at.is_(None))
        .order_by(PromptVersion.version)
    )
    return list((await db.execute(stmt)).scalars().all())


@router.get(
    "/prompts/{prompt_id}/versions/diff",
    response_model=VersionDiff,
    summary="Neutral diff between two versions of a prompt",
)
async def diff_prompt_versions(
    prompt_id: uuid.UUID,
    db: TenantSession,
    from_version: Annotated[int, Query(ge=1, description="The baseline version number.")],
    to_version: Annotated[int, Query(ge=1, description="The version to compare against.")],
) -> VersionDiff:
    """Declared BEFORE ``/versions/{version}`` so the literal ``diff`` segment is not
    coerced to an int. The diff is neutral — it never says which version is 'better'."""
    await _get_active_prompt(db, prompt_id)
    return await _versions.diff(db, prompt_id, from_version, to_version)


@router.post(
    "/prompts/{prompt_id}/versions/compare",
    response_model=VersionComparison,
    summary="Measured comparison of two versions (which is better, by how much, regressions)",
)
async def compare_prompt_versions(
    prompt_id: uuid.UUID,
    payload: CompareRequest,
    user: CurrentUser,
    db: TenantSession,
) -> VersionComparison:
    """Run each version's compiled prompt over the same case set, measure with the Evaluator
    (rules-v1), and return a numbers-backed verdict. Unlike the neutral diff, this ranks the
    versions — honestly flagged as not meaningful when the offline Echo STUB produced the
    outputs (no real provider key)."""
    await _get_active_prompt(db, prompt_id)
    a = await _load_version_under_test(db, prompt_id, payload.from_version)
    b = await _load_version_under_test(db, prompt_id, payload.to_version)
    try:
        return await _comparator.compare(
            prompt_id=prompt_id, a=a, b=b, cases=payload.cases, tenant_id=str(user.tenant_id)
        )
    except ComparatorError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get(
    "/prompts/{prompt_id}/versions/{version}",
    response_model=PromptVersionRead,
    summary="Get a specific version of a prompt by its number",
)
async def get_prompt_version(
    prompt_id: uuid.UUID, version: int, db: TenantSession
) -> PromptVersion:
    await _get_active_prompt(db, prompt_id)
    stmt = select(PromptVersion).where(
        PromptVersion.prompt_id == prompt_id,
        PromptVersion.version == version,
        PromptVersion.deleted_at.is_(None),
    )
    prompt_version = (await db.execute(stmt)).scalars().first()
    if prompt_version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prompt version not found"
        )
    return prompt_version
