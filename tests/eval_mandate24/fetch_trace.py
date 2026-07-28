"""Fetch a just-created trace from the Jaeger query API by exact trace ID."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from typing import Any

try:  # Support both `python -m` and direct script execution.
    from .common import validate_trace_id, write_json
except ImportError:
    from common import validate_trace_id, write_json  # type: ignore


def fetch_trace(
    trace_id: str,
    jaeger_url: str,
    *,
    timeout_seconds: float = 10,
) -> dict[str, Any]:
    trace_id = validate_trace_id(trace_id)
    endpoint = f"{jaeger_url.rstrip('/')}/api/traces/{trace_id}"
    request = urllib.request.Request(
        endpoint,
        headers={"Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.load(response)
    traces = payload.get("data", []) if isinstance(payload, dict) else []
    if not traces:
        raise RuntimeError(f"trace {trace_id} was not found")
    returned_trace_ids = {
        str(trace.get("traceID", "")).lower()
        for trace in traces
        if isinstance(trace, dict)
    }
    if trace_id not in returned_trace_ids:
        raise RuntimeError("Jaeger response did not contain the requested trace")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace_id")
    parser.add_argument(
        "--jaeger-url",
        default="http://localhost:16686/jaeger/ui",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = fetch_trace(args.trace_id, args.jaeger_url)
    write_json(args.output, payload)
    print(
        json.dumps(
            {
                "trace_id": validate_trace_id(args.trace_id),
                "trace_count": len(payload["data"]),
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
