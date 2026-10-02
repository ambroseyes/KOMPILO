"""Unit tests for the Version Manager's pure diff logic (no DB, deterministic).

The diff must describe WHAT changed between two versions and never imply which is
"better" — a quality verdict needs a measurement the MVP does not have.
"""

from __future__ import annotations

import uuid

from app.engines.version_manager import VersionSnapshot, compute_version_diff


def _snap(
    version: int,
    *,
    source_intent: str | None = None,
    model_target: str | None = None,
    catr: dict | None = None,
    renders: dict | None = None,
    diagnostics: list[dict] | None = None,
) -> VersionSnapshot:
    return VersionSnapshot(
        version=version,
        source_intent=source_intent,
        model_target=model_target,
        catr=catr or {},
        renders=renders or {},
        diagnostics=diagnostics or [],
    )


def test_identical_versions_report_no_changes() -> None:
    a = _snap(
        1,
        source_intent="x",
        model_target="gpt-4o-mini",
        catr={"objective": "o"},
        renders={"compact": "hello", "professional": "hello", "expert": "hello"},
        diagnostics=[{"dimension": "clarity", "level": "high"}],
    )
    diff = compute_version_diff(uuid.uuid4(), a, a)
    assert diff.catr_fields == []
    assert all(not r.changed for r in diff.renders)
    assert all(not d.changed for d in diff.diagnostics)
    assert diff.source_intent.changed is False
    assert diff.model_target.changed is False


def test_catr_field_added_changed_removed() -> None:
    a = _snap(1, catr={"objective": "write a poem", "audience": "kids"})
    b = _snap(2, catr={"objective": "write a sonnet", "domain": "poetry"})
    diff = compute_version_diff(uuid.uuid4(), a, b)
    by_path = {c.path: c for c in diff.catr_fields}
    assert by_path["objective"].change == "changed"
    assert by_path["objective"].before == "write a poem"
    assert by_path["objective"].after == "write a sonnet"
    assert by_path["audience"].change == "removed"  # only in `a`
    assert by_path["domain"].change == "added"  # only in `b`


def test_render_change_produces_unified_diff() -> None:
    a = _snap(1, renders={"compact": "line one\nline two", "professional": "", "expert": ""})
    b = _snap(2, renders={"compact": "line one\nline TWO", "professional": "", "expert": ""})
    diff = compute_version_diff(uuid.uuid4(), a, b)
    compact = next(r for r in diff.renders if r.mode == "compact")
    assert compact.changed is True
    assert "line two" in compact.unified_diff
    assert "line TWO" in compact.unified_diff
    # Unchanged modes carry an empty diff.
    assert next(r for r in diff.renders if r.mode == "professional").changed is False


def test_diagnostic_level_delta_is_neutral() -> None:
    a = _snap(1, diagnostics=[{"dimension": "clarity", "level": "low"}])
    b = _snap(2, diagnostics=[{"dimension": "clarity", "level": "high"}])
    diff = compute_version_diff(uuid.uuid4(), a, b)
    clarity = next(d for d in diff.diagnostics if d.dimension == "clarity")
    assert clarity.before == "low"
    assert clarity.after == "high"
    assert clarity.changed is True
    # A delta carries only before/after/changed — no ranking/direction field.
    assert set(clarity.model_dump()) == {"dimension", "before", "after", "changed"}
    # The summary is neutral (no verdict), and the note explicitly disclaims one.
    assert all(w not in diff.summary.lower() for w in ("meilleur", "better", "improv"))
    assert "sans mesure" in diff.note.lower()


def test_summary_counts_changes() -> None:
    a = _snap(1, source_intent="a", catr={"objective": "o1"}, renders={"compact": "x"})
    b = _snap(3, source_intent="b", catr={"objective": "o2"}, renders={"compact": "y"})
    diff = compute_version_diff(uuid.uuid4(), a, b)
    assert diff.from_version == 1
    assert diff.to_version == 3
    assert "v1 → v3" in diff.summary
