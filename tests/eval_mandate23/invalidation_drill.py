#!/usr/bin/env python3

"""Run miss→hit→source-change→miss and restore the exact review row in finally."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

import grpc
import psycopg2


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(
    0,
    str(REPO_ROOT / "techx-corp-platform" / "src" / "product-reviews"),
)
import demo_pb2  # noqa: E402
import demo_pb2_grpc  # noqa: E402


def _ask(stub, product_id, question, user_id, session_id, timeout):
    started = time.monotonic()
    response = stub.AskProductAIAssistant(
        demo_pb2.AskProductAIAssistantRequest(
            product_id=product_id,
            question=question,
            user_id=user_id,
            session_id=session_id,
        ),
        timeout=timeout,
    )
    return {
        "cache": response.cache_status,
        "cache_eligible": response.cache_eligible,
        "cache_reason": response.cache_reason,
        "model_calls": response.model_calls,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "estimated_cost_usd": response.estimated_cost_usd,
        "latency_ms": response.latency_ms
        or (time.monotonic() - started) * 1_000,
        "response": response.response,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-dsn", required=True)
    parser.add_argument("--target", default="localhost:3551")
    parser.add_argument("--product-id", default="OLJCESPC7Z")
    parser.add_argument(
        "--question",
        default="What exact feedback and score are in review {review_id}?",
    )
    parser.add_argument("--user-id", default="mandate23-invalidation-user")
    parser.add_argument("--session-id", default="mandate23-invalidation-session")
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    connection = psycopg2.connect(args.db_dsn)
    original = None
    selected_id = None
    result = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "product_id": args.product_id,
        "events": [],
    }
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
SELECT id, description, score
FROM reviews.productreviews
WHERE product_id = %s
ORDER BY id
LIMIT 1
""",
                (args.product_id,),
            )
            original = cursor.fetchone()
            if original is None:
                raise RuntimeError("no review row found for product")
            selected_id = original[0]
            result["source_record"] = {
                "table": "reviews.productreviews",
                "id": selected_id,
                "original_description": original[1],
                "original_score": str(original[2]),
            }
        question = args.question.format(review_id=selected_id)
        result["question"] = question

        with grpc.insecure_channel(args.target) as channel:
            stub = demo_pb2_grpc.ProductReviewServiceStub(channel)
            result["events"].append(
                {
                    "step": "cold",
                    **_ask(
                        stub,
                        args.product_id,
                        question,
                        args.user_id,
                        args.session_id,
                        args.timeout_seconds,
                    ),
                }
            )
            result["events"].append(
                {
                    "step": "warm",
                    **_ask(
                        stub,
                        args.product_id,
                        question,
                        args.user_id,
                        args.session_id,
                        args.timeout_seconds,
                    ),
                }
            )
            marker = f"MANDATE23_INVALIDATION_{int(time.time())}"
            updated_description = f"{original[1]} {marker}"
            updated_score = 1 if float(original[2]) != 1 else 2
            with connection.cursor() as cursor:
                cursor.execute(
                    """
UPDATE reviews.productreviews
SET description = %s, score = %s
WHERE id = %s
""",
                    (updated_description, updated_score, selected_id),
                )
            connection.commit()
            result["mutation"] = {
                "id": selected_id,
                "marker": marker,
                "updated_score": str(updated_score),
            }
            result["events"].append(
                {
                    "step": "source_changed",
                    **_ask(
                        stub,
                        args.product_id,
                        question,
                        args.user_id,
                        args.session_id,
                        args.timeout_seconds,
                    ),
                }
            )
    finally:
        if original is not None and selected_id is not None:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
UPDATE reviews.productreviews
SET description = %s, score = %s
WHERE id = %s
""",
                    (original[1], original[2], selected_id),
                )
            connection.commit()
            with connection.cursor() as cursor:
                cursor.execute(
                    """
SELECT description, score
FROM reviews.productreviews
WHERE id = %s
""",
                    (selected_id,),
                )
                restored = cursor.fetchone()
            result["restore_verified"] = bool(
                restored
                and restored[0] == original[1]
                and restored[1] == original[2]
            )
        connection.close()
        Path(args.output).write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

    events = result["events"]
    passed = (
        len(events) == 3
        and events[0]["cache"] == "miss"
        and events[1]["cache"] == "hit"
        and events[2]["cache"] == "miss"
        and events[2]["cache_reason"] == "source_changed"
        and result.get("mutation", {}).get("marker", "")
        in events[2].get("response", "")
        and result.get("restore_verified") is True
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
