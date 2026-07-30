"""Replay a mentor-supplied quality series and emit bounded drift signals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .common import write_json
from .contract import load_json, load_observations, validate
from .detector import detect


def replay(
    series_path: Path,
    baseline_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    observations = load_observations(series_path)
    baseline = load_json(baseline_path, "baseline.schema.json")
    report = detect(observations, baseline)
    validate(report, "report.schema.json")
    write_json(output_path, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect model-quality drift in an external JSONL series."
    )
    parser.add_argument("series", type=Path)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fail-on-drift", action="store_true")
    args = parser.parse_args()
    report = replay(args.series, args.baseline, args.output)
    print(
        json.dumps(
            {
                "status": report["status"],
                "signals": len(report["signals"]),
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    if args.fail_on_drift and report["status"] == "drift":
        raise SystemExit(2)


if __name__ == "__main__":
    main()

