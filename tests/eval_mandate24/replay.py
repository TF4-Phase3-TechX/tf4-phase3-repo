"""Replay externally supplied Copilot requests and return one trace ID per row."""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import grpc

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRODUCT_REVIEWS = (
    _REPO_ROOT / "techx-corp-platform" / "src" / "product-reviews"
)
sys.path.insert(0, str(_PRODUCT_REVIEWS))

import demo_pb2  # noqa: E402
import demo_pb2_grpc  # noqa: E402

try:  # Support both `python -m` and direct script execution.
    from .common import read_jsonl, request_digest, validate_trace_id
except ImportError:
    from common import read_jsonl, request_digest, validate_trace_id  # type: ignore


def validate_case(case: dict[str, Any], row_number: int) -> dict[str, Any]:
    allowed = {"case_id", "query", "user_id", "session_id", "deadline_seconds"}
    unknown = sorted(set(case) - allowed)
    if unknown:
        raise ValueError(f"row {row_number}: unknown fields: {', '.join(unknown)}")
    case_id = str(case.get("case_id") or "").strip()
    query = str(case.get("query") or "")
    if not case_id or not query.strip():
        raise ValueError(f"row {row_number}: case_id and query are required")
    deadline = float(case.get("deadline_seconds", 30))
    if not 0 < deadline <= 60:
        raise ValueError(f"row {row_number}: deadline_seconds must be in (0, 60]")
    return {
        "case_id": case_id[:128],
        "query": query,
        "user_id": str(case.get("user_id") or f"m24-{uuid.uuid4().hex}"),
        "session_id": str(
            case.get("session_id") or f"m24-{uuid.uuid4().hex}"
        ),
        "deadline_seconds": deadline,
    }


def replay(
    cases_path: Path,
    target: str,
    output_path: Path,
) -> list[dict[str, Any]]:
    stub = demo_pb2_grpc.ProductReviewServiceStub(grpc.insecure_channel(target))
    results: list[dict[str, Any]] = []
    for row_number, raw_case in enumerate(read_jsonl(cases_path), start=1):
        case = validate_case(raw_case, row_number)
        started = time.perf_counter()
        response = stub.SearchProductsAIAssistant(
            demo_pb2.SearchProductsAIAssistantRequest(
                query=case["query"],
                session_id=case["session_id"],
                user_id=case["user_id"],
            ),
            timeout=case["deadline_seconds"],
        )
        trace_id = validate_trace_id(response.trace.trace_id)
        result = {
            "schema_version": "mandate24-replay-result-v1",
            "case_id": case["case_id"],
            "request_sha256": request_digest(case["query"]),
            "trace_id": trace_id,
            "outcome": str(response.outcome),
            "latency_ms": round((time.perf_counter() - started) * 1_000, 3),
            "input_tokens": int(response.trace.input_tokens),
            "output_tokens": int(response.trace.output_tokens),
            "estimated_cost_usd": float(response.trace.estimated_cost_usd),
            "refusal_reason": str(response.trace.refusal_reason),
        }
        results.append(result)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(
            json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n"
            for result in results
        ),
        encoding="utf-8",
    )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cases", type=Path)
    parser.add_argument(
        "--target",
        default="localhost:3551",
        help="ProductReviewService gRPC target",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    replay(args.cases, args.target, args.output)


if __name__ == "__main__":
    main()
