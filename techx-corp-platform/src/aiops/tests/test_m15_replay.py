"""Tests for the Mandate-15 external-scenario replay CLI (benchmark.replay).

Covers:
- real_incident: detector fires within 1 detector cycle (lead_time_steps <= 1, 45s)
- masking: noise spike on main service doesn't trigger, while hidden target service/signal incident is caught within 1 cycle
- healthy_busy: no false alarm on high-load-but-healthy data
- event-level confusion matrix (TP, FP, FN, TN) and precision/recall
- schema validation errors & scenario parsing errors enforce all_passed = False and non-zero exit code
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from app.config import Settings
from benchmark.replay import _aggregate, _load_scenarios, _validate_scenario, replay


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NORMAL_LATENCY = [120.0] * 30  # stable ~120 ms baseline
HIGH_LATENCY = [2500.0] * 8   # sustained well above 1 000 ms floor

NORMAL_ERROR = [0.008] * 30   # ~0.8% baseline
HIGH_ERROR = [0.10] * 8       # 10% — above 5% floor


def _write_jsonl(tmp_path: Path, scenarios: list[dict]) -> Path:
    path = tmp_path / "scenarios.jsonl"
    path.write_text("\n".join(json.dumps(s) for s in scenarios), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Validation Tests
# ---------------------------------------------------------------------------


def test_validate_scenario_ok():
    scenario = {
        "id": "test-01",
        "scenario_kind": "real_incident",
        "description": "ok",
        "expected_detected": True,
        "expected_severity": "high",
        "service": "frontend",
        "signal": "latency",
        "baseline_series": NORMAL_LATENCY,
        "incident_series": HIGH_LATENCY,
    }
    _validate_scenario(scenario, 1)  # must not raise


def test_validate_scenario_missing_fields():
    with pytest.raises(ValueError, match="missing fields"):
        _validate_scenario({"id": "x"}, 1)


def test_validate_scenario_bad_kind():
    scenario = {
        "id": "bad",
        "scenario_kind": "unknown_kind",
        "description": "x",
        "expected_detected": True,
        "expected_severity": "medium",
        "service": "frontend",
        "signal": "latency",
        "baseline_series": NORMAL_LATENCY,
        "incident_series": HIGH_LATENCY,
    }
    with pytest.raises(ValueError, match="unknown scenario_kind"):
        _validate_scenario(scenario, 1)


def test_validate_scenario_unsupported_signal():
    scenario = {
        "id": "bad_signal",
        "scenario_kind": "real_incident",
        "description": "unsupported signal",
        "expected_detected": True,
        "expected_severity": "high",
        "service": "frontend",
        "signal": "unsupported_memory_leak",
        "baseline_series": NORMAL_LATENCY,
        "incident_series": HIGH_LATENCY,
    }
    with pytest.raises(ValueError, match="unsupported signal"):
        _validate_scenario(scenario, 1)


def test_validate_masking_scenario_missing_hidden_metadata():
    scenario = {
        "id": "bad_masking",
        "scenario_kind": "masking",
        "description": "missing hidden metadata",
        "expected_detected": False,
        "expected_severity": "medium",
        "service": "checkout",
        "signal": "error_rate",
        "baseline_series": NORMAL_ERROR,
        "incident_series": NORMAL_ERROR[:5],
        "hidden_incident_series": HIGH_LATENCY,  # missing hidden_incident_service and other fields
    }
    with pytest.raises(ValueError, match="missing required hidden fields"):
        _validate_scenario(scenario, 1)


# ---------------------------------------------------------------------------
# Core Scenario Behavior & 1 Detector Cycle Hard Bar Tests
# ---------------------------------------------------------------------------


def test_real_incident_latency_detected_within_one_detector_cycle(tmp_path: Path):
    """A genuine acute latency spike must fire within 1 detector cycle (lead_time_steps <= 1, 45s)."""
    scenarios = [
        {
            "id": "real-latency",
            "scenario_kind": "real_incident",
            "description": "latency spike",
            "expected_detected": True,
            "expected_severity": "high",
            "service": "frontend",
            "signal": "latency",
            "baseline_series": NORMAL_LATENCY,
            "incident_series": HIGH_LATENCY,
        }
    ]
    report = replay(_write_jsonl(tmp_path, scenarios))
    case = report["cases"][0]
    assert case["actual_detected"] is True, "Real incident must be detected"
    assert case["passed"] is True
    assert case["lead_time_steps"] <= 1, "Hard bar: real incident must fire within 1 detector cycle"
    assert case["lead_time_seconds"] == 45.0


def test_real_incident_error_rate_detected_within_one_cycle(tmp_path: Path):
    """A genuine error-rate spike must fire within 1 detector cycle."""
    scenarios = [
        {
            "id": "real-error",
            "scenario_kind": "real_incident",
            "description": "error spike",
            "expected_detected": True,
            "expected_severity": "high",
            "service": "product-reviews",
            "signal": "error_rate",
            "baseline_series": NORMAL_ERROR,
            "incident_series": HIGH_ERROR,
        }
    ]
    report = replay(_write_jsonl(tmp_path, scenarios))
    case = report["cases"][0]
    assert case["actual_detected"] is True
    assert case["passed"] is True
    assert case["lead_time_steps"] <= 1


def test_healthy_busy_no_false_alarm_latency(tmp_path: Path):
    """High-load but healthy: latency rises within normal deviation, no alert."""
    busy = [130.0, 145.0, 162.0, 175.0, 185.0, 190.0, 188.0, 186.0]
    scenarios = [
        {
            "id": "healthy-busy-lat",
            "scenario_kind": "healthy_busy",
            "description": "high load, still healthy",
            "expected_detected": False,
            "expected_severity": "medium",
            "service": "frontend",
            "signal": "latency",
            "baseline_series": NORMAL_LATENCY,
            "incident_series": busy,
        }
    ]
    report = replay(_write_jsonl(tmp_path, scenarios))
    case = report["cases"][0]
    assert case["actual_detected"] is False, "Busy-but-healthy must not fire"
    assert case["passed"] is True


def test_masking_hidden_incident_routed_and_detected_within_one_cycle(tmp_path: Path):
    """Noise spike on checkout does not alert, while hidden latency incident on product-reviews is caught in 1 cycle."""
    noise_error = [0.015, 0.010, 0.012, 0.009, 0.010, 0.008, 0.009, 0.008]
    scenarios = [
        {
            "id": "masking-01",
            "scenario_kind": "masking",
            "description": "noise on checkout, hidden latency on product-reviews",
            "expected_detected": False,
            "expected_severity": "medium",
            "service": "checkout",
            "signal": "error_rate",
            "baseline_series": NORMAL_ERROR,
            "incident_series": noise_error,
            "hidden_incident_service": "product-reviews",
            "hidden_incident_signal": "latency",
            "hidden_expected_detected": True,
            "hidden_expected_severity": "high",
            "hidden_baseline_series": NORMAL_LATENCY,
            "hidden_incident_series": HIGH_LATENCY,
        }
    ]
    report = replay(_write_jsonl(tmp_path, scenarios))
    case = report["cases"][0]
    assert case["actual_detected"] is False, "Checkout noise spike should not trigger incident"
    assert case["hidden_event"] is not None
    assert case["hidden_event"]["service"] == "product-reviews"
    assert case["hidden_event"]["signal"] == "latency"
    assert case["hidden_event"]["actual_detected"] is True, "Hidden latency incident must be detected"
    assert case["hidden_event"]["lead_time_steps"] <= 1, "Hidden incident must fire within 1 cycle"
    assert case["passed"] is True


# ---------------------------------------------------------------------------
# Confusion Matrix & Aggregation Tests
# ---------------------------------------------------------------------------


def test_aggregate_confusion_matrix_and_metrics():
    cases = [
        {
            "passed": True,
            "scenario_kind": "real_incident",
            "events": [{"classification": "TP", "lead_time_seconds": 45.0}],
        },
        {
            "passed": True,
            "scenario_kind": "healthy_busy",
            "events": [{"classification": "TN", "lead_time_seconds": None}],
        },
        {
            "passed": True,
            "scenario_kind": "masking",
            "events": [
                {"classification": "TN", "lead_time_seconds": None},
                {"classification": "TP", "lead_time_seconds": 45.0},
            ],
        },
    ]
    agg = _aggregate(cases, errors=[])
    assert agg["all_passed"] is True
    assert agg["events_evaluated"] == 4
    assert agg["confusion_matrix"] == {"TP": 2, "FP": 0, "FN": 0, "TN": 2}
    assert agg["precision"] == 1.0
    assert agg["recall"] == 1.0
    assert agg["avg_lead_time_seconds"] == 45.0


def test_aggregate_fails_on_errors():
    cases = [
        {
            "passed": True,
            "scenario_kind": "real_incident",
            "events": [{"classification": "TP", "lead_time_seconds": 45.0}],
        }
    ]
    errors = [{"scenario_id": "#2", "error": "ValueError"}]
    agg = _aggregate(cases, errors)
    assert agg["all_passed"] is False, "Errors present must force all_passed to False"


def test_replay_on_invalid_file_reports_error_and_fails(tmp_path: Path):
    path = tmp_path / "bad.jsonl"
    path.write_text("{not valid json}\n", encoding="utf-8")
    report = replay(path)
    assert report["aggregate"]["all_passed"] is False
    assert len(report["errors"]) > 0


# ---------------------------------------------------------------------------
# End-to-End Report Schema
# ---------------------------------------------------------------------------


def test_report_schema(tmp_path: Path):
    scenarios = [
        {
            "id": "schema-test",
            "scenario_kind": "healthy_busy",
            "description": "check report keys",
            "expected_detected": False,
            "expected_severity": "medium",
            "service": "frontend",
            "signal": "latency",
            "baseline_series": NORMAL_LATENCY,
            "incident_series": [125.0] * 8,
        }
    ]
    report = replay(_write_jsonl(tmp_path, scenarios))
    assert "schema_version" in report
    assert "generated_at" in report
    assert "aggregate" in report
    assert "cases" in report
    assert "limitations" in report
    assert "detector_config" in report
    agg = report["aggregate"]
    assert "total_cases" in agg
    assert "passed_cases" in agg
    assert "all_passed" in agg
    assert "events_evaluated" in agg
    assert "confusion_matrix" in agg
    assert "precision" in agg
    assert "recall" in agg
    assert "avg_lead_time_seconds" in agg
    assert "by_kind" in agg
