"""Collect bounded, read-only Prometheus windows for detector replay.

The manifest carries explicit operator labels; this collector never infers that
a quiet-looking window is normal or that a high value is an incident.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


def _timestamp(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def collect(manifest: dict[str, Any], client: httpx.Client) -> dict[str, Any]:
    label_authority = str(manifest.get("label_authority", "")).strip()
    label_evidence = manifest.get("label_evidence", [])
    if not label_authority or not isinstance(label_evidence, list) or not label_evidence:
        raise ValueError("label_authority and non-empty label_evidence are required")
    url = str(manifest["prometheus_url"]).rstrip("/")
    start = _timestamp(str(manifest["start"]))
    end = _timestamp(str(manifest["end"]))
    step = int(manifest.get("step_seconds", 60))
    cases = []
    for spec in manifest.get("cases", []):
        response = client.get(
            f"{url}/api/v1/query_range",
            params={
                "query": spec["query"],
                "start": start,
                "end": end,
                "step": step,
            },
        )
        response.raise_for_status()
        body = response.json()
        if body.get("status") != "success":
            raise RuntimeError(f"Prometheus query failed for {spec['name']}: {body}")
        result = body.get("data", {}).get("result", [])
        if len(result) != 1:
            raise RuntimeError(
                f"case {spec['name']} expected exactly one series, got {len(result)}"
            )
        raw_values = result[0].get("values", [])
        points = [float(value) for _, value in raw_values if value not in (None, "NaN")]
        if not points:
            raise RuntimeError(f"case {spec['name']} returned no numeric points")
        cases.append(
            {
                "name": spec["name"],
                "points": points,
                "floor": float(spec["floor"]),
                "anomalous": bool(spec["anomalous"]),
                "purpose": spec.get("purpose", "operator-labelled Prometheus window"),
                "query": spec["query"],
                "metric": result[0].get("metric", {}),
                "sample_count": len(points),
            }
        )
    if not cases:
        raise ValueError("manifest must contain at least one case")
    source = {
        "kind": "prometheus_query_range",
        "start_utc": datetime.fromtimestamp(start, timezone.utc).isoformat(),
        "end_utc": datetime.fromtimestamp(end, timezone.utc).isoformat(),
        "step_seconds": step,
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "label_authority": label_authority,
        "label_evidence": label_evidence,
    }
    payload = {
        "scope": manifest.get("scope", "TF4 production Prometheus labelled replay"),
        "source": source,
        "cases": cases,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["sha256_before_hash_field"] = hashlib.sha256(canonical).hexdigest()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    with httpx.Client(timeout=args.timeout) as client:
        payload = collect(manifest, client)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
