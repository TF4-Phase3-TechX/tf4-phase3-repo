"""Shared, content-safe helpers for live Guardrail evaluation runners."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PINNED_VERSION_RE = re.compile(r"^[1-9][0-9]*$")
SAFE_NAME_RE = re.compile(r"[^a-z0-9_.-]+")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def canonical_json_sha256(value: bytes) -> str:
    """Hash JSON semantics, independent of indentation and line endings."""

    parsed = json.loads(value.decode("utf-8"))
    canonical = json.dumps(
        parsed,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(canonical)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{line_number}: invalid JSON") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path.name}:{line_number}: object required")
        rows.append(row)
    return rows


def require_pinned_guardrail(guardrail_id: str, version: str, region: str) -> None:
    if not guardrail_id or not guardrail_id.strip():
        raise ValueError("non-empty guardrail id required")
    if not PINNED_VERSION_RE.fullmatch(version):
        raise ValueError("guardrail version must be a pinned positive integer, never DRAFT")
    if not region or not region.strip():
        raise ValueError("non-empty AWS region required")


def normalized_error_class(exc: BaseException) -> str:
    """Return bounded error metadata without retaining exception messages."""

    response = getattr(exc, "response", None)
    code: Any = None
    if isinstance(response, dict):
        error = response.get("Error")
        if isinstance(error, dict):
            code = error.get("Code")
    raw = str(code or type(exc).__name__).lower()
    return SAFE_NAME_RE.sub("_", raw).strip("_")[:64] or "unknown_error"


def write_json_report(path: Path, report: dict[str, Any], force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"refusing to overwrite existing report: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
