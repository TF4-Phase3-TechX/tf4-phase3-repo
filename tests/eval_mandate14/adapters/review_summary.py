"""Run externally supplied review cases through the production post-retrieval path."""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import boto3

REPO_ROOT = Path(__file__).resolve().parents[3]
PRODUCT_REVIEWS_DIR = REPO_ROOT / "techx-corp-platform" / "src" / "product-reviews"
if str(PRODUCT_REVIEWS_DIR) not in sys.path:
    sys.path.insert(0, str(PRODUCT_REVIEWS_DIR))

from ai_assistant import GroundedAssistant  # noqa: E402
from bedrock_adapter import BedrockAdapter  # noqa: E402

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def _estimated_cost(input_tokens: int, output_tokens: int) -> float:
    input_rate = float(os.environ.get("BEDROCK_INPUT_USD_PER_MILLION", "1"))
    output_rate = float(os.environ.get("BEDROCK_OUTPUT_USD_PER_MILLION", "5"))
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000


def _claims(response: str, citations: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    """Bind each user-visible sentence to the validator-approved review sources."""
    if not citations:
        return []
    source_ids = [
        "product-description",
        *sorted({f"review:{int(item['review_id'])}" for item in citations}),
    ]
    return [
        {
            "text": sentence.strip(),
            "claim_type": "mixed",
            "source_ids": source_ids,
        }
        for sentence in SENTENCE_RE.split(response)
        if sentence.strip()
    ]


class ReviewSummaryAdapter:
    """Inject supplied sources only at the production retrieval boundary."""

    def __init__(self, provider: Any):
        self.provider = provider

    @classmethod
    def from_environment(cls) -> "ReviewSummaryAdapter":
        region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
        client = boto3.client("bedrock-runtime", region_name=region)
        provider = BedrockAdapter(
            model_id=os.environ["BEDROCK_MODEL_ID"],
            guardrail_id=os.environ["BEDROCK_GUARDRAIL_ID"],
            guardrail_version=os.environ["BEDROCK_GUARDRAIL_VERSION"],
            output_mode=os.environ.get("BEDROCK_OUTPUT_MODE", "tool"),
            deadline_seconds=float(
                os.environ.get("BEDROCK_DEADLINE_SECONDS", "4.5")
            ),
            client=client,
            system_canary=os.environ.get("BEDROCK_SYSTEM_CANARY", ""),
        )
        return cls(provider)

    def run(self, case: dict[str, Any]) -> dict[str, Any]:
        payload = case["input"]
        product = dict(payload["product"])
        reviews = list(payload.get("reviews", []))
        rows = [
            (
                int(review["review_id"]),
                "synthetic-reviewer",
                str(review["text"]),
                float(review.get("score", 0)),
            )
            for review in reviews
        ]
        assistant = GroundedAssistant(
            self.provider,
            fetch_product=lambda _product_id: product,
            fetch_reviews=lambda _product_id: rows,
            system_canary=os.environ.get("BEDROCK_SYSTEM_CANARY", ""),
        )

        started = time.perf_counter()
        outcome = assistant.answer(
            str(product["id"]),
            str(payload["question"]),
            session_id=f"m14-{case['case_id']}",
            user_id=f"m14-{case['case_id']}",
        )
        wall_latency_ms = (time.perf_counter() - started) * 1_000
        citations = tuple(outcome.citations)
        return {
            "outcome": (
                "insufficient_evidence"
                if outcome.outcome == "insufficient"
                else outcome.outcome
            ),
            "response_text": outcome.response,
            "output_fields": {
                "citations": [
                    {
                        "source_id": f"review:{int(item['review_id'])}",
                        "evidence_quote": item["evidence_quote"],
                    }
                    for item in citations
                ],
                "quarantined_reviews": outcome.quarantined_reviews,
                "error_class": outcome.error_class,
            },
            "claims": _claims(outcome.response, citations),
            "blocked": outcome.outcome == "blocked",
            "abstained": outcome.outcome == "insufficient",
            "tool_calls": [],
            "write_attempted": False,
            "write_applied": False,
            "latency_ms": max(wall_latency_ms, float(outcome.latency_ms)),
            "input_tokens": int(outcome.input_tokens),
            "output_tokens": int(outcome.output_tokens),
            "model_requests": int(outcome.provider_attempted),
            "estimated_cost_usd": _estimated_cost(
                int(outcome.input_tokens),
                int(outcome.output_tokens),
            ),
        }
