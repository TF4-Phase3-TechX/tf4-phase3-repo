#!/usr/bin/env python3
"""Validate and score externally supplied Mandate 14 JSONL observations."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from scorer import aggregate, score_case

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CASE_SCHEMA = SCRIPT_DIR / "schemas" / "case.schema.json"
DEFAULT_RESULT_SCHEMA = SCRIPT_DIR / "schemas" / "result.schema.json"


def _git_metadata() -> dict[str, Any]:
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        dirty = subprocess.run(
            ["git", "diff", "--quiet"],
            check=False,
            stderr=subprocess.DEVNULL,
        ).returncode != 0 or subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            check=False,
            stderr=subprocess.DEVNULL,
        ).returncode != 0
        return {"sha": sha, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"sha": "unknown", "dirty": True}


def _validator(path: Path) -> Draft202012Validator:
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def load_jsonl(path: Path, schema_path: Path = DEFAULT_CASE_SCHEMA) -> list[dict[str, Any]]:
    validator = _validator(schema_path)
    cases: list[dict[str, Any]] = []
    case_ids: set[str] = set()
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            case = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc.msg}") from exc
        errors = sorted(validator.iter_errors(case), key=lambda error: list(error.path))
        if errors:
            details = "; ".join(
                f"{'.'.join(str(item) for item in error.path) or '<root>'}: {error.message}"
                for error in errors
            )
            raise ValueError(f"{path}:{line_number}: schema validation failed: {details}")
        case_id = str(case["case_id"])
        if case_id in case_ids:
            raise ValueError(f"{path}:{line_number}: duplicate case_id {case_id!r}")
        case_ids.add(case_id)
        source_ids = [str(source["source_id"]) for source in case.get("sources", [])]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError(f"{path}:{line_number}: duplicate source_id in {case_id}")
        cases.append(case)
    if not cases:
        raise ValueError("dataset is empty")
    return cases


def build_report(
    cases: list[dict[str, Any]],
    raw: bytes,
    semantic_judge: Any | None = None,
) -> dict[str, Any]:
    results = [
        score_case(
            case,
            semantic_faithfulness=semantic_judge is not None,
        )
        for case in cases
    ]
    semantic = None
    if semantic_judge is not None:
        from semantic_faithfulness import apply_semantic_faithfulness

        semantic = apply_semantic_faithfulness(
            cases,
            results,
            semantic_judge,
        )
    aggregate_result = aggregate(results)
    if semantic is not None:
        aggregate_result["semantic_faithfulness_judge"] = semantic
    return {
        "schema_version": "mandate14-report-v2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "git": _git_metadata(),
        "per_case": results,
        "aggregate": aggregate_result,
    }


def require_no_semantic_truncation(report: dict[str, Any]) -> None:
    semantic = report["aggregate"].get("semantic_faithfulness_judge")
    if semantic and semantic["input_truncated_count"]:
        raise ValueError(
            "semantic faithfulness input truncated; evidence fails closed"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and score Mandate 14 observations from either AI surface."
    )
    parser.add_argument("--input", type=Path, required=True, help="JSONL observations")
    parser.add_argument("--output", type=Path, required=True, help="Report JSON path")
    parser.add_argument("--case-schema", type=Path, default=DEFAULT_CASE_SCHEMA)
    parser.add_argument("--result-schema", type=Path, default=DEFAULT_RESULT_SCHEMA)
    parser.add_argument(
        "--require-clean-git",
        action="store_true",
        help="Fail certification evidence if tracked files differ from HEAD.",
    )
    parser.add_argument(
        "--require-calibration",
        action="store_true",
        help="Require at least ten human-labeled cases.",
    )
    parser.add_argument(
        "--allow-hard-bar-failures",
        action="store_true",
        help="Return zero for an intentionally failing baseline fixture.",
    )
    parser.add_argument(
        "--require-all-pass",
        action="store_true",
        help="Fail certification when any supplied public/hidden case fails.",
    )
    parser.add_argument(
        "--semantic-faithfulness",
        action="store_true",
        help=(
            "Replace keyword claim support with the pinned calibrated HHEM "
            "semantic-faithfulness judge."
        ),
    )
    args = parser.parse_args()

    raw = args.input.read_bytes()
    cases = load_jsonl(args.input, args.case_schema)
    semantic_judge = None
    if args.semantic_faithfulness:
        from semantic_faithfulness import HHEMJudge

        semantic_judge = HHEMJudge()
    report = build_report(cases, raw, semantic_judge=semantic_judge)
    require_no_semantic_truncation(report)
    _validator(args.result_schema).validate(report)

    labeled_cases = report["aggregate"]["scorer_human"]["labeled_cases"]
    if args.require_calibration and labeled_cases < 10:
        raise ValueError(
            f"calibration requires at least 10 human labels, found {labeled_cases}"
        )
    if args.require_clean_git and report["git"]["dirty"]:
        raise ValueError("certification evidence requires a clean tracked worktree")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["aggregate"], ensure_ascii=False, indent=2))
    hard_bars_pass = report["aggregate"]["hard_bars"]["pass"]
    all_cases_pass = (
        report["aggregate"]["case_pass"]["numerator"]
        == report["aggregate"]["case_pass"]["denominator"]
    )
    if args.require_all_pass and not all_cases_pass:
        return 3
    return 0 if hard_bars_pass or args.allow_hard_bar_failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
