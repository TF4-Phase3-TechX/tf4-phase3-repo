"""Generate deterministic stable and shifted external replay fixtures."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .common import write_jsonl


MODEL_ID = "fixture-model-v1"
GUARDRAIL_VERSION = "3"
SCORER_VERSION = "mandate14-v2"
START = datetime(2026, 7, 30, tzinfo=timezone.utc)


def _normal_metrics(surface: str, index: int) -> dict[str, Any]:
    if surface == "copilot":
        fallback = int(index % 50 == 0)
        abstained = int(index % 12 == 0)
        faithfulness_values = (0.92, 0.96, 1.0, 0.94, 0.98)
    else:
        fallback = int(index % 80 == 0)
        abstained = int(index % 10 == 0)
        faithfulness_values = (0.90, 0.94, 0.98, 0.96, 1.0)
    return {
        "fallback": fallback,
        "abstained": abstained,
        "faithfulness": faithfulness_values[index % len(faithfulness_values)],
    }


def build_series(
    name: str,
    *,
    samples_per_surface: int = 120,
) -> list[dict[str, Any]]:
    supported = {
        "baseline",
        "stable",
        "transient_spike",
        "seasonal_stable",
        "shifted_copilot_fallback",
        "shifted_review_faithfulness",
    }
    if name not in supported:
        raise ValueError(f"unsupported fixture name: {name}")
    rows: list[dict[str, Any]] = []
    for index in range(samples_per_surface):
        observed_at = START + timedelta(minutes=index)
        for surface in ("review_summary", "copilot"):
            metrics = _normal_metrics(surface, index)
            if name == "transient_spike" and surface == "copilot":
                if index in {60, 61}:
                    metrics["fallback"] = 1
            elif name == "seasonal_stable":
                # Move normal abstentions within each 30-sample window without
                # changing their expected rate.
                if surface == "copilot":
                    metrics["abstained"] = int((index + (index // 30) * 3) % 12 == 0)
                else:
                    metrics["abstained"] = int((index + (index // 30) * 2) % 10 == 0)
            elif name == "shifted_copilot_fallback":
                if surface == "copilot" and index >= 60:
                    metrics["fallback"] = int(index % 3 != 0)
            elif name == "shifted_review_faithfulness":
                if surface == "review_summary" and index >= 60:
                    metrics["faithfulness"] = 0.52 + 0.02 * (index % 3)
            rows.append(
                {
                    "schema_version": "mandate27-observation-v1",
                    "event_id": f"{name}-{surface}-{index:04d}",
                    "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
                    "surface": surface,
                    "model_id": MODEL_ID,
                    "guardrail_version": GUARDRAIL_VERSION,
                    "scorer_version": SCORER_VERSION,
                    "metrics": metrics,
                }
            )
    return rows


def generate(output_dir: Path) -> dict[str, Path]:
    paths = {}
    for name in (
        "baseline",
        "stable",
        "transient_spike",
        "seasonal_stable",
        "shifted_copilot_fallback",
        "shifted_review_faithfulness",
    ):
        path = output_dir / f"{name.replace('_', '-')}.jsonl"
        write_jsonl(path, build_series(name))
        paths[name] = path
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    paths = generate(args.output_dir)
    for name, path in paths.items():
        print(f"{name}={path}")


if __name__ == "__main__":
    main()
