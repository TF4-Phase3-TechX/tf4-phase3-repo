"""Strict schemas and input validation for external drift series."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .common import parse_timestamp


PACKAGE_ROOT = Path(__file__).resolve().parent
SCHEMA_ROOT = PACKAGE_ROOT / "schemas"


@lru_cache(maxsize=None)
def validator(schema_name: str) -> Draft202012Validator:
    schema = json.loads(
        (SCHEMA_ROOT / schema_name).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate(value: Any, schema_name: str) -> None:
    errors = sorted(
        validator(schema_name).iter_errors(value),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = ".".join(str(item) for item in error.absolute_path) or "<root>"
        raise ValueError(f"{schema_name}:{path}: {error.message}")


def load_json(path: Path, schema_name: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    validate(value, schema_name)
    return value


def load_observations(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    event_ids: set[str] = set()
    previous_timestamp = None
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw_line.strip():
            continue
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
        validate(row, "observation.schema.json")
        event_id = row["event_id"]
        if event_id in event_ids:
            raise ValueError(f"{path}:{line_number}: duplicate event_id {event_id!r}")
        event_ids.add(event_id)
        observed_at = parse_timestamp(row["observed_at"])
        if previous_timestamp is not None and observed_at < previous_timestamp:
            raise ValueError(
                f"{path}:{line_number}: observed_at must be non-decreasing"
            )
        previous_timestamp = observed_at
        rows.append(row)
    if not rows:
        raise ValueError(f"{path}: at least one observation is required")
    return rows
