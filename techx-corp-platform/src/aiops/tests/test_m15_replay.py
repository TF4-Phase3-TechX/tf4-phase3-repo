"""Tests for the Mandate-15 external-scenario replay CLI (benchmark.replay).

Covers:
- real_incident: detector fires within 1 detector cycle (lead_time_steps <= 1, 45s)
- masking: noise spike on main service doesn't trigger, while hidden target service/signal incident is caught within 1 cycle
- healthy_busy: no false alarm on high-load-but-healthy data
- event-level confusion matrix (TP, FP, FN, TN) and precision/recall
- schema validation errors & scenario parsing errors enforce all_passed = False and non-zero exit code
- testing committed JSONL dataset directly
- incident summary rendering in replay output
"""
from __future__ import annotations

import json
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
        "schema_version": 1,
        "scenario_kind": "real_incident",
        "description": "ok",
        "expected_detected": True,
        "expected_severity": "high",
        "service": "frontend",
        "signal": "latency",
        "baseline_series": NORMAL_LATENCY,
        "incident_series": HIGH_LATENCY,
    }
    _validate_scenario(scenario, 1, set())  # must not raise


def test_validate_scenario_bad_schema_version():
    scenario = {
        "id": "test-v2",
        "schema_version": 2,
        "scenario_kind": "real_incident",
        "description": "bad version",
        "expected_detected": True,
        "expected_severity": "high",
        "service": "frontend",
        "signal": "latency",
        "baseline_series": NORMAL_LATENCY,
        "incident_series": HIGH_LATENCY,
    }
    with pytest.raises(ValueError, match="schema_version must be 1"):
        _validate_scenario(scenario, 1, set())


def test_validate_scenario_non_bool_expected_detected():
    scenario = {
        "id": "test-non-bool",
        "schema_version": 1,
        "scenario_kind": "real_incident",
        "description": "non bool flag",
        "expected_detected": "true",  # string instead of boolean
        "expected_severity": "high",
        "service": "frontend",
        "signal": "latency",
        "baseline_series": NORMAL_LATENCY,
        "incident_series": HIGH_LATENCY,
    }
    with pytest.raises(ValueError, match="expected_detected' must be a boolean"):
        _validate_scenario(scenario, 1, set())


def test_validate_scenario_duplicate_id():
    scenario = {
        "id": "dup-id",
        "schema_version": 1,
        "scenario_kind": "real_incident",
        "description": "dup",
        "expected_detected": True,
        "expected_severity": "high",
        "service": "frontend",
        "signal": "latency",
        "baseline_series": NORMAL_LATENCY,
        "incident_series": HIGH_LATENCY,
    }
    seen = {"dup-id"}
    with pytest.raises(ValueError, match="duplicate scenario id"):
        _validate_scenario(scenario, 2, seen)


def test_validate_scenario_unsupported_signal():
    scenario = {
        "id": "bad_signal",
        "schema_version": 1,
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
        _validate_scenario(scenario, 1, set())


# ---------------------------------------------------------------------------
# Core Scenario Behavior & 1 Detector Cycle Hard Bar Tests
# ---------------------------------------------------------------------------


def test_real_incident_latency_detected_within_one_detector_cycle(tmp_path: Path):
    """A genuine acute latency spike must fire within 1 detector cycle (lead_time_steps <= 1, 45s)."""
    scenarios = [
        {
            "id": "real-latency",
            "schema_version": 1,
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
    assert case["incident_summary"] is not None
    assert "AIOps Incident" in case["incident_summary"]


def test_healthy_busy_high_baseline_no_false_alarm(tmp_path: Path):
    """High-baseline service (1800ms) with moderate traffic rise remains healthy (ratio < 1.5x)."""
    high_base = [1800.0] * 30
    busy = [1850.0, 1900.0, 1920.0, 1950.0, 1980.0, 1960.0]
    scenarios = [
        {
            "id": "healthy-busy-high-base",
            "schema_version": 1,
            "scenario_kind": "healthy_busy",
            "description": "high baseline service, traffic rise is normal relative to baseline",
            "expected_detected": False,
            "expected_severity": "medium",
            "service": "product-catalog",
            "signal": "latency",
            "baseline_series": high_base,
            "incident_series": busy,
        }
    ]
    report = replay(_write_jsonl(tmp_path, scenarios))
    case = report["cases"][0]
    assert case["actual_detected"] is False, "Relative normal baseline must not fire false alarm"
    assert case["passed"] is True


def test_masking_hidden_incident_routed_and_detected_within_one_cycle(tmp_path: Path):
    """Noise spike on checkout error rate is below floor, while hidden latency incident on product-reviews is caught in 1 cycle."""
    noise_error = [0.015, 0.010, 0.012, 0.009, 0.010, 0.008, 0.009, 0.008]
    scenarios = [
        {
            "id": "masking-01",
            "schema_version": 1,
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
            "hidden_expected_severity": "medium",
            "hidden_baseline_series": NORMAL_LATENCY,
            "hidden_incident_series": [1100.0, 1150.0, 1180.0, 1220.0],
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
# Test Actual Committed Dataset File
# ---------------------------------------------------------------------------


def test_committed_labeled_scenarios_dataset_passes():
    """Verify that the committed docs/aio1/mandate-15/labeled-scenarios-v1.jsonl dataset passes 5/5."""
    dataset_path = (
        Path(__file__).resolve().parents[4]
        / "docs"
        / "aio1"
        / "mandate-15"
        / "labeled-scenarios-v1.jsonl"
    )
    assert dataset_path.exists(), f"Committed dataset not found at {dataset_path}"
    report = replay(dataset_path)
    agg = report["aggregate"]
    assert agg["total_cases"] == 5
    assert agg["passed_cases"] == 5
    assert agg["all_passed"] is True
    assert agg["precision"] == 1.0
    assert agg["recall"] == 1.0
    assert agg["avg_lead_time_seconds"] == 45.0


# ---------------------------------------------------------------------------
# Confusion Matrix & Zero Denominator Tests
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
    ]
    agg = _aggregate(cases, errors=[])
    assert agg["all_passed"] is True
    assert agg["events_evaluated"] == 2
    assert agg["confusion_matrix"] == {"TP": 1, "FP": 0, "FN": 0, "TN": 1}
    assert agg["precision"] == 1.0
    assert agg["recall"] == 1.0
    assert agg["avg_lead_time_seconds"] == 45.0


def test_aggregate_handles_zero_denominator_gracefully():
    cases = [
        {
            "passed": True,
            "scenario_kind": "healthy_busy",
            "events": [{"classification": "TN", "lead_time_seconds": None}],
        }
    ]
    agg = _aggregate(cases, errors=[])
    assert agg["precision"] is None
    assert agg["recall"] is None
    assert agg["avg_lead_time_seconds"] is None
