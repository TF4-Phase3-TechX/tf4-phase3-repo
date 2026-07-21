#!/usr/bin/env python3
"""Mandate-15 external-scenario replay entry point.

Accepts a labeled incident scenario file and runs the detector's scoring
logic offline against each scenario's injected metric series. Replays poll by
poll sequentially, evaluating `decision.anomalous` (which simulates streak >= sustained_polls)
to accurately report per-case precision/recall contribution and lead-time.

Usage (one-command repro):
    cd techx-corp-platform/src/aiops
    .venv/bin/python -m benchmark.replay \\
      ../../../../docs/aio1/mandate-15/labeled-scenarios-v1.jsonl \\
      --output /tmp/m15-replay-report.json

On grading day, the BTC supplies a hidden scenario file:
    .venv/bin/python -m benchmark.replay <hidden-scenarios.jsonl> \\
      --output /tmp/m15-grading.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

try:
    from app.config import Settings
    from app.detection import Detector
except ImportError:
    _src = Path(__file__).resolve().parents[1]
    if str(_src) not in sys.path:
        sys.path.insert(0, str(_src))
    from app.config import Settings
    from app.detection import Detector


SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_scenarios(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"Scenarios file not found: {path}")
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"Scenarios file is empty: {path}")
    scenarios = []
    for line_no, line in enumerate(content.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            scenarios.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON parse error at line {line_no}: {exc}") from exc
    if not scenarios:
        raise ValueError(f"No valid scenarios found in file: {path}")
    return scenarios


def _validate_scenario(scenario: dict[str, Any], index: int) -> None:
    required = {
        "id",
        "scenario_kind",
        "description",
        "expected_detected",
        "expected_severity",
        "service",
        "signal",
        "baseline_series",
        "incident_series",
    }
    missing = required - set(scenario)
    if missing:
        raise ValueError(
            f"Scenario #{index} (id={scenario.get('id')!r}) missing fields: {missing}"
        )
    kind = scenario["scenario_kind"]
    if kind not in ("real_incident", "masking", "healthy_busy"):
        raise ValueError(
            f"Scenario #{index}: unknown scenario_kind {kind!r}; "
            "must be real_incident, masking, or healthy_busy"
        )
    if kind == "masking" and "hidden_incident_series" in scenario:
        hidden_req = {"hidden_incident_service", "hidden_incident_signal"}
        hidden_missing = hidden_req - set(scenario)
        if hidden_missing:
            raise ValueError(
                f"Masking scenario #{index} (id={scenario.get('id')!r}) "
                f"missing hidden incident metadata: {hidden_missing}"
            )


def _make_fake_series(points: list[float]) -> list[dict[str, Any]]:
    """Wrap a list of float values in the Prometheus range-query format."""
    return [{"metric": {}, "values": [[i, str(v)] for i, v in enumerate(points)]}]


def _simulate_event_polls(
    service: str,
    signal: str,
    baseline_series: list[float],
    incident_series: list[float],
    expected_detected: bool,
    expected_severity: str | None,
    settings: Settings,
) -> dict[str, Any]:
    """Replay poll by poll sequentially using a fresh Detector instance.

    Checks decision.anomalous (streak >= sustained_polls) at each step to accurately
    simulate worker incident creation and measure lead time.
    """
    detector = Detector(settings)
    query = f"replay:{signal}:{service}"

    detected = False
    first_anomalous_step: int | None = None
    detected_severity: str | None = None
    detected_confidence: float = 0.0
    runbook_id: str = "observe-and-escalate"
    recommended_action: str = "Collect more evidence"

    for step in range(1, len(incident_series) + 1):
        current_points = baseline_series + incident_series[:step]
        fake_series = _make_fake_series(current_points)
        if signal == "latency":
            decision = detector.latency(service, fake_series, query)
        else:
            decision = detector.error_rate(service, fake_series, query)

        if decision.anomalous:
            if not detected:
                detected = True
                first_anomalous_step = step
                detected_severity = decision.severity
                detected_confidence = decision.confidence
                runbook_id = decision.runbook_id
                recommended_action = decision.recommended_action

    severity_match = (
        (detected_severity == expected_severity)
        if (detected and expected_detected and expected_severity)
        else True
    )
    passed = (detected == expected_detected) and severity_match
    lead_time_seconds = (
        first_anomalous_step * settings.poll_seconds
        if first_anomalous_step is not None
        else None
    )

    # Event outcome classification for precision/recall confusion matrix
    if expected_detected and detected:
        classification = "TP"
    elif not expected_detected and detected:
        classification = "FP"
    elif expected_detected and not detected:
        classification = "FN"
    else:
        classification = "TN"

    return {
        "service": service,
        "signal": signal,
        "expected_detected": expected_detected,
        "actual_detected": detected,
        "expected_severity": expected_severity,
        "actual_severity": detected_severity,
        "severity_match": severity_match,
        "confidence": round(detected_confidence, 3),
        "lead_time_steps": first_anomalous_step,
        "lead_time_seconds": lead_time_seconds,
        "passed": passed,
        "classification": classification,
        "runbook_id": runbook_id,
        "recommended_action": recommended_action,
    }


def _evaluate_scenario(
    scenario: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    """Run detector simulation on one scenario, evaluating main and optional hidden events."""
    service = scenario["service"]
    signal = scenario["signal"]
    kind = scenario["scenario_kind"]
    baseline_points = list(map(float, scenario["baseline_series"]))
    incident_points = list(map(float, scenario["incident_series"]))
    expected_detected = bool(scenario["expected_detected"])
    expected_severity = scenario.get("expected_severity")

    primary_res = _simulate_event_polls(
        service=service,
        signal=signal,
        baseline_series=baseline_points,
        incident_series=incident_points,
        expected_detected=expected_detected,
        expected_severity=expected_severity,
        settings=settings,
    )

    hidden_res: dict[str, Any] | None = None
    if kind == "masking" and "hidden_incident_series" in scenario:
        hidden_service = scenario["hidden_incident_service"]
        hidden_signal = scenario["hidden_incident_signal"]
        hidden_baseline = list(
            map(
                float,
                scenario.get("hidden_baseline_series", scenario["baseline_series"]),
            )
        )
        hidden_incident = list(map(float, scenario["hidden_incident_series"]))
        hidden_expected_detected = bool(scenario.get("hidden_expected_detected", True))
        hidden_expected_severity = scenario.get("hidden_expected_severity")

        hidden_res = _simulate_event_polls(
            service=hidden_service,
            signal=hidden_signal,
            baseline_series=hidden_baseline,
            incident_series=hidden_incident,
            expected_detected=hidden_expected_detected,
            expected_severity=hidden_expected_severity,
            settings=settings,
        )

    # Scenario overall pass require both primary and hidden events to pass
    passed = primary_res["passed"] and (hidden_res["passed"] if hidden_res else True)

    events = [primary_res]
    if hidden_res:
        events.append(hidden_res)

    return {
        "scenario_id": scenario["id"],
        "scenario_kind": kind,
        "service": service,
        "signal": signal,
        "description": scenario.get("description", ""),
        "expected_detected": expected_detected,
        "actual_detected": primary_res["actual_detected"],
        "expected_severity": expected_severity,
        "actual_severity": primary_res["actual_severity"],
        "severity_match": primary_res["severity_match"],
        "confidence": primary_res["confidence"],
        "lead_time_steps": primary_res["lead_time_steps"],
        "lead_time_seconds": primary_res["lead_time_seconds"],
        "hidden_event": hidden_res,
        "events": events,
        "passed": passed,
        "runbook_id": primary_res["runbook_id"],
        "recommended_action": primary_res["recommended_action"],
    }


def _aggregate(
    cases: list[dict[str, Any]], errors: list[dict[str, Any]]
) -> dict[str, Any]:
    total_cases = len(cases)
    passed_cases = sum(1 for c in cases if c.get("passed", False))
    has_errors = len(errors) > 0
    all_passed = (total_cases > 0) and (passed_cases == total_cases) and (not has_errors)

    # Aggregate confusion matrix across all evaluated events (main + hidden)
    all_events = []
    for c in cases:
        all_events.extend(c.get("events", []))

    tp = sum(1 for e in all_events if e["classification"] == "TP")
    fp = sum(1 for e in all_events if e["classification"] == "FP")
    fn = sum(1 for e in all_events if e["classification"] == "FN")
    tn = sum(1 for e in all_events if e["classification"] == "TN")

    precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 1.0
    recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 1.0

    lead_times = [
        e["lead_time_seconds"]
        for e in all_events
        if e.get("lead_time_seconds") is not None
    ]
    avg_lead_time_s = round(mean(lead_times), 1) if lead_times else None

    by_kind: dict[str, dict[str, Any]] = {}
    for kind in ("real_incident", "masking", "healthy_busy"):
        subset = [c for c in cases if c["scenario_kind"] == kind]
        by_kind[kind] = {
            "count": len(subset),
            "passed": sum(1 for c in subset if c["passed"]),
        }

    return {
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "all_passed": all_passed,
        "events_evaluated": len(all_events),
        "confusion_matrix": {"TP": tp, "FP": fp, "FN": fn, "TN": tn},
        "precision": precision,
        "recall": recall,
        "avg_lead_time_seconds": avg_lead_time_s,
        "by_kind": by_kind,
    }


def replay(
    scenarios_path: Path,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Run all scenarios and return the full report dict."""
    settings = settings or Settings()

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    try:
        raw = _load_scenarios(scenarios_path)
    except Exception as exc:
        errors.append({"scenario_id": "load_error", "error": f"{type(exc).__name__}: {exc}"})
        raw = []

    for i, scenario in enumerate(raw, 1):
        sc_id = scenario.get("id", f"#{i}")
        try:
            _validate_scenario(scenario, i)
            result = _evaluate_scenario(scenario, settings)
            results.append(result)
            status = "PASS" if result["passed"] else "FAIL"
            print(
                f"[{i}/{len(raw)}] {sc_id} ({scenario['scenario_kind']}): "
                f"{status}  actual_detected={result['actual_detected']}  "
                f"lead_time={result['lead_time_seconds']}s",
                flush=True,
            )
        except Exception as exc:
            errors.append({
                "scenario_id": sc_id,
                "error": f"{type(exc).__name__}: {exc}",
            })
            print(f"[{i}/{len(raw)}] {sc_id}: ERROR {exc}", flush=True)

    aggregate = _aggregate(results, errors)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "scenarios_file": str(scenarios_path),
        "detector_config": {
            "poll_seconds": settings.poll_seconds,
            "sustained_polls": settings.sustained_polls,
            "latency_threshold_ms": settings.latency_threshold_ms,
            "error_rate_threshold": settings.error_rate_threshold,
            "zscore_threshold": settings.zscore_threshold,
            "ratio_threshold": settings.ratio_threshold,
            "ewma_threshold": settings.ewma_threshold,
            "trend_min_relative_change": settings.trend_min_relative_change,
        },
        "aggregate": aggregate,
        "cases": results,
        "errors": errors,
        "limitations": [
            "This replay uses synthetic metric series, not live Prometheus data.",
            "Lead-time is measured in poll-cycle steps where decision.anomalous became True.",
            "Precision and recall are computed across all evaluated primary and hidden events.",
            "Each target signal evaluation uses a fresh Detector instance to isolate streak state.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Mandate-15 external-scenario replay — "
            "deterministic offline detector evaluation"
        )
    )
    parser.add_argument(
        "scenarios",
        type=Path,
        help="Path to a JSONL file with labeled scenarios (one JSON object per line)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write the full JSON report to this path",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing output file",
    )
    args = parser.parse_args()

    if not args.scenarios.exists():
        parser.error(f"Scenarios file not found: {args.scenarios}")

    if args.output and args.output.exists() and not args.force:
        parser.error(
            f"Output file already exists: {args.output}. Pass --force to overwrite."
        )

    report = replay(args.scenarios)
    agg = report["aggregate"]

    print(
        f"\n{'='*60}\n"
        f"MANDATE-15 REPLAY RESULT\n"
        f"  Total cases : {agg['total_cases']}\n"
        f"  Passed      : {agg['passed_cases']} / {agg['total_cases']}\n"
        f"  All passed  : {agg['all_passed']}\n"
        f"  Events eval : {agg['events_evaluated']}\n"
        f"  Matrix (TP/FP/FN/TN): {agg['confusion_matrix']}\n"
        f"  Precision   : {agg['precision']}\n"
        f"  Recall      : {agg['recall']}\n"
        f"  Avg MTTD    : {agg['avg_lead_time_seconds']}s\n"
        f"  Errors      : {len(report['errors'])}\n"
        f"{'='*60}"
    )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report written to: {args.output}")

    return 0 if (agg["all_passed"] and len(report["errors"]) == 0) else 2


if __name__ == "__main__":
    raise SystemExit(main())
