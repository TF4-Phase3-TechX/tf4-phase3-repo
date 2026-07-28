"""Fetch an exact Jaeger trace and emit a content-free Mandate 25 summary."""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from collections import Counter

TRACE_ID = re.compile(r"^[0-9a-f]{32}$")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace_id")
    parser.add_argument(
        "--jaeger-url",
        default=(
            "http://jaeger.techx-observability.svc.cluster.local:16686/jaeger/ui"
        ),
    )
    args = parser.parse_args()
    trace_id = args.trace_id.lower()
    if not TRACE_ID.fullmatch(trace_id):
        raise ValueError("trace_id must be 32 lowercase hexadecimal characters")
    endpoint = f"{args.jaeger_url.rstrip('/')}/api/traces/{trace_id}"
    request = urllib.request.Request(endpoint, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.load(response)
    traces = payload.get("data", [])
    matching = [trace for trace in traces if trace.get("traceID", "").lower() == trace_id]
    if len(matching) != 1:
        raise RuntimeError(f"expected one exact trace, found {len(matching)}")
    spans = matching[0].get("spans", [])
    operations = Counter(str(span.get("operationName", "")) for span in spans)
    print(
        json.dumps(
            {
                "trace_id": trace_id,
                "trace_count": 1,
                "span_count": len(spans),
                "bedrock_converse_span_count": operations.get("bedrock.converse", 0),
                "operation_counts": dict(sorted(operations.items())),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
