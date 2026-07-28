"""Prove a marked input is absent from one trace and retained OpenSearch logs."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

try:  # Support both `python -m` and direct script execution.
    from .common import write_json
except ImportError:
    from common import write_json  # type: ignore


def _opensearch_hits(
    opensearch_url: str,
    index: str,
    marker: str,
) -> int:
    endpoint = f"{opensearch_url.rstrip('/')}/{index}/_search"
    body = json.dumps({
        "size": 0,
        "track_total_hits": True,
        "query": {
            "simple_query_string": {
                "query": f'"{marker}"',
                "fields": ["*"],
                "default_operator": "and",
            }
        },
    }).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.load(response)
    total: Any = payload.get("hits", {}).get("total", 0)
    return int(total.get("value", 0) if isinstance(total, dict) else total)


def verify(
    marker: str,
    trace_path: Path,
    opensearch_url: str,
    index: str,
) -> dict[str, Any]:
    if not marker:
        raise ValueError("marker is required")
    trace_text = trace_path.read_text(encoding="utf-8")
    trace_hits = trace_text.count(marker)
    log_hits = _opensearch_hits(opensearch_url, index, marker)
    report = {
        "schema_version": "mandate24-marker-absence-v1",
        "marker_sha256": hashlib.sha256(marker.encode("utf-8")).hexdigest(),
        "trace_file": str(trace_path),
        "trace_raw_marker_hits": trace_hits,
        "opensearch_raw_marker_hits": log_hits,
        "pass": trace_hits == 0 and log_hits == 0,
    }
    if not report["pass"]:
        raise RuntimeError("raw marker was retained in trace or log storage")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--marker", required=True)
    parser.add_argument("--trace-json", type=Path, required=True)
    parser.add_argument(
        "--opensearch-url",
        default="http://localhost:9200",
    )
    parser.add_argument("--index", default="otel-logs-*")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(
        args.marker,
        args.trace_json,
        args.opensearch_url,
        args.index,
    )
    write_json(args.output, report)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
