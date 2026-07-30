#!/usr/bin/env python3
"""Run paired, alternating M24 overhead observations against two shadow pods."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import sys
import time
from typing import Any

import grpc


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile requires at least one value")
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def call(
    stub: Any,
    pb2: Any,
    *,
    run_id: str,
    mode: str,
    pair: int,
    warmup: bool,
) -> dict[str, Any]:
    suffix = f"{pair:03d}"
    phase = "warmup" if warmup else "measure"
    # Arm-specific principals keep both requests cold in the shared response
    # cache. The strings have equal length and differ only by the arm marker.
    user_id = f"m24-{run_id}-{mode}-{phase}-{suffix}"
    session_id = f"m24-{run_id}-{mode}-{phase}-{suffix}"
    # Keep the timestamp-like run identifier out of model content because the
    # safety layer correctly treats long digit sequences as possible PII.
    # Cache isolation comes from the run-scoped user identity.
    question = f"Summarize portability for matched overhead case {phase}-{suffix}"
    request = pb2.AskProductAIAssistantRequest(
        product_id="OLJCESPC7Z",
        question=question,
        user_id=user_id,
        session_id=session_id,
    )
    started_wall_ns = time.time_ns()
    started = time.perf_counter()
    response = stub.AskProductAIAssistant(request, timeout=15)
    elapsed_ms = (time.perf_counter() - started) * 1_000
    return {
        "phase": phase,
        "pair": pair,
        "mode": mode,
        "started_wall_ns": started_wall_ns,
        "elapsed_ms": round(elapsed_ms, 3),
        "server_model_latency_ms": round(float(response.latency_ms), 3),
        "model_calls": int(response.model_calls),
        "input_tokens": int(response.input_tokens),
        "output_tokens": int(response.output_tokens),
        "cache_status": str(response.cache_status),
        "cache_eligible": bool(response.cache_eligible),
        "cache_reason": str(response.cache_reason),
        "memory_status": str(response.memory_status),
        "response_nonempty": bool(response.response),
        "outcome": (
            "answered"
            if int(response.input_tokens) > 0 and int(response.output_tokens) > 0
            else "zero_token_fallback"
        ),
    }


def summarize(rows: list[dict[str, Any]], gate_percent: float) -> dict[str, Any]:
    measured = [row for row in rows if row["phase"] == "measure"]
    grouped = {
        mode: [float(row["elapsed_ms"]) for row in measured if row["mode"] == mode]
        for mode in ("off", "on")
    }
    invalid = [
        row
        for row in measured
        if row["model_calls"] != 1
        or row["cache_status"] == "hit"
        or row["input_tokens"] <= 0
        or row["output_tokens"] <= 0
        or not row["response_nonempty"]
    ]
    stats: dict[str, Any] = {}
    for mode, values in grouped.items():
        stats[mode] = {
            "count": len(values),
            "min_ms": round(min(values), 3),
            "mean_ms": round(statistics.fmean(values), 3),
            "median_ms": round(statistics.median(values), 3),
            "p95_ms": round(percentile(values, 0.95), 3),
            "max_ms": round(max(values), 3),
        }

    p95_increase = (stats["on"]["p95_ms"] / stats["off"]["p95_ms"] - 1) * 100
    paired_deltas = []
    for pair in sorted({int(row["pair"]) for row in measured}):
        by_mode = {
            row["mode"]: float(row["elapsed_ms"])
            for row in measured
            if int(row["pair"]) == pair
        }
        paired_deltas.append(by_mode["on"] - by_mode["off"])

    return {
        "schema_version": "mandate24-matched-overhead-v2",
        "measurement": "client wall-clock gRPC latency",
        "design": "paired alternating order; same image/node/window; cold arm-specific principals",
        "off_contract": {
            "LLM_OBSERVABILITY_ENABLED": "false",
            "OTEL_SDK_DISABLED": "true",
            "interpretation": "conservative all-OpenTelemetry-off upper-bound baseline",
        },
        "on_contract": {
            "LLM_OBSERVABILITY_ENABLED": "true",
            "OTEL_SDK_DISABLED": "false",
        },
        "stats": stats,
        "p95_increase_percent": round(p95_increase, 3),
        "paired_delta_median_ms": round(statistics.median(paired_deltas), 3),
        "paired_delta_mean_ms": round(statistics.fmean(paired_deltas), 3),
        "gate_percent": gate_percent,
        "valid_rows": len(invalid) == 0,
        "invalid_row_count": len(invalid),
        "invalid_rows": [
            {
                "pair": row["pair"],
                "mode": row["mode"],
                "model_calls": row["model_calls"],
                "input_tokens": row["input_tokens"],
                "output_tokens": row["output_tokens"],
                "cache_status": row["cache_status"],
                "outcome": row["outcome"],
            }
            for row in invalid
        ],
        "pass": len(invalid) == 0 and p95_increase <= gate_percent,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--off-target", default="127.0.0.1:43551")
    parser.add_argument("--on-target", default="127.0.0.1:43552")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--pairs", type=int, default=40)
    parser.add_argument("--warmup-pairs", type=int, default=3)
    parser.add_argument("--gate-percent", type=float, default=5.0)
    parser.add_argument("--inter-call-delay", type=float, default=0.35)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--proto-dir", type=Path, required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(args.proto_dir.resolve()))
    import demo_pb2  # type: ignore
    import demo_pb2_grpc  # type: ignore

    channels = {
        "off": grpc.insecure_channel(args.off_target),
        "on": grpc.insecure_channel(args.on_target),
    }
    stubs = {
        mode: demo_pb2_grpc.ProductReviewServiceStub(channel)
        for mode, channel in channels.items()
    }
    for channel in channels.values():
        grpc.channel_ready_future(channel).result(timeout=20)

    rows: list[dict[str, Any]] = []
    try:
        for pair in range(1, args.warmup_pairs + 1):
            for mode in (("off", "on") if pair % 2 else ("on", "off")):
                row = call(
                    stubs[mode],
                    demo_pb2,
                    run_id=args.run_id,
                    mode=mode,
                    pair=pair,
                    warmup=True,
                )
                rows.append(row)
                print(json.dumps(row, sort_keys=True), flush=True)
                time.sleep(args.inter_call_delay)

        for pair in range(1, args.pairs + 1):
            for mode in (("off", "on") if pair % 2 else ("on", "off")):
                row = call(
                    stubs[mode],
                    demo_pb2,
                    run_id=args.run_id,
                    mode=mode,
                    pair=pair,
                    warmup=False,
                )
                rows.append(row)
                print(json.dumps(row, sort_keys=True), flush=True)
                time.sleep(args.inter_call_delay)
    finally:
        for channel in channels.values():
            channel.close()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = args.output_dir / "matched-overhead.jsonl"
    raw_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    summary = summarize(rows, args.gate_percent)
    (args.output_dir / "overhead-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
