"""Build a versioned, content-free quality baseline from external observations."""

from __future__ import annotations

import argparse
import math
from copy import deepcopy
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable

from .common import git_metadata, sha256_value, utc_now, write_json
from .contract import load_observations, validate


DEFAULT_CONFIG: dict[str, Any] = {
    "window_size": 30,
    "stride": 10,
    "required_consecutive": 2,
    "minimum_window_span_seconds": 1740,
    "minimum_persistence_seconds": 600,
    "recovery_windows": 3,
    "min_baseline_samples": 50,
    "confidence_z": 2.576,
    "metrics": {
        "fallback": {
            "signal_name": "fallback_rate",
            "kind": "binary",
            "direction": "increase",
            "min_delta": 0.10,
        },
        "abstained": {
            "signal_name": "abstention_rate",
            "kind": "binary",
            "direction": "increase",
            "min_delta": 0.15,
        },
        "faithfulness": {
            "signal_name": "faithfulness",
            "kind": "continuous",
            "direction": "decrease",
            "min_delta": 0.10,
            "jsd_threshold": 0.10,
            "bin_edges": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        },
    },
}


def wilson_interval(
    successes: int,
    samples: int,
    z: float,
) -> tuple[float, float]:
    if samples <= 0:
        raise ValueError("Wilson interval requires at least one sample")
    probability = successes / samples
    denominator = 1 + z * z / samples
    center = (probability + z * z / (2 * samples)) / denominator
    margin = (
        z
        * math.sqrt(
            probability * (1 - probability) / samples
            + z * z / (4 * samples * samples)
        )
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def histogram(values: Iterable[float], edges: list[float]) -> list[int]:
    counts = [0 for _ in range(len(edges) - 1)]
    for raw_value in values:
        value = float(raw_value)
        if not edges[0] <= value <= edges[-1]:
            raise ValueError(f"metric value {value} is outside histogram bounds")
        index = len(counts) - 1
        for candidate in range(len(counts)):
            if value < edges[candidate + 1]:
                index = candidate
                break
        counts[index] += 1
    return counts


def _single_compatibility_value(
    observations: list[dict[str, Any]],
    field: str,
    override: str | None,
) -> str | None:
    if override:
        return override
    values = {
        str(row[field])
        for row in observations
        if str(row.get(field, "")).strip()
    }
    if len(values) > 1:
        raise ValueError(f"baseline contains multiple {field} values: {sorted(values)}")
    return next(iter(values), None)


def build_baseline(
    observations: list[dict[str, Any]],
    *,
    config: dict[str, Any] | None = None,
    created_at_utc: str | None = None,
    git: dict[str, Any] | None = None,
    model_id: str | None = None,
    guardrail_version: str | None = None,
    scorer_version: str | None = None,
) -> dict[str, Any]:
    if not observations:
        raise ValueError("at least one baseline observation is required")
    resolved_config = deepcopy(config or DEFAULT_CONFIG)
    minimum = int(resolved_config["min_baseline_samples"])
    z = float(resolved_config["confidence_z"])
    surfaces: dict[str, Any] = {}
    for surface in ("review_summary", "copilot"):
        surface_rows = [
            observation
            for observation in observations
            if observation["surface"] == surface
        ]
        if not surface_rows:
            continue
        metric_baselines: dict[str, Any] = {}
        for metric_name, metric_config in resolved_config["metrics"].items():
            values = [
                float(row["metrics"][metric_name])
                for row in surface_rows
                if metric_name in row["metrics"]
            ]
            if not values:
                continue
            sample_count = len(values)
            ready = sample_count >= minimum
            if metric_config["kind"] == "binary":
                unfavorable = int(sum(values))
                lower, upper = wilson_interval(unfavorable, sample_count, z)
                metric_baselines[metric_name] = {
                    "kind": "binary",
                    "sample_count": sample_count,
                    "ready": ready,
                    "unfavorable_count": unfavorable,
                    "rate": unfavorable / sample_count,
                    "wilson_lower": lower,
                    "wilson_upper": upper,
                }
            else:
                edges = [float(edge) for edge in metric_config["bin_edges"]]
                metric_baselines[metric_name] = {
                    "kind": "continuous",
                    "sample_count": sample_count,
                    "ready": ready,
                    "mean": mean(values),
                    "median": median(values),
                    "minimum": min(values),
                    "maximum": max(values),
                    "bin_edges": edges,
                    "bin_counts": histogram(values, edges),
                }
        surfaces[surface] = {
            "observation_count": len(surface_rows),
            "metrics": metric_baselines,
        }

    baseline = {
        "schema_version": "mandate27-baseline-v1",
        "created_at_utc": created_at_utc or utc_now(),
        "input_sha256": sha256_value(observations),
        "git": git or git_metadata(),
        "compatibility": {
            "model_id": _single_compatibility_value(
                observations, "model_id", model_id
            ),
            "guardrail_version": _single_compatibility_value(
                observations, "guardrail_version", guardrail_version
            ),
            "scorer_version": _single_compatibility_value(
                observations, "scorer_version", scorer_version
            ),
        },
        "config": resolved_config,
        "surfaces": surfaces,
    }
    validate(baseline, "baseline.schema.json")
    return baseline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a versioned Mandate 27 quality baseline."
    )
    parser.add_argument("observations", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-id")
    parser.add_argument("--guardrail-version")
    parser.add_argument("--scorer-version")
    parser.add_argument("--min-baseline-samples", type=int, default=50)
    args = parser.parse_args()
    if args.min_baseline_samples < 10:
        raise ValueError("min-baseline-samples must be at least 10")
    config = deepcopy(DEFAULT_CONFIG)
    config["min_baseline_samples"] = args.min_baseline_samples
    baseline = build_baseline(
        load_observations(args.observations),
        config=config,
        model_id=args.model_id,
        guardrail_version=args.guardrail_version,
        scorer_version=args.scorer_version,
    )
    write_json(args.output, baseline)
    ready_metrics = sum(
        metric["ready"]
        for surface in baseline["surfaces"].values()
        for metric in surface["metrics"].values()
    )
    print(
        f"baseline={args.output} surfaces={len(baseline['surfaces'])} "
        f"ready_metrics={ready_metrics}"
    )


if __name__ == "__main__":
    main()
