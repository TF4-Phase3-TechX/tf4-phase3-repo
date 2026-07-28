"""Shared fail-closed helpers for Mandate 24 evidence commands."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def validate_trace_id(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not TRACE_ID_RE.fullmatch(normalized) or normalized == "0" * 32:
        raise ValueError("trace_id must be a non-zero 32-character lowercase hex value")
    return normalized


def request_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: each row must be an object")
        yield value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
