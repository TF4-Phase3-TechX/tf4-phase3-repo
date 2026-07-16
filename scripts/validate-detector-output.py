#!/usr/bin/env python3
"""Validate one detector JSONL event against the TF4AIO-40 schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


def load_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON payload: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", required=True, help="Path to the JSON Schema file")
    parser.add_argument("--line", help="A single JSONL line to validate")
    parser.add_argument("--file", help="File containing a single JSON line or JSONL stream")
    args = parser.parse_args()

    schema_path = Path(args.schema)
    schema = load_json(schema_path.read_text(encoding="utf-8"))

    if args.line:
        payload_text = args.line
    elif args.file:
        payload_text = Path(args.file).read_text(encoding="utf-8").splitlines()[0]
    else:
        payload_text = sys.stdin.read().strip()
        if not payload_text:
            parser.error("provide --line, --file, or pipe a JSONL line on stdin")

    payload = load_json(payload_text)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda err: list(err.path))

    if errors:
        for error in errors:
            path = ".".join(str(part) for part in error.path) or "<root>"
            print(f"{path}: {error.message}", file=sys.stderr)
        return 1

    print("Detector payload is valid against the schema.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
