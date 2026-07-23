#!/usr/bin/env python3
"""Score externally supplied Mandate 14 JSONL observations."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scorer import aggregate, score_case


def load_jsonl(path: Path) -> list[dict]:
    cases = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        case = json.loads(raw)
        required = {"case_id", "surface", "category", "human_pass", "expected", "observed"}
        missing = required - set(case)
        if missing:
            raise ValueError(f"{path}:{line_number}: missing {sorted(missing)}")
        if case["surface"] not in {"review_summary", "copilot"}:
            raise ValueError(f"{path}:{line_number}: unsupported surface")
        cases.append(case)
    if not cases:
        raise ValueError("dataset is empty")
    return cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    raw = args.input.read_bytes()
    cases = load_jsonl(args.input)
    results = [score_case(case) for case in cases]
    report = {
        "schema_version": "mandate14-observation-v1",
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "per_case": results,
        "aggregate": aggregate(results),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["aggregate"], ensure_ascii=False, indent=2))
    return 0 if report["aggregate"]["hard_bars_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
