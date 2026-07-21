#!/usr/bin/env python3
"""Mandate-15 external-scenario replay entry point.

Accepts a labeled incident scenario file and runs the detector's scoring
logic offline against each scenario's injected metric series, then reports
per-case precision/recall contribution and lead-time.

Usage (one-command repro):
    cd techx-corp-platform/src/aiops
    python -m benchmark.replay \\
      ../../../../docs/aio1/mandate-15/labeled-scenarios-v1.jsonl \\
      --output /tmp/m15-replay-report.json

On grading day, the BTC supplies a hidden scenario file:
    python -m benchmark.replay <hidden-scenarios.jsonl> \\
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

# Allow running as both `python -m benchmark.replay` and `python replay.py`
try:
    from app.config import Settings
    from app.detection import Detector
    from app.summary import IncidentSummaryGenerator
except ImportError:
    _src = Path(__file__).resolve().parents[1]
    if str(_src) not in sys.path:
        sys.path.insert(0, str(_src))
    from app.config import Settings
    from app.detection import Detector
    from app.summary import IncidentSummaryGenerator


SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_scenarios(path: Path) -> list[dict[str, Any]]:
    scenarios = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            scenarios.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON parse error at line {line_no}: {exc}") from exc
    return scenarios


def _validate_scenario(scenario: dict[str, Any], index: int) -> None:
    required = {
        "id", "scenario_kind", "description", "expected_detected",
        "expected_severity", "service", "signal",
        "baseline_series", "incident_series",
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


def _make_fake_series(points: list[float]) -> list[dict[str, Any]]:
    """Wrap a list of float values in the Prometheus range-query format."""
    return [{"metric": {}, "values": [[i, str(v)] for i, v in enumerate(points)]}]


def _evaluate_scenario(
    scenario: dict[str, Any],
    detector: Detector,
    settings: Settings,
) -> dict[str, Any]:
    """Run detector on one scenario; return per-case result record."""
    service = scenario["service"]
    signal = scenario["signal"]
    kind = scenario["scenario_kind"]
    baseline_points: list[float] = list(map(float, scenario["baseline_series"]))
    incident_points: list[float] = list(map(float, scenario["incident_series"]))

    # Full series = baseline window followed by incident window.
    full_series = baseline_points + incident_points
    query = f"replay:{signal}:{service}"
    fake_series = _make_fake_series(full_series)

    if signal == "latency":
        decision = detector.latency(service, fake_series, query)
    else:
        decision = detector.error_rate(service, fake_series, query)

    # Lead-time: number of incident-window steps until first breach.
    lead_time_steps: int | None = None
    for step in range(1, len(incident_points) + 1):
        partial = baseline_points + incident_points[:step]
        if signal == "latency":
            d = detector.latency(service, _make_fake_series(partial), query)
        else:
            d = detector.error_rate(service, _make_fake_series(partial), query)
        if d.breached:
            lead_time_steps = step
            break

    # For masking: also test the hidden subtle incident separately.
    hidden_detected: bool | None = None
    if kind == "masking" and "hidden_incident_series" in scenario:
        hidden_series = list(map(float, scenario["hidden_incident_series"]))
        combined = baseline_points + hidden_series
        detector_fresh = Detector(settings)
        if signal == "latency":
            hd = detector_fresh.latency(service, _make_fake_series(combined), query)
        else:
            hd = detector_fresh.error_rate(service, _make_fake_series(combined), query)
        hidden_detected = hd.breached

    expected_detected: bool = bool(scenario["expected_detected"])
    actual_detected: bool = decision.breached
    severity_match: bool = (
        decision.severity == scenario["expected_severity"]
        if actual_detected and expected_detected
        else True
    )

    # Precision contribution: 1 if alert is correct (no false alarm), 0 if false alarm.
    # Recall contribution: 1 if real incident was caught, 0 if missed.
    is_real_incident = expected_detected
    precision_contribution: float | None = None
    recall_contribution: float | None = None
    if actual_detected:
        precision_contribution = 1.0 if is_real_incident else 0.0
    if is_real_incident:
        recall_contribution = 1.0 if actual_detected else 0.0

    passed = (actual_detected == expected_detected) and severity_match
    if kind == "masking" and hidden_detected is not None:
        # Masking scenario additionally requires the hidden incident is found.
        passed = passed and hidden_detected

    lead_time_seconds: float | None = (
        lead_time_steps * settings.poll_seconds if lead_time_steps is not None else None
    )

    return {
        "scenario_id": scenario["id"],
        "scenario_kind": kind,
        "service": service,
        "signal": signal,
        "description": scenario.get("description", ""),
        "expected_detected": expected_detected,
        "actual_detected": actual_detected,
        "expected_severity": scenario.get("expected_severity"),
        "actual_severity": decision.severity if actual_detected else None,
        "severity_match": severity_match,
        "confidence": round(decision.confidence, 3),
        "coverage_status": decision.coverage_status,
        "precision_contribution": precision_contribution,
        "recall_contribution": recall_contribution,
        "lead_time_steps": lead_time_steps,
        "lead_time_seconds": lead_time_seconds,
        "hidden_incident_detected": hidden_detected,
        "passed": passed,
        "runbook_id": decision.runbook_id,
        "recommended_action": decision.recommended_action,
    }


def _aggregate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(cases)
    passed = sum(c["passed"] for c in cases)
    precision_cases = [c for c in cases if c["precision_contribution"] is not None]
    recall_cases = [c for c in cases if c["recall_contribution"] is not None]
    lead_time_cases = [c for c in cases if c["lead_time_seconds"] is not None]

    precision = (
        round(mean(c["precision_contribution"] for c in precision_cases), 4)
        if precision_cases
        else None
    )
    recall = (
        round(mean(c["recall_contribution"] for c in recall_cases), 4)
        if recall_cases
        else None
    )
    avg_lead_time_s = (
        round(mean(c["lead_time_seconds"] for c in lead_time_cases), 1)
        if lead_time_cases
        else None
    )

    by_kind: dict[str, dict[str, Any]] = {}
    for kind in ("real_incident", "masking", "healthy_busy"):
        subset = [c for c in cases if c["scenario_kind"] == kind]
        by_kind[kind] = {
            "count": len(subset),
            "passed": sum(c["passed"] for c in subset),
        }

    return {
        "total_cases": total,
        "passed_cases": passed,
        "all_passed": passed == total,
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
    detector = Detector(settings)

    raw = _load_scenarios(scenarios_path)
    if not raw:
        raise ValueError(f"No scenarios found in {scenarios_path}")

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for i, scenario in enumerate(raw, 1):
        try:
            _validate_scenario(scenario, i)
            result = _evaluate_scenario(scenario, detector, settings)
            results.append(result)
            status = "PASS" if result["passed"] else "FAIL"
            print(
                f"[{i}/{len(raw)}] {scenario['id']} ({scenario['scenario_kind']}): "
                f"{status}  detected={result['actual_detected']}  "
                f"lead_time={result['lead_time_seconds']}s",
                flush=True,
            )
        except Exception as exc:
            errors.append({
                "scenario_id": scenario.get("id", f"#{i}"),
                "error": f"{type(exc).__name__}: {exc}",
            })
            print(
                f"[{i}/{len(raw)}] {scenario.get('id', f'#{i}')}: ERROR {exc}",
                flush=True,
            )

    aggregate = _aggregate(results)
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
            "Lead-time is measured in poll-cycle steps; wall-clock MTTD = lead_time_steps * poll_seconds.",
            "Precision and recall are computed per-case; aggregate numbers assume equal case weight.",
            "Masking detection uses a fresh Detector instance to isolate streak state from the noise spike.",
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
        f"  Precision   : {agg['precision']}\n"
        f"  Recall      : {agg['recall']}\n"
        f"  Avg MTTD    : {agg['avg_lead_time_seconds']}s\n"
        f"{'='*60}"
    )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report written to: {args.output}")

    return 0 if agg["all_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
