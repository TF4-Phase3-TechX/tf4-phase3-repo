"""Run the bounded Mandate 25 production drill from inside product-reviews.

The control token is read only from the workload environment. Output contains
no token, prompt body, or user identity; request identifiers are synthetic.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from typing import Any

import demo_pb2
import demo_pb2_grpc
import grpc

CONTROL = "/tf4.mandate25.ResilienceControl"
UNAVAILABLE = (
    "The AI assistant is temporarily unavailable. Please use the original "
    "product details and reviews and try again later."
)
INSUFFICIENT = (
    "I don't have enough information in the available product details and "
    "reviews to answer that question."
)


def _json_call(channel: grpc.Channel, method: str):
    return channel.unary_unary(
        f"{CONTROL}/{method}",
        request_serializer=lambda value: json.dumps(
            value, sort_keys=True, separators=(",", ":")
        ).encode("utf-8"),
        response_deserializer=lambda value: json.loads(value.decode("utf-8")),
    )


def _classify(text: str) -> str:
    if text == UNAVAILABLE:
        return "unavailable"
    if text == INSUFFICIENT:
        return "insufficient"
    return "answered"


class Drill:
    def __init__(self, run_id: str):
        token = os.environ.get("MANDATE25_FAULT_TOKEN", "")
        if not token:
            raise RuntimeError("MANDATE25_FAULT_TOKEN is unavailable")
        self.run_id = run_id
        self.channel = grpc.insecure_channel("127.0.0.1:3551")
        self.stub = demo_pb2_grpc.ProductReviewServiceStub(self.channel)
        self.status_call = _json_call(self.channel, "GetStatus")
        self.set_call = _json_call(self.channel, "SetFault")
        self.metadata = (("x-mandate25-token", token),)

    def close(self) -> None:
        self.channel.close()

    def status(self) -> dict[str, Any]:
        return self.status_call({}, timeout=3)

    def set_fault(self, mode: str, ttl_seconds: int = 30) -> dict[str, Any]:
        return self.set_call(
            {"mode": mode, "ttl_seconds": ttl_seconds},
            timeout=3,
            metadata=self.metadata,
        )

    def restore(self) -> dict[str, Any]:
        self.set_fault("off", 0)
        return self.status()

    def ask(self, case_id: str) -> dict[str, Any]:
        started = time.monotonic()
        response = self.stub.AskProductAIAssistant(
            demo_pb2.AskProductAIAssistantRequest(
                product_id="OLJCESPC7Z",
                question=f"Summarize portability; controlled ref {self.run_id}-{case_id}",
                user_id=f"m25-prod-{self.run_id}",
                session_id=f"m25-prod-{self.run_id}-{case_id}",
            ),
            timeout=8,
        )
        return {
            "case_id": case_id,
            "transport": "ok",
            "outcome": _classify(str(response.response)),
            "has_action_proposal": response.HasField("action_proposal"),
            "model_calls": int(response.model_calls),
            "elapsed_ms": round((time.monotonic() - started) * 1_000, 3),
            "status": self.status(),
        }

    def search(self, case_id: str) -> dict[str, Any]:
        started = time.monotonic()
        response = self.stub.SearchProductsAIAssistant(
            demo_pb2.SearchProductsAIAssistantRequest(
                query=f"Find a telescope; controlled ref {self.run_id}-{case_id}",
                user_id=f"m25-prod-{self.run_id}",
                session_id=f"m25-prod-{self.run_id}-{case_id}",
            ),
            timeout=8,
        )
        return {
            "case_id": case_id,
            "transport": "ok",
            "outcome": str(response.outcome) or _classify(str(response.response)),
            "has_action_proposal": response.HasField("action_proposal"),
            "model_calls": int(response.model_calls),
            "trace_id": str(response.trace.trace_id),
            "elapsed_ms": round((time.monotonic() - started) * 1_000, 3),
            "status": self.status(),
        }


def run_faults(drill: Drill) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    expected_errors = {
        "timeout": "timeout",
        "throttling": "throttlingexception",
        "provider_5xx": "internalserverexception",
    }
    try:
        for mode, expected_error in expected_errors.items():
            drill.set_fault(mode)
            observation = drill.ask(mode)
            assert observation["outcome"] == "unavailable", observation
            assert observation["has_action_proposal"] is False, observation
            assert observation["status"]["resilience"]["last_provider_error"] == expected_error
            observations.append(observation)
            restored = drill.restore()
            assert restored["fault"]["mode"] == "off", restored

        drill.set_fault("malformed_output")
        malformed = drill.ask("malformed_output")
        assert malformed["outcome"] == "insufficient", malformed
        assert malformed["has_action_proposal"] is False, malformed
        observations.append(malformed)
        restored = drill.restore()
        assert restored["fault"]["mode"] == "off", restored

        drill.set_fault("throttling")
        breaker = [drill.search(f"breaker-{index}") for index in range(1, 7)]
        assert breaker[4]["status"]["resilience"]["circuit_state"] == "open", breaker
        assert breaker[5]["status"]["resilience"]["circuit_state"] == "open", breaker
        assert breaker[5]["has_action_proposal"] is False, breaker[5]
        restored = drill.restore()
        assert restored["fault"]["mode"] == "off", restored
        assert restored["resilience"]["circuit_state"] == "open", restored
        return {
            "phase": "faults",
            "run_id": drill.run_id,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "pod": os.environ.get("HOSTNAME", "unknown"),
            "observations": observations,
            "breaker": breaker,
            "final_status": restored,
        }
    finally:
        drill.restore()


def run_recovery(drill: Drill) -> dict[str, Any]:
    before = drill.status()
    assert before["fault"]["mode"] == "off", before
    assert before["resilience"]["circuit_state"] == "half_open", before
    recovered = drill.search("post-cooldown-recovery")
    assert recovered["status"]["resilience"]["circuit_state"] == "closed", recovered
    assert recovered["status"]["resilience"]["last_provider_outcome"] == "success", recovered
    assert recovered["trace_id"] and recovered["trace_id"] != "0" * 32, recovered
    final_status = drill.restore()
    assert final_status["fault"]["mode"] == "off", final_status
    return {
        "phase": "recovery",
        "run_id": drill.run_id,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "pod": os.environ.get("HOSTNAME", "unknown"),
        "before": before,
        "recovered": recovered,
        "final_status": final_status,
    }


def run_status(drill: Drill) -> dict[str, Any]:
    return {
        "phase": "status",
        "run_id": drill.run_id,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "pod": os.environ.get("HOSTNAME", "unknown"),
        "status": drill.status(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase", choices=("faults", "recovery", "status"), required=True
    )
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    drill = Drill(args.run_id)
    try:
        if args.phase == "faults":
            result = run_faults(drill)
        elif args.phase == "recovery":
            result = run_recovery(drill)
        else:
            result = run_status(drill)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    finally:
        drill.close()


if __name__ == "__main__":
    main()
