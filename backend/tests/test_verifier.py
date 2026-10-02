"""No-DB unit tests for the Verifier v1 (format + JSON-schema validation)."""

from __future__ import annotations

import json

from app.engines.verifier import verify_output

_SCHEMA = {
    "type": "object",
    "required": ["title", "count"],
    "properties": {
        "title": {"type": "string"},
        "count": {"type": "integer"},
        "meta": {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}},
    },
}


def test_valid_json_without_schema() -> None:
    report = verify_output('{"a": 1}', output_format="json")
    assert report.valid is True
    assert report.issues == []


def test_valid_json_matching_schema() -> None:
    out = json.dumps({"title": "Hello", "count": 3, "meta": {"ok": True}})
    report = verify_output(out, output_format="json", output_schema=_SCHEMA)
    assert report.valid is True


def test_invalid_json_is_detected() -> None:
    report = verify_output("{not json", output_format="json")
    assert report.valid is False
    assert any(i.kind == "parse_error" for i in report.issues)


def test_missing_required_field_is_detected() -> None:
    report = verify_output('{"title": "x"}', output_format="json", output_schema=_SCHEMA)
    assert report.valid is False
    missing = [i for i in report.issues if i.kind == "missing_field"]
    assert any(i.path == "count" for i in missing)


def test_type_mismatch_is_detected() -> None:
    out = json.dumps({"title": "x", "count": "three"})  # count should be integer
    report = verify_output(out, output_format="json", output_schema=_SCHEMA)
    assert report.valid is False
    assert any(i.kind == "type_mismatch" and i.path == "count" for i in report.issues)


def test_nested_missing_field_has_dotted_path() -> None:
    out = json.dumps({"title": "x", "count": 1, "meta": {}})  # meta.ok missing
    report = verify_output(out, output_format="json", output_schema=_SCHEMA)
    assert report.valid is False
    assert any(i.path == "meta.ok" for i in report.issues)


def test_empty_output_is_invalid() -> None:
    report = verify_output("   ", output_format="markdown")
    assert report.valid is False
    assert report.issues[0].kind == "empty_output"


def test_non_json_format_passes_when_non_empty() -> None:
    report = verify_output("# A heading\n\nsome text", output_format="markdown")
    assert report.valid is True
