"""Query aggregate LLM cost/call/latency views without reading raw logs."""

from __future__ import annotations

import argparse
import json
import math
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:  # Support both `python -m` and direct script execution.
    from .common import write_json
except ImportError:
    from common import write_json  # type: ignore


WINDOW_RE = re.compile(r"^[1-9][0-9]*[mhd]$")


def prom_query(prometheus_url: str, query: str) -> list[dict[str, Any]]:
    endpoint = (
        f"{prometheus_url.rstrip('/')}/api/v1/query?"
        + urllib.parse.urlencode({"query": query})
    )
    request = urllib.request.Request(
        endpoint,
        headers={"Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.load(response)
    if payload.get("status") != "success":
        raise RuntimeError("Prometheus query failed")
    return payload.get("data", {}).get("result", [])


def validate_result(metric_name: str, result: list[dict[str, Any]]) -> None:
    """Reject incomplete Prometheus evidence instead of publishing false proof."""
    if not result:
        raise RuntimeError(f"{metric_name}: Prometheus returned no samples")
    for index, sample in enumerate(result):
        labels = sample.get("metric")
        if not isinstance(labels, dict):
            raise RuntimeError(f"{metric_name}[{index}]: metric labels missing")
        for label_name in ("llm_model", "ai_surface"):
            if not str(labels.get(label_name, "")).strip():
                raise RuntimeError(
                    f"{metric_name}[{index}]: {label_name} label missing"
                )
        value = sample.get("value")
        if not isinstance(value, list) or len(value) != 2:
            raise RuntimeError(f"{metric_name}[{index}]: instant value missing")
        try:
            numeric_value = float(value[1])
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"{metric_name}[{index}]: sample is not numeric"
            ) from exc
        if not math.isfinite(numeric_value):
            raise RuntimeError(f"{metric_name}[{index}]: sample is not finite")


def aggregate(prometheus_url: str, window: str) -> dict[str, Any]:
    if not WINDOW_RE.fullmatch(window):
        raise ValueError("window must look like 30m, 1h, or 7d")
    selector = '{service_name="product-reviews"}'
    queries = {
        "estimated_cost_usd": (
            "sum by (llm_model, ai_surface) "
            f"(increase(app_llm_estimated_cost_usd_USD_total{selector}[{window}]))"
        ),
        "model_calls": (
            "sum by (llm_model, ai_surface) "
            f"(increase(app_llm_calls_total{selector}[{window}]))"
        ),
        "p95_latency_seconds": (
            "histogram_quantile(0.95, "
            "sum by (le, llm_model, ai_surface) "
            f"(rate(app_llm_latency_seconds_bucket{selector}[{window}])))"
        ),
    }
    query_results = []
    for metric, query in queries.items():
        result = prom_query(prometheus_url, query)
        validate_result(metric, result)
        query_results.append(
            {
                "metric": metric,
                "promql": query,
                "result": result,
            }
        )
    return {
        "schema_version": "mandate24-aggregate-v1",
        "window": window,
        "source": prometheus_url,
        "queries": query_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prometheus-url",
        default="http://localhost:9090",
    )
    parser.add_argument("--window", default="1h")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = aggregate(args.prometheus_url, args.window)
    write_json(args.output, report)
    print(
        json.dumps(
            {
                "window": args.window,
                "query_count": len(report["queries"]),
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
