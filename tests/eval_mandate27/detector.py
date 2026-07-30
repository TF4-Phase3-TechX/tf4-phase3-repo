"""Rolling, persistence-gated drift detector for bounded AI quality metrics."""

from __future__ import annotations

from collections import defaultdict
from math import log2
from statistics import mean
from typing import Any

from .baseline import histogram, wilson_interval
from .common import git_metadata, parse_timestamp, sha256_value, utc_now


def jensen_shannon_divergence(
    baseline_counts: list[int],
    current_counts: list[int],
) -> float:
    if len(baseline_counts) != len(current_counts):
        raise ValueError("histograms must use identical bins")
    baseline_total = sum(baseline_counts)
    current_total = sum(current_counts)
    if baseline_total <= 0 or current_total <= 0:
        raise ValueError("histograms must contain samples")
    baseline = [value / baseline_total for value in baseline_counts]
    current = [value / current_total for value in current_counts]
    midpoint = [
        (baseline_value + current_value) / 2
        for baseline_value, current_value in zip(baseline, current)
    ]

    def divergence(values: list[float]) -> float:
        return sum(
            value * log2(value / middle)
            for value, middle in zip(values, midpoint)
            if value > 0 and middle > 0
        )

    return (divergence(baseline) + divergence(current)) / 2


def _compatibility_mismatches(
    observations: list[dict[str, Any]],
    baseline: dict[str, Any],
) -> list[dict[str, Any]]:
    diagnostics = []
    compatibility = baseline["compatibility"]
    for field in ("model_id", "guardrail_version", "scorer_version"):
        expected = compatibility.get(field)
        missing_observations = sum(
            not str(row.get(field, "")).strip() for row in observations
        )
        observed = {
            str(row[field])
            for row in observations
            if str(row.get(field, "")).strip()
        }
        if expected and (
            missing_observations > 0 or observed != {expected}
        ):
            diagnostics.append(
                {
                    "code": "baseline_incompatible",
                    "field": field,
                    "expected": expected,
                    "observed": sorted(observed),
                    "missing_observations": missing_observations,
                }
            )
    return diagnostics


def _evaluate_binary(
    values: list[float],
    baseline_metric: dict[str, Any],
    metric_config: dict[str, Any],
    confidence_z: float,
) -> dict[str, Any]:
    unfavorable = int(sum(values))
    current = unfavorable / len(values)
    current_lower, current_upper = wilson_interval(
        unfavorable, len(values), confidence_z
    )
    baseline_value = float(baseline_metric["rate"])
    delta = current - baseline_value
    return {
        "baseline_value": baseline_value,
        "current_value": current,
        "absolute_delta": delta,
        "threshold": float(metric_config["min_delta"]),
        "statistic": "wilson_interval",
        "statistic_value": current_lower - float(baseline_metric["wilson_upper"]),
        "current_interval": [current_lower, current_upper],
        "baseline_interval": [
            float(baseline_metric["wilson_lower"]),
            float(baseline_metric["wilson_upper"]),
        ],
        "breach": (
            delta >= float(metric_config["min_delta"])
            and current_lower > float(baseline_metric["wilson_upper"])
        ),
    }


def _evaluate_continuous(
    values: list[float],
    baseline_metric: dict[str, Any],
    metric_config: dict[str, Any],
) -> dict[str, Any]:
    baseline_value = float(baseline_metric["mean"])
    current = mean(values)
    delta = baseline_value - current
    edges = [float(value) for value in baseline_metric["bin_edges"]]
    jsd = jensen_shannon_divergence(
        [int(value) for value in baseline_metric["bin_counts"]],
        histogram(values, edges),
    )
    return {
        "baseline_value": baseline_value,
        "current_value": current,
        "absolute_delta": delta,
        "threshold": float(metric_config["min_delta"]),
        "statistic": "jensen_shannon_divergence",
        "statistic_value": jsd,
        "statistic_threshold": float(metric_config["jsd_threshold"]),
        # A material mean regression is sufficient. JSD remains a useful
        # diagnostic, but coarse bins must never mask a threshold breach.
        "breach": delta >= float(metric_config["min_delta"]),
    }


