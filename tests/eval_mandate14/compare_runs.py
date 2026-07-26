#!/usr/bin/env python3
"""Create a like-for-like Mandate 14 before/after comparison."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    results = json.loads((path / "results.json").read_text(encoding="utf-8"))
    return manifest, results


def _delta(before: float, after: float) -> dict[str, float | None]:
    return {
        "before": before,
        "after": after,
        "absolute": after - before,
        "percent": ((after - before) / before * 100) if before else None,
    }


def compare(before_dir: Path, after_dir: Path) -> dict[str, Any]:
    before_manifest, before_results = _load(before_dir)
    after_manifest, after_results = _load(after_dir)
    if before_manifest["dataset_sha256"] != after_manifest["dataset_sha256"]:
        raise ValueError("before/after dataset hashes differ")
    if before_manifest["model"] != after_manifest["model"]:
        raise ValueError("before/after model or guardrail configuration differs")
    before_ids = [item["case_id"] for item in before_results["per_case"]]
    after_ids = [item["case_id"] for item in after_results["per_case"]]
    if before_ids != after_ids:
        raise ValueError("before/after case identities or order differ")

    before_aggregate = before_results["aggregate"]
    after_aggregate = after_results["aggregate"]
    before_performance = before_aggregate["performance"]
    after_performance = after_aggregate["performance"]
    return {
        "schema_version": "mandate14-before-after-v1",
        "dataset_sha256": before_manifest["dataset_sha256"],
        "same_dataset": True,
        "same_model_guardrail": True,
        "case_ids": before_ids,
        "before": {
            "run_id": before_manifest["run_id"],
            "git_sha": before_manifest["git"]["sha"],
            "hard_bars": before_manifest["hard_bars"],
        },
        "after": {
            "run_id": after_manifest["run_id"],
            "git_sha": after_manifest["git"]["sha"],
            "hard_bars": after_manifest["hard_bars"],
        },
        "quality": {
            "case_pass_rate": _delta(
                float(before_aggregate["case_pass"]["rate"]),
                float(after_aggregate["case_pass"]["rate"]),
            ),
            "task_success_rate": _delta(
                float(before_aggregate["task_success"]["rate"]),
                float(after_aggregate["task_success"]["rate"]),
            ),
            "faithfulness_rate": _delta(
                float(before_aggregate["claim_faithfulness"]["rate"]),
                float(after_aggregate["claim_faithfulness"]["rate"]),
            ),
            "hallucination_rate": _delta(
                float(before_aggregate["hallucination"]["rate"]),
                float(after_aggregate["hallucination"]["rate"]),
            ),
            "failed_cases_before": [
                {
                    "case_id": item["case_id"],
                    "failures": item["failures"],
                }
                for item in before_results["per_case"]
                if item["status"] != "pass"
            ],
            "failed_cases_after": [
                {
                    "case_id": item["case_id"],
                    "failures": item["failures"],
                }
                for item in after_results["per_case"]
                if item["status"] != "pass"
            ],
        },
        "performance": {
            "p95_latency_ms": _delta(
                float(before_performance["p95_latency_ms"]),
                float(after_performance["p95_latency_ms"]),
            ),
            "tokens_per_request": _delta(
                float(before_performance["tokens_per_request"]),
                float(after_performance["tokens_per_request"]),
            ),
            "cost_per_request_usd": _delta(
                float(before_performance["cost_per_request_usd"]),
                float(after_performance["cost_per_request_usd"]),
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    comparison = compare(args.before, args.after)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
