"""Replay external Product Reviews requests and capture bounded resilience state."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import grpc

PRODUCT_REVIEWS_SRC = (
    Path(__file__).resolve().parents[2]
    / "techx-corp-platform"
    / "src"
    / "product-reviews"
)
if str(PRODUCT_REVIEWS_SRC) not in sys.path:
    sys.path.insert(0, str(PRODUCT_REVIEWS_SRC))

import demo_pb2
import demo_pb2_grpc
from safety import INSUFFICIENT_RESPONSE, UNAVAILABLE_RESPONSE

STATUS_METHOD = "/tf4.mandate25.ResilienceControl/GetStatus"


def read_cases(path: Path) -> list[dict[str, str]]:
    """Read JSONL cases, supporting both 'ask' (Q&A) and 'search' (intent) types.

    'ask' cases require: case_id, product_id, question, user_id, session_id.
    'search' cases require: case_id, query, user_id, session_id.
    A missing 'type' field defaults to 'ask' for backward compatibility.
    """
    cases = []
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw_line.strip():
            continue
        value = json.loads(raw_line)
        if not isinstance(value, dict) or "case_id" not in value:
            raise ValueError(f"line {line_number}: required field 'case_id' missing")
        case_type = str(value.get("type", "ask")).lower()
        if case_type == "search":
            required = {"case_id", "query", "user_id", "session_id"}
            if not required.issubset(value):
                raise ValueError(
                    f"line {line_number}: search case required fields: {sorted(required)}"
                )
            cases.append(
                {
                    "case_id": str(value["case_id"]),
                    "type": "search",
                    "query": str(value["query"]),
                    "user_id": str(value["user_id"]),
                    "session_id": str(value["session_id"]),
                }
            )
        else:
            required = {"case_id", "product_id", "question", "user_id", "session_id"}
            if not required.issubset(value):
                raise ValueError(
                    f"line {line_number}: ask case required fields: {sorted(required)}"
                )
            cases.append(
                {
                    "case_id": str(value["case_id"]),
                    "type": "ask",
                    "product_id": str(value["product_id"]),
                    "question": str(value["question"]),
                    "user_id": str(value["user_id"]),
                    "session_id": str(value["session_id"]),
                }
            )
    if not cases:
        raise ValueError("at least one replay case is required")
    return cases


def classify_response(response_text: str) -> str:
    if response_text == UNAVAILABLE_RESPONSE:
        return "unavailable"
    if response_text == INSUFFICIENT_RESPONSE:
        return "insufficient"
    return "answered"


def request_fingerprint(case: dict[str, str]) -> str:
    canonical = json.dumps(case, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def replay(
    cases: Iterable[dict[str, str]],
    *,
    stub: Any,
    status_call: Any,
    repeat: int,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    """Replay cases against the service and capture bounded resilience state.

    Routes to AskProductAIAssistant for type='ask' cases and
    SearchProductsAIAssistant for type='search' cases so that the
    Search Intent fault-injection path is exercised in addition to Q&A.
    """
    rows: list[dict[str, Any]] = []
    for case in cases:
        for iteration in range(1, repeat + 1):
            started = time.monotonic()
            case_type = case.get("type", "ask")
            try:
                if case_type == "search":
                    response = stub.SearchProductsAIAssistant(
                        demo_pb2.SearchProductsAIAssistantRequest(
                            query=case["query"],
                            user_id=case["user_id"],
                            session_id=case["session_id"],
                        ),
                        timeout=timeout_seconds,
                    )
                    response_text = str(response.response)[:1_000]
                    has_action = response.HasField("action_proposal")
                    trace_id = str(response.trace.trace_id)
                else:
                    response = stub.AskProductAIAssistant(
                        demo_pb2.AskProductAIAssistantRequest(
                            product_id=case["product_id"],
                            question=case["question"],
                            user_id=case["user_id"],
                            session_id=case["session_id"],
                        ),
                        timeout=timeout_seconds,
                    )
                    response_text = str(response.response)[:1_000]
                    has_action = response.HasField("action_proposal")
                    trace_id = ""
                transport = "ok"
            except grpc.RpcError as exc:
                response_text = ""
                transport = exc.code().name
                has_action = False
                trace_id = ""
            status = status_call({}, timeout=2)
            rows.append(
                {
                    "case_id": case["case_id"],
                    "case_type": case_type,
                    "iteration": iteration,
                    "request_sha256": request_fingerprint(case),
                    "transport": transport,
                    "trace_id": trace_id,
                    "outcome": (
                        classify_response(response_text)
                        if transport == "ok"
                        else "transport_error"
                    ),
                    "response": response_text,
                    "has_action_proposal": has_action,
                    "elapsed_ms": round(
                        (time.monotonic() - started) * 1_000,
                        3,
                    ),
                    "fault": status.get("fault", {}),
                    "resilience": status.get("resilience", {}),
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cases", type=Path)
    parser.add_argument("--target", default="127.0.0.1:3551")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=6)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.repeat <= 20:
        raise ValueError("repeat must be between 1 and 20")
    if not 0 < args.timeout_seconds <= 10:
        raise ValueError("timeout-seconds must be between 0 and 10")

    channel = grpc.insecure_channel(args.target)
    try:
        stub = demo_pb2_grpc.ProductReviewServiceStub(channel)
        status_call = channel.unary_unary(
            STATUS_METHOD,
            request_serializer=lambda value: json.dumps(value).encode("utf-8"),
            response_deserializer=lambda value: json.loads(
                value.decode("utf-8")
            ),
        )
        rows = replay(
            read_cases(args.cases),
            stub=stub,
            status_call=status_call,
            repeat=args.repeat,
            timeout_seconds=args.timeout_seconds,
        )
    finally:
        channel.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(
            json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "rows": len(rows),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
