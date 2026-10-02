"""Verifier v1 — validate an output against its contract (format + optional schema).

Deterministic and dependency-free. For a JSON output it parses the text and, when an
``output_schema`` is given, checks required fields and property types (one level, with
recursion into nested object/array schemas). The report says exactly WHAT is missing or
invalid — never a single pass/fail with no explanation.

The schema is a small JSON-Schema subset: ``{"type": "object", "required": [...],
"properties": {name: {"type": "string|number|integer|boolean|object|array|null", ...}}}``.
"""

from __future__ import annotations

import json
from typing import Any

from app.schemas.verify import VerificationIssue, VerificationReport

_JSON_TYPES: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "object": dict,
    "array": list,
    "null": type(None),
}


def _type_ok(value: Any, json_type: str) -> bool:
    expected = _JSON_TYPES.get(json_type)
    if expected is None:
        return True  # unknown type in the schema → don't block
    if json_type == "integer" and isinstance(value, bool):
        return False  # bool is a subclass of int; a boolean is not an integer
    if json_type == "number" and isinstance(value, bool):
        return False
    return isinstance(value, expected)


def _validate(value: Any, schema: dict[str, Any], path: str) -> list[VerificationIssue]:
    issues: list[VerificationIssue] = []
    declared = schema.get("type")

    if declared is not None and not _type_ok(value, str(declared)):
        issues.append(
            VerificationIssue(
                kind="type_mismatch",
                path=path or "$",
                detail=f"expected {declared}, got {type(value).__name__}",
            )
        )
        return issues  # type is wrong → deeper checks are meaningless

    if declared == "object" or (declared is None and isinstance(value, dict)):
        if not isinstance(value, dict):
            return issues
        for req in schema.get("required", []):
            if req not in value:
                issues.append(
                    VerificationIssue(
                        kind="missing_field",
                        path=f"{path}.{req}" if path else req,
                        detail=f"required field '{req}' is missing",
                    )
                )
        for name, subschema in (schema.get("properties") or {}).items():
            if name in value and isinstance(subschema, dict):
                issues += _validate(value[name], subschema, f"{path}.{name}" if path else name)

    if declared == "array" and isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(value):
                issues += _validate(item, item_schema, f"{path}[{i}]")

    return issues


def verify_output(
    output: str,
    *,
    output_format: str = "markdown",
    output_schema: dict[str, Any] | None = None,
) -> VerificationReport:
    issues: list[VerificationIssue] = []

    if not output.strip():
        issues.append(VerificationIssue(kind="empty_output", detail="output is empty"))
        return VerificationReport(
            valid=False, format=output_format, issues=issues, summary="Output is empty."
        )

    if output_format.lower() == "json":
        try:
            data = json.loads(output)
        except ValueError as exc:
            issues.append(
                VerificationIssue(kind="parse_error", detail=f"invalid JSON: {exc.args[0]}")
            )
            return VerificationReport(
                valid=False,
                format=output_format,
                issues=issues,
                summary="Output is not valid JSON.",
            )
        if output_schema is not None:
            issues += _validate(data, output_schema, "")

    valid = not issues
    if valid:
        summary = f"Output conforms to the {output_format} contract."
    else:
        summary = f"{len(issues)} issue(s): " + "; ".join(i.detail for i in issues[:5])
    return VerificationReport(valid=valid, format=output_format, issues=issues, summary=summary)
