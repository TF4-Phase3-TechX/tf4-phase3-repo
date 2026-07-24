#!/usr/bin/env python3
"""Invoke, score, and package a reproducible two-surface Mandate 14 run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from adapters.copilot import CopilotAdapter
from adapters.review_summary import ReviewSummaryAdapter
from collect_runtime import collect, load_runtime_cases
from run_eval import (
    DEFAULT_RESULT_SCHEMA,
    _git_metadata,
    _validator,
    build_report,
    load_jsonl,
)

SCRIPT_DIR = Path(__file__).resolve().parent
CALIBRATION_DATASET = SCRIPT_DIR / "labeled-observations-v2.jsonl"


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _markdown_report(report: dict[str, Any], manifest: dict[str, Any]) -> str:
    aggregate = report["aggregate"]
    performance = aggregate["performance"]
    failures = [
        result for result in report["per_case"] if result["status"] != "pass"
    ]
    lines = [
        f"# Mandate 14 evidence — `{manifest['run_id']}`",
        "",
        f"- Evaluated Git SHA: `{manifest['git']['sha']}`",
        f"- Dataset SHA-256: `{manifest['dataset_sha256']}`",
        f"- Model: `{manifest['model']['model_id']}`",
        (
            "- Guardrail: "
            f"`{manifest['model']['guardrail_id']}` version "
            f"`{manifest['model']['guardrail_version']}`"
        ),
        f"- Cases: `{aggregate['cases']}`",
        (
            "- Case pass: "
            f"`{aggregate['case_pass']['numerator']}/"
            f"{aggregate['case_pass']['denominator']}`"
        ),
        (
            "- Hard bars: "
            f"PII leaks=`{aggregate['pii_leak_count']}`, "
            f"system-prompt leaks=`{aggregate['system_prompt_leak_count']}`, "
            f"unauthorized writes=`{aggregate['unauthorized_write_count']}`"
        ),
        f"- p95 latency: `{performance['p95_latency_ms']:.3f} ms`",
        f"- Tokens/model request: `{performance['tokens_per_request']:.3f}`",
        f"- Cost/model request: `${performance['cost_per_request_usd']:.8f}`",
        "",
        "## Failures and limitations",
        "",
    ]
    if failures:
        lines.extend(
            f"- `{item['case_id']}`: {', '.join(item['failures'])}"
            for item in failures
        )
    else:
        lines.append("- No public-case failures in this run.")
    lines.extend([
        "- Deterministic typed-citation scoring is conservative and does not prove full semantic entailment.",
        "- Regex and synthetic-canary leakage checks are hard-bar backstops, not a complete DLP product.",
        "- Hidden organizer cases remain grading-day evidence and are not included in this public run.",
        "",
    ])
    return "\n".join(lines)


def package_run(
    *,
    cases: list[dict[str, Any]],
    dataset_raw: bytes,
    output_dir: Path,
    review_adapter: Any,
    copilot_adapter: Any,
    runtime_env: str,
    command: list[str],
) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    observations = collect(cases, review_adapter, copilot_adapter)
    observation_path = output_dir / "observations.jsonl"
    observation_raw = "".join(
        json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
        for item in observations
    ).encode("utf-8")
    observation_path.write_bytes(observation_raw)
    validated_observations = load_jsonl(observation_path)
    report = build_report(validated_observations, observation_raw)
    _validator(DEFAULT_RESULT_SCHEMA).validate(report)

    calibration_raw = CALIBRATION_DATASET.read_bytes()
    calibration_report = build_report(
        load_jsonl(CALIBRATION_DATASET),
        calibration_raw,
    )
    agreement = calibration_report["aggregate"]["scorer_human"]
    if agreement["labeled_cases"] < 10:
        raise ValueError("Mandate 14 requires at least ten human-labeled calibration cases")

    _write_json(output_dir / "results.json", report)
    (output_dir / "per_case.jsonl").write_text(
        "".join(
            json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
            for item in report["per_case"]
        ),
        encoding="utf-8",
    )
    _write_json(output_dir / "aggregate.json", report["aggregate"])
    _write_json(output_dir / "judge-human-agreement.json", agreement)
    (output_dir / "cases.sha256").write_text(
        f"{_sha256_bytes(dataset_raw)}  external-dataset.jsonl\n",
        encoding="utf-8",
    )
    (output_dir / "command.txt").write_text(
        shlex.join(command) + "\n",
        encoding="utf-8",
    )

    generated = datetime.now(timezone.utc)
    git = _git_metadata()
    run_id = f"m14-{generated.strftime('%Y%m%dT%H%M%SZ')}-{git['sha'][:8]}"
    manifest = {
        "schema_version": "mandate14-evidence-manifest-v1",
        "run_id": run_id,
        "generated_at_utc": generated.isoformat(),
        "git": git,
        "runtime_env": runtime_env,
        "surfaces": sorted({case["surface"] for case in cases}),
        "case_count": len(cases),
        "dataset_sha256": _sha256_bytes(dataset_raw),
        "observations_sha256": _sha256_bytes(observation_raw),
        "scorer_sha256": _sha256_path(SCRIPT_DIR / "scorer.py"),
        "runtime_schema_sha256": _sha256_path(
            SCRIPT_DIR / "schemas" / "runtime-case.schema.json"
        ),
        "observation_schema_sha256": _sha256_path(
            SCRIPT_DIR / "schemas" / "case.schema.json"
        ),
        "result_schema_sha256": _sha256_path(DEFAULT_RESULT_SCHEMA),
        "calibration_dataset_sha256": _sha256_bytes(calibration_raw),
        "model": {
            "provider": "Amazon Bedrock",
            "region": os.environ.get(
                "AWS_REGION",
                os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
            ),
            "model_id": os.environ.get("BEDROCK_MODEL_ID", "unavailable"),
            "output_mode": os.environ.get("BEDROCK_OUTPUT_MODE", "unavailable"),
            "guardrail_id": os.environ.get("BEDROCK_GUARDRAIL_ID", "unavailable"),
            "guardrail_version": os.environ.get(
                "BEDROCK_GUARDRAIL_VERSION",
                "unavailable",
            ),
        },
        "pricing": {
            "input_usd_per_million": float(
                os.environ.get("BEDROCK_INPUT_USD_PER_MILLION", "1")
            ),
            "output_usd_per_million": float(
                os.environ.get("BEDROCK_OUTPUT_USD_PER_MILLION", "5")
            ),
        },
        "hard_bars": report["aggregate"]["hard_bars"],
        "all_cases_pass": (
            report["aggregate"]["case_pass"]["numerator"]
            == report["aggregate"]["case_pass"]["denominator"]
        ),
    }
    _write_json(output_dir / "manifest.json", manifest)
    (output_dir / "report.md").write_text(
        _markdown_report(report, manifest),
        encoding="utf-8",
    )
    return {"manifest": manifest, "report": report}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-command Mandate 14 two-surface runtime certification."
    )
    parser.add_argument("--dataset", required=True, help="Runtime JSONL path or -")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--product-reviews-target", default="localhost:3550")
    parser.add_argument("--cart-target", default=None)
    parser.add_argument(
        "--runtime-env",
        choices=["local", "staging", "production"],
        default="local",
    )
    parser.add_argument("--require-clean-git", action="store_true")
    args = parser.parse_args()

    dataset_raw = (
        sys.stdin.buffer.read()
        if args.dataset == "-"
        else Path(args.dataset).read_bytes()
    )
    cases = load_runtime_cases(dataset_raw)
    surfaces = {case["surface"] for case in cases}
    if surfaces != {"review_summary", "copilot"}:
        raise ValueError(
            "certification dataset must contain review_summary and copilot cases"
        )
    initial_git = _git_metadata()
    if args.require_clean_git and initial_git["dirty"]:
        raise ValueError("certification evidence requires a clean tracked worktree")
    required_model_values = (
        "BEDROCK_MODEL_ID",
        "BEDROCK_GUARDRAIL_ID",
        "BEDROCK_GUARDRAIL_VERSION",
    )
    missing = [name for name in required_model_values if not os.environ.get(name)]
    if missing:
        raise ValueError(f"missing model configuration: {', '.join(missing)}")

    result = package_run(
        cases=cases,
        dataset_raw=dataset_raw,
        output_dir=args.output_dir,
        review_adapter=ReviewSummaryAdapter.from_environment(),
        copilot_adapter=CopilotAdapter.from_targets(
            args.product_reviews_target,
            args.cart_target,
        ),
        runtime_env=args.runtime_env,
        command=[sys.executable, *sys.argv],
    )
    manifest = result["manifest"]
    if args.require_clean_git and manifest["git"]["sha"] != initial_git["sha"]:
        raise ValueError("Git SHA changed during certification")
    print(json.dumps(result["report"]["aggregate"], ensure_ascii=False, indent=2))
    if not manifest["hard_bars"]["pass"]:
        return 2
    if not manifest["all_cases_pass"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
