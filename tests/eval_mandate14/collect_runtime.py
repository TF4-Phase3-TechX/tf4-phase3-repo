#!/usr/bin/env python3
"""Collect common Mandate 14 observations from externally supplied cases."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from adapters.copilot import CopilotAdapter
from adapters.review_summary import ReviewSummaryAdapter

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SCHEMA = SCRIPT_DIR / "schemas" / "runtime-case.schema.json"


def _validator(path: Path) -> Draft202012Validator:
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def load_runtime_cases(raw: bytes, schema_path: Path = DEFAULT_SCHEMA) -> list[dict[str, Any]]:
    validator = _validator(schema_path)
    cases: list[dict[str, Any]] = []
    case_ids: set[str] = set()
    for line_number, raw_line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            case = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {line_number}: invalid JSON: {exc.msg}") from exc
        errors = sorted(validator.iter_errors(case), key=lambda error: list(error.path))
        if errors:
            details = "; ".join(
                f"{'.'.join(str(item) for item in error.path) or '<root>'}: {error.message}"
                for error in errors
            )
            raise ValueError(f"line {line_number}: schema validation failed: {details}")
        case_id = str(case["case_id"])
        if case_id in case_ids:
            raise ValueError(f"line {line_number}: duplicate case_id {case_id!r}")
        case_ids.add(case_id)
        cases.append(case)
    if not cases:
        raise ValueError("dataset is empty")
    return cases


def _review_sources(case: dict[str, Any]) -> list[dict[str, Any]]:
    product = case["input"]["product"]
    product_text = " ".join(
        value
        for value in (
            str(product.get("name", "")),
            str(product.get("description", "")),
            ", ".join(str(item) for item in product.get("categories", [])),
        )
        if value
    )
    sources = [{
        "source_id": "product-description",
        "source_type": "product_description",
        "text": product_text,
    }]
    for review in case["input"].get("reviews", []):
        source = {
            "source_id": f"review:{int(review['review_id'])}",
            "source_type": "review",
            "text": str(review["text"]),
        }
        if review.get("synthetic_pii"):
            source["synthetic_pii"] = list(review["synthetic_pii"])
        sources.append(source)
    return sources


def collect(
    cases: list[dict[str, Any]],
    review_adapter: Any,
    copilot_adapter: Any,
) -> list[dict[str, Any]]:
    observations = []
    for case in cases:
        if case["surface"] == "review_summary":
            observed = review_adapter.run(case)
            sources = _review_sources(case)
        elif case["surface"] == "copilot":
            observed = copilot_adapter.run(case)
            sources = list(observed.pop("_sources", []))
        else:  # Schema validation makes this unreachable.
            raise ValueError(f"unsupported surface {case['surface']!r}")
        observation = {
            "schema_version": "mandate14-case-v2",
            "case_id": case["case_id"],
            "surface": case["surface"],
            "variant": case.get("variant", "candidate"),
            "category": case["category"],
            "sources": sources,
            "expected": case["expected"],
            "observed": observed,
            "metadata": {
                **case.get("metadata", {}),
                "runtime_case_schema": case["schema_version"],
            },
        }
        observations.append(observation)
    return observations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Invoke both Mandate 14 surfaces and emit scorer-ready JSONL."
    )
    parser.add_argument("--input", required=True, help="Runtime JSONL path or - for stdin")
    parser.add_argument("--output", type=Path, required=True, help="Observation JSONL")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument(
        "--product-reviews-target",
        default="localhost:3550",
        help="ProductReviewService gRPC target",
    )
    parser.add_argument(
        "--cart-target",
        default=None,
        help="CartService gRPC target; required for write-state cases",
    )
    args = parser.parse_args()

    raw = sys.stdin.buffer.read() if args.input == "-" else Path(args.input).read_bytes()
    cases = load_runtime_cases(raw, args.schema)
    review_adapter = ReviewSummaryAdapter.from_environment()
    copilot_adapter = CopilotAdapter.from_targets(
        args.product_reviews_target,
        args.cart_target,
    )
    observations = collect(cases, review_adapter, copilot_adapter)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(
            json.dumps(observation, ensure_ascii=False, separators=(",", ":")) + "\n"
            for observation in observations
        ),
        encoding="utf-8",
    )
    print(f"Mandate 14 observations: {args.output} ({len(observations)} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
