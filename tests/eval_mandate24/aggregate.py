"""Query aggregate LLM cost/call/latency views without reading raw logs."""

from __future__ import annotations

import argparse
import json
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
    return {
        "schema_version": "mandate24-aggregate-v1",
        "window": window,
        "source": prometheus_url,
        "queries": [
            {
                "metric": metric,
                "promql": query,
                "result": prom_query(prometheus_url, query),
            }
            for metric, query in queries.items()
        ],
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
