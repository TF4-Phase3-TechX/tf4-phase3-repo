"""Compare matched baseline/candidate replay latency for instrumentation overhead."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import median
from typing import Any

try:  # Support both `python -m` and direct script execution.
    from .common import read_jsonl, write_json
except ImportError:
    from common import read_jsonl, write_json  # type: ignore


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("at least one latency value is required")
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def compare(
    baseline_path: Path,
    candidate_path: Path,
    max_p95_increase_percent: float,
) -> dict[str, Any]:
    if max_p95_increase_percent < 0:
        raise ValueError("max p95 increase must be non-negative")
    baseline = {
        str(row["case_id"]): float(row["latency_ms"])
        for row in read_jsonl(baseline_path)
    }
    candidate = {
        str(row["case_id"]): float(row["latency_ms"])
        for row in read_jsonl(candidate_path)
    }
    if set(baseline) != set(candidate) or not baseline:
        raise ValueError("baseline and candidate must contain the same case IDs")
    baseline_values = list(baseline.values())
    candidate_values = list(candidate.values())
    baseline_p95 = _p95(baseline_values)
    candidate_p95 = _p95(candidate_values)
    increase_percent = (
        ((candidate_p95 - baseline_p95) / baseline_p95) * 100
        if baseline_p95 > 0
        else 0.0
    )
    return {
        "schema_version": "mandate24-overhead-v1",
        "matched_cases": len(baseline),
        "baseline_p50_ms": median(baseline_values),
        "candidate_p50_ms": median(candidate_values),
        "baseline_p95_ms": baseline_p95,
        "candidate_p95_ms": candidate_p95,
        "p95_increase_percent": increase_percent,
        "threshold_percent": max_p95_increase_percent,
        "pass": increase_percent <= max_p95_increase_percent,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--max-p95-increase-percent", type=float, default=5.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = compare(
        args.baseline,
        args.candidate,
        args.max_p95_increase_percent,
    )
    write_json(args.output, report)
    print(json.dumps(report, sort_keys=True))
    if not report["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
