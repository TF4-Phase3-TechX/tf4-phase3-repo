#!/usr/bin/env python3

"""Replay Mandate 23 cases through the production ProductReview gRPC boundary."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from typing import Any, Iterable

import grpc
from google.protobuf.json_format import MessageToDict


REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCT_REVIEWS_SRC = REPO_ROOT / "techx-corp-platform" / "src" / "product-reviews"
sys.path.insert(0, str(PRODUCT_REVIEWS_SRC))

import demo_pb2  # noqa: E402
import demo_pb2_grpc  # noqa: E402


SCHEMA_VERSION = "mandate23-replay-v1"


def _json_line(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _git_revision() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _git_tracked_dirty() -> bool | None:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        return None


def _read_cases(path: str) -> list[dict[str, Any]]:
    stream = sys.stdin if path == "-" else Path(path).open(encoding="utf-8")
    try:
        cases = []
        for line_number, raw in enumerate(stream, start=1):
            if not raw.strip():
                continue
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError(f"line {line_number}: case must be an object")
            if not value.get("user_id") or not value.get("session_id"):
                raise ValueError(
                    f"line {line_number}: user_id and session_id are required"
                )
            if "expect" in value and not isinstance(value["expect"], dict):
                raise ValueError(f"line {line_number}: expect must be an object")
            cases.append(value)
        return cases
    finally:
        if stream is not sys.stdin:
            stream.close()


def materialize_cases(
    cases: Iterable[dict[str, Any]],
    *,
    repetitions: int = 1,
    identity_suffix: str = "",
) -> list[dict[str, Any]]:
    if repetitions < 1:
        raise ValueError("repetitions must be at least 1")
    materialized = []
    for repetition in range(1, repetitions + 1):
        suffix = identity_suffix
        if repetitions > 1:
            suffix = f"{suffix}-r{repetition}"
        for original in cases:
            case = dict(original)
            case["user_id"] = f"{original['user_id']}{suffix}"
            case["session_id"] = f"{original['session_id']}{suffix}"
            if repetitions > 1:
                case["case_id"] = f"{original.get('case_id', '')}-r{repetition}"
            materialized.append(case)
    return materialized


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def aggregate(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    materialized = list(rows)
    for row in materialized:
        groups[row["surface"]].append(row)
    groups["total"] = materialized

    result: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "groups": {}}
    for name, items in groups.items():
        successful = [item for item in items if not item.get("error")]
        validated = [
            item
            for item in items
            if int((item.get("assertions") or {}).get("checked", 0)) > 0
        ]
        assertion_failures = sum(
            (item.get("assertions") or {}).get("status") == "failed"
            for item in items
        )
        hits = sum(item.get("cache") == "hit" for item in successful)
        latencies = [float(item.get("latency_ms", 0)) for item in successful]
        misses = [
            float(item.get("latency_ms", 0))
            for item in successful
            if item.get("cache") == "miss"
        ]
        warm = [
            float(item.get("latency_ms", 0))
            for item in successful
            if item.get("cache") == "hit"
        ]
        result["groups"][name] = {
            "cases": len(items),
            "successful_cases": len(successful),
            "failed_cases": len(items) - len(successful),
            "validated_cases": len(validated),
            "assertion_failures": assertion_failures,
            "cache_hits": hits,
            "cache_misses": len(successful) - hits,
            "hit_rate": hits / len(successful) if successful else 0.0,
            "latency_ms": {
                "p50": statistics.median(latencies) if latencies else 0.0,
                "p95": _percentile(latencies, 0.95),
                "miss_mean": statistics.fmean(misses) if misses else 0.0,
                "hit_mean": statistics.fmean(warm) if warm else 0.0,
            },
            "model_calls": sum(int(item.get("model_calls", 0)) for item in successful),
            "input_tokens": sum(int(item.get("input_tokens", 0)) for item in successful),
            "output_tokens": sum(int(item.get("output_tokens", 0)) for item in successful),
            "estimated_cost_usd": sum(
                float(item.get("estimated_cost_usd", 0)) for item in successful
            ),
        }
    return result


def _request_payload(case: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    raw_request = case.get("request")
    request = raw_request if isinstance(raw_request, dict) else {"question": raw_request}
    surface = str(case.get("surface") or request.get("surface") or "product_qa")
    return surface, request


def validate_expectations(
    case: dict[str, Any],
    observation: dict[str, Any],
) -> tuple[int, list[str]]:
    """Validate semantic outcomes, not only transport success."""
    expected = case.get("expect")
    if not expected:
        return 0, []
    if not isinstance(expected, dict):
        return 0, ["expect must be an object"]

    errors: list[str] = []
    checked = 0
    payload = observation.get("response")
    payload = payload if isinstance(payload, dict) else {}

    for field in (
        "cache",
        "cache_eligible",
        "cache_reason",
        "model_calls",
        "memory_status",
    ):
        if field not in expected:
            continue
        checked += 1
        actual = observation.get(field)
        if actual != expected[field]:
            errors.append(
                f"{field}: expected {expected[field]!r}, observed {actual!r}"
            )

    if "outcome" in expected:
        checked += 1
        actual = payload.get("outcome", "")
        if actual != expected["outcome"]:
            errors.append(
                f"outcome: expected {expected['outcome']!r}, observed {actual!r}"
            )

    response_text = str(payload.get("response") or "")
    for field, should_contain in (
        ("response_contains", True),
        ("response_not_contains", False),
    ):
        if field not in expected:
            continue
        values = expected[field]
        values = [values] if isinstance(values, str) else values
        if not isinstance(values, list) or not all(
            isinstance(value, str) and value for value in values
        ):
            errors.append(f"{field}: expected a string or non-empty string list")
            continue
        for value in values:
            checked += 1
            present = value.casefold() in response_text.casefold()
            if present != should_contain:
                qualifier = "contain" if should_contain else "exclude"
                errors.append(f"{field}: response must {qualifier} {value!r}")

    results = payload.get("results")
    result_ids = (
        [str(item.get("id") or "") for item in results if isinstance(item, dict)]
        if isinstance(results, list)
        else []
    )
    if "result_product_ids" in expected:
        checked += 1
        wanted = expected["result_product_ids"]
        if not isinstance(wanted, list) or result_ids != wanted:
            errors.append(
                f"result_product_ids: expected {wanted!r}, observed {result_ids!r}"
            )
    if "result_product_ids_contains" in expected:
        wanted = expected["result_product_ids_contains"]
        if not isinstance(wanted, list):
            errors.append("result_product_ids_contains: expected a list")
        else:
            for product_id in wanted:
                checked += 1
                if product_id not in result_ids:
                    errors.append(
                        f"result_product_ids_contains: missing {product_id!r}"
                    )

    return checked, errors


def run_case(
    stub: Any,
    case: dict[str, Any],
    *,
    timeout_seconds: float,
    default_product_id: str,
) -> dict[str, Any]:
    surface, request = _request_payload(case)
    started = time.monotonic()
    try:
        if surface == "product_qa":
            product_id = str(request.get("product_id") or default_product_id)
            question = str(request.get("question") or request.get("query") or "")
            if not product_id or not question:
                raise ValueError("product_qa requires product_id and question")
            response = stub.AskProductAIAssistant(
                demo_pb2.AskProductAIAssistantRequest(
                    product_id=product_id,
                    question=question,
                    user_id=case["user_id"],
                    session_id=case["session_id"],
                ),
                timeout=timeout_seconds,
            )
        elif surface == "copilot":
            query = str(request.get("query") or request.get("question") or "")
            if not query:
                raise ValueError("copilot requires query")
            response = stub.SearchProductsAIAssistant(
                demo_pb2.SearchProductsAIAssistantRequest(
                    query=query,
                    user_id=case["user_id"],
                    session_id=case["session_id"],
                ),
                timeout=timeout_seconds,
            )
        else:
            raise ValueError(f"unsupported surface: {surface}")
        client_latency_ms = (time.monotonic() - started) * 1_000
        payload = MessageToDict(response, preserving_proto_field_name=True)
        cache_status = str(getattr(response, "cache_status", "") or "miss")
        observation = {
            "schema_version": SCHEMA_VERSION,
            "case_id": str(case.get("case_id") or ""),
            "surface": surface,
            "user_id": case["user_id"],
            "session_id": case["session_id"],
            "cache": cache_status,
            "cache_status": cache_status,
            "cache_eligible": bool(getattr(response, "cache_eligible", False)),
            "cache_reason": str(getattr(response, "cache_reason", "")),
            "model_calls": int(getattr(response, "model_calls", 0)),
            "input_tokens": int(getattr(response, "input_tokens", 0)),
            "output_tokens": int(getattr(response, "output_tokens", 0)),
            "estimated_cost_usd": float(
                getattr(response, "estimated_cost_usd", 0)
            ),
            "latency_ms": float(
                getattr(response, "latency_ms", 0) or client_latency_ms
            ),
            "client_latency_ms": client_latency_ms,
            "memory_status": str(getattr(response, "memory_status", "")),
            "response": payload,
        }
        checked, validation_errors = validate_expectations(case, observation)
        observation["assertions"] = {
            "status": (
                "failed"
                if validation_errors
                else "passed"
                if checked
                else "not_configured"
            ),
            "checked": checked,
        }
        if validation_errors:
            observation["error"] = "AssertionError"
            observation["error_message"] = "; ".join(validation_errors)[:2_000]
        return observation
    except Exception as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "case_id": str(case.get("case_id") or ""),
            "surface": surface,
            "user_id": case["user_id"],
            "session_id": case["session_id"],
            "cache": "miss",
            "cache_status": "miss",
            "latency_ms": (time.monotonic() - started) * 1_000,
            "error": type(exc).__name__,
            "error_message": str(exc)[:500],
        }


def _report(summary: dict[str, Any]) -> str:
    lines = [
        "# Mandate 23 replay report",
        "",
        "| Surface | Cases | Validated | Failures | Assertion failures | Hit rate | Miss mean ms | Hit mean ms | Model calls | Tokens | Cost USD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for surface, row in summary["groups"].items():
        lines.append(
            f"| {surface} | {row['cases']} | {row['validated_cases']} | "
            f"{row['failed_cases']} | {row['assertion_failures']} | "
            f"{row['hit_rate']:.2%} | "
            f"{row['latency_ms']['miss_mean']:.2f} | {row['latency_ms']['hit_mean']:.2f} | "
            f"{row['model_calls']} | {row['input_tokens'] + row['output_tokens']} | "
            f"{row['estimated_cost_usd']:.8f} |"
        )
    lines.extend(
        [
            "",
            "All numbers above are computed from this runtime replay. Transport or semantic assertion failures remain in `per_case.jsonl`, fail the command, and are not counted as successful cache observations.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="-", help="JSONL file or - for stdin")
    parser.add_argument("--target", default="localhost:3551")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--default-product-id", default="")
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument(
        "--source-revision",
        default=os.getenv("MANDATE23_SOURCE_REVISION") or _git_revision(),
    )
    parser.add_argument(
        "--runtime-image",
        default=os.getenv("MANDATE23_RUNTIME_IMAGE", ""),
    )
    parser.add_argument(
        "--runtime-image-digest",
        default=os.getenv("MANDATE23_RUNTIME_IMAGE_DIGEST", ""),
    )
    parser.add_argument(
        "--runtime-code-sha256",
        default=os.getenv("MANDATE23_RUNTIME_CODE_SHA256", ""),
    )
    parser.add_argument(
        "--model-id",
        default=os.getenv("BEDROCK_MODEL_ID", ""),
    )
    parser.add_argument(
        "--guardrail-id",
        default=os.getenv("BEDROCK_GUARDRAIL_ID", ""),
    )
    parser.add_argument(
        "--guardrail-version",
        default=os.getenv("BEDROCK_GUARDRAIL_VERSION", ""),
    )
    parser.add_argument(
        "--identity-suffix",
        default="",
        help="Suffix added to every user_id/session_id to guarantee a fresh replay",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    source_cases = _read_cases(args.input)
    input_bytes = "\n".join(_json_line(case) for case in source_cases).encode("utf-8")
    cases = materialize_cases(
        source_cases,
        repetitions=args.repetitions,
        identity_suffix=args.identity_suffix,
    )

    with grpc.insecure_channel(args.target) as channel:
        stub = demo_pb2_grpc.ProductReviewServiceStub(channel)
        rows = [
            run_case(
                stub,
                case,
                timeout_seconds=args.timeout_seconds,
                default_product_id=args.default_product_id,
            )
            for case in cases
        ]

    per_case_path = output_dir / "per_case.jsonl"
    per_case_path.write_text(
        "".join(f"{_json_line(row)}\n" for row in rows),
        encoding="utf-8",
    )
    summary = aggregate(rows)
    (output_dir / "aggregate.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(_report(summary), encoding="utf-8")
    (output_dir / "command.txt").write_text(
        " ".join([sys.executable, *sys.argv]) + "\n",
        encoding="utf-8",
    )
    config = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "target": args.target,
        "timeout_seconds": args.timeout_seconds,
        "default_product_id": args.default_product_id,
        "repetitions": args.repetitions,
        "identity_suffix": args.identity_suffix,
        "source_case_count": len(source_cases),
        "case_count": len(cases),
        "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
        "source": {
            "revision": args.source_revision,
            "tracked_dirty": _git_tracked_dirty(),
        },
        "runtime": {
            "image": args.runtime_image,
            "image_digest": args.runtime_image_digest,
            "code_sha256": args.runtime_code_sha256,
            "model_id": args.model_id,
            "guardrail_id": args.guardrail_id,
            "guardrail_version": args.guardrail_version,
        },
        "price_snapshot": {
            "input_usd_per_million": os.getenv("BEDROCK_INPUT_USD_PER_MILLION"),
            "output_usd_per_million": os.getenv("BEDROCK_OUTPUT_USD_PER_MILLION"),
        },
    }
    (output_dir / "config.json").write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {}
    for path in sorted(output_dir.iterdir()):
        if path.name == "manifest.sha256":
            continue
        manifest[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (output_dir / "manifest.sha256").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in manifest.items()),
        encoding="utf-8",
    )
    return 1 if any(row.get("error") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