def detect(
    observations: list[dict[str, Any]],
    baseline: dict[str, Any],
    *,
    generated_at_utc: str | None = None,
    git: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = baseline["config"]
    compatibility_diagnostics = _compatibility_mismatches(
        observations, baseline
    )
    if compatibility_diagnostics:
        return {
            "schema_version": "mandate27-report-v1",
            "generated_at_utc": generated_at_utc or utc_now(),
            "status": "baseline_incompatible",
            "baseline_sha256": sha256_value(baseline),
            "input_sha256": sha256_value(observations),
            "git": git or git_metadata(),
            "config": config,
            "signals": [],
            "windows": [],
            "diagnostics": compatibility_diagnostics,
        }

    by_surface: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for observation in observations:
        by_surface[observation["surface"]].append(observation)

    windows: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    evaluated_metrics = 0
    warming_metrics = 0
    insufficient_metrics = 0
    window_size = int(config["window_size"])
    stride = int(config["stride"])
    required_consecutive = int(config["required_consecutive"])
    minimum_window_span = int(config["minimum_window_span_seconds"])
    minimum_persistence = int(config["minimum_persistence_seconds"])
    recovery_windows = int(config["recovery_windows"])
    confidence_z = float(config["confidence_z"])

    for surface, baseline_surface in baseline["surfaces"].items():
        surface_rows = by_surface.get(surface, [])
        if not surface_rows:
            ready_metrics = [
                (metric_name, config["metrics"][metric_name])
                for metric_name, value in baseline_surface["metrics"].items()
                if value.get("ready", False)
            ]
            for _, metric_config in ready_metrics:
                diagnostics.append(
                    {
                        "code": "current_surface_missing",
                        "surface": surface,
                        "metric": metric_config["signal_name"],
                        "sample_count": 0,
                        "required": window_size,
                    }
                )
                insufficient_metrics += 1
            continue
        for metric_name, baseline_metric in baseline_surface["metrics"].items():
            metric_config = config["metrics"][metric_name]
            metric_rows = [
                row for row in surface_rows if metric_name in row["metrics"]
            ]
            if not metric_rows:
                if baseline_metric.get("ready", False):
                    diagnostics.append(
                        {
                            "code": "current_metric_missing",
                            "surface": surface,
                            "metric": metric_config["signal_name"],
                            "sample_count": 0,
                            "required": window_size,
                        }
                    )
                    insufficient_metrics += 1
                continue
            if not baseline_metric.get("ready", False):
                diagnostics.append(
                    {
                        "code": "baseline_metric_insufficient",
                        "surface": surface,
                        "metric": metric_config["signal_name"],
                        "sample_count": (
                            int(baseline_metric["sample_count"])
                            if baseline_metric
                            else 0
                        ),
                        "required": int(config["min_baseline_samples"]),
                    }
                )
                insufficient_metrics += 1
                continue
            if len(metric_rows) < window_size:
                diagnostics.append(
                    {
                        "code": "current_window_warming_up",
                        "surface": surface,
                        "metric": metric_config["signal_name"],
                        "sample_count": len(metric_rows),
                        "required": window_size,
                    }
                )
                warming_metrics += 1
                continue

            evaluated_metrics += 1
            consecutive = 0
            clean_after_drift = 0
            signal_emitted = False
            first_breach_row: dict[str, Any] | None = None
            first_breach_end = None
            time_span_diagnostic_emitted = False
            for end in range(window_size, len(metric_rows) + 1, stride):
                window_rows = metric_rows[end - window_size : end]
                window_start_time = parse_timestamp(
                    window_rows[0]["observed_at"]
                )
                window_end_time = parse_timestamp(
                    window_rows[-1]["observed_at"]
                )
                window_span_seconds = (
                    window_end_time - window_start_time
                ).total_seconds()
                if window_span_seconds < minimum_window_span:
                    if not time_span_diagnostic_emitted:
                        diagnostics.append(
                            {
                                "code": "current_window_time_span_insufficient",
                                "surface": surface,
                                "metric": metric_config["signal_name"],
                                "span_seconds": window_span_seconds,
                                "required": minimum_window_span,
                            }
                        )
                        time_span_diagnostic_emitted = True
                        warming_metrics += 1
                    windows.append(
                        {
                            "surface": surface,
                            "metric": metric_config["signal_name"],
                            "window_start": window_rows[0]["observed_at"],
                            "window_end": window_rows[-1]["observed_at"],
                            "sample_count": len(window_rows),
                            "window_span_seconds": window_span_seconds,
                            "state": "warming_up",
                            "consecutive_breaches": 0,
                            "breach": False,
                        }
                    )
                    consecutive = 0
                    first_breach_row = None
                    first_breach_end = None
                    continue
                values = [
                    float(row["metrics"][metric_name])
                    for row in window_rows
                ]
                if metric_config["kind"] == "binary":
                    result = _evaluate_binary(
                        values,
                        baseline_metric,
                        metric_config,
                        confidence_z,
                    )
                else:
                    result = _evaluate_continuous(
                        values,
                        baseline_metric,
                        metric_config,
                    )
                if result["breach"]:
                    consecutive += 1
                    clean_after_drift = 0
                    if first_breach_row is None:
                        first_breach_row = window_rows[0]
                        first_breach_end = window_end_time
                else:
                    consecutive = 0
                    first_breach_row = None
                    first_breach_end = None
                    if signal_emitted:
                        clean_after_drift += 1

                state = "normal"
                if result["breach"]:
                    state = (
                        "drift"
                        if (
                            consecutive >= required_consecutive
                            and first_breach_end is not None
                            and (
                                window_end_time - first_breach_end
                            ).total_seconds()
                            >= minimum_persistence
                        )
                        else "suspected"
                    )
                elif signal_emitted and clean_after_drift < recovery_windows:
                    state = "recovering"
                elif signal_emitted:
                    state = "recovered"

                window_result = {
                    "surface": surface,
                    "metric": metric_config["signal_name"],
                    "window_start": window_rows[0]["observed_at"],
                    "window_end": window_rows[-1]["observed_at"],
                    "sample_count": len(window_rows),
                    "window_span_seconds": window_span_seconds,
                    "state": state,
                    "consecutive_breaches": consecutive,
                    **result,
                }
                windows.append(window_result)

                if state == "recovered":
                    signal_emitted = False
                    clean_after_drift = 0

                if (
                    state == "drift"
                    and not signal_emitted
                    and first_breach_row is not None
                ):
                    signals.append(
                        {
                            "schema_version": "mandate27-drift-signal-v1",
                            "status": "drift",
                            "surface": surface,
                            "metric": metric_config["signal_name"],
                            "detected_at": window_rows[-1]["observed_at"],
                            "window_start": window_rows[0]["observed_at"],
                            "sample_count": len(window_rows),
                            "baseline_value": result["baseline_value"],
                            "current_value": result["current_value"],
                            "absolute_delta": result["absolute_delta"],
                            "threshold": result["threshold"],
                            "consecutive_breaches": consecutive,
                            "first_breach_window_event_id": first_breach_row[
                                "event_id"
                            ],
                        }
                    )
                    signal_emitted = True

    if signals:
        status = "drift"
    elif insufficient_metrics:
        status = "baseline_insufficient"
    elif warming_metrics:
        status = "warming_up"
    elif evaluated_metrics:
        status = "no_drift"
    else:
        status = "warming_up"
        diagnostics.append({"code": "no_supported_metrics"})

    return {
        "schema_version": "mandate27-report-v1",
        "generated_at_utc": generated_at_utc or utc_now(),
        "status": status,
        "baseline_sha256": sha256_value(baseline),
        "input_sha256": sha256_value(observations),
        "git": git or git_metadata(),
        "config": config,
        "signals": signals,
        "windows": windows,
        "diagnostics": diagnostics,
    }
