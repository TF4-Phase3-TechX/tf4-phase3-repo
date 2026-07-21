"""Tests for the Mandate-15 external-scenario replay CLI (benchmark.replay).

Covers:
- real_incident: detector fires, lead-time ≤ 1 cycle
- masking: noise spike does not hide a hidden subtle incident
- healthy_busy: no false alarm on high-load-but-healthy data
- schema validation errors
- aggregate metric computation
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
# Validation
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


# ---------------------------------------------------------------------------
# Core scenario behaviour
# ---------------------------------------------------------------------------


def test_real_incident_latency_detected(tmp_path: Path):
    """A genuine latency spike must be detected (recall = 1)."""
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
    assert case["recall_contribution"] == 1.0
    assert case["precision_contribution"] == 1.0
    # Lead-time: must fire within sustained_polls steps
    settings = Settings()
    assert case["lead_time_steps"] is not None
    assert case["lead_time_steps"] <= settings.sustained_polls + 1


def test_real_incident_error_rate_detected(tmp_path: Path):
    """A genuine error-rate spike must be detected."""
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
    assert report["cases"][0]["actual_detected"] is True
    assert report["cases"][0]["passed"] is True


def test_healthy_busy_no_false_alarm_latency(tmp_path: Path):
    """High-load but healthy: latency rises within normal deviation, no alert."""
    # Busy series: rises to ~190 ms (within 50% of 120 ms baseline)
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
    assert case["precision_contribution"] is None  # no alert, so precision is n/a
    assert case["recall_contribution"] is None     # no real incident, so recall is n/a


def test_healthy_busy_no_false_alarm_error_rate(tmp_path: Path):
    """Campaign traffic: error rate stays at baseline, no alert."""
    busy_error = [0.009, 0.010, 0.008, 0.011, 0.009, 0.010, 0.008, 0.009]
    scenarios = [
        {
            "id": "healthy-busy-err",
            "scenario_kind": "healthy_busy",
            "description": "high rps, errors fine",
            "expected_detected": False,
            "expected_severity": "medium",
            "service": "checkout",
            "signal": "error_rate",
            "baseline_series": NORMAL_ERROR,
            "incident_series": busy_error,
        }
    ]
    report = replay(_write_jsonl(tmp_path, scenarios))
    assert report["cases"][0]["actual_detected"] is False
    assert report["cases"][0]["passed"] is True


def test_masking_hidden_incident_found(tmp_path: Path):
    """Noise spike on checkout must not mask subtle hidden incident on product-reviews."""
    # Main signal: transient noise spike (not a real incident on checkout)
    noise_error = [0.065, 0.080, 0.060, 0.055, 0.010, 0.009, 0.008, 0.009]
    # Hidden: real, sustained latency degradation on product-reviews
    hidden_lat = NORMAL_LATENCY + [240.0, 380.0, 520.0, 680.0, 1100.0, 1200.0, 1300.0, 1400.0]

    scenarios = [
        {
            "id": "masking-01",
            "scenario_kind": "masking",
            "description": "noise masks hidden incident",
            "expected_detected": False,  # checkout spike should self-resolve
            "expected_severity": "medium",
            "service": "checkout",
            "signal": "error_rate",
            "baseline_series": NORMAL_ERROR,
            "incident_series": noise_error,
            "hidden_incident_series": hidden_lat,
        }
    ]
    report = replay(_write_jsonl(tmp_path, scenarios))
    case = report["cases"][0]
    # The hidden incident series (latency) must have been detected independently.
    assert case["hidden_incident_detected"] is True, (
        "Hidden subtle incident must not be masked by the noise spike"
    )


# ---------------------------------------------------------------------------
# Aggregate metrics
# ---------------------------------------------------------------------------


def test_aggregate_all_pass():
    cases = [
        {
            "passed": True,
            "scenario_kind": "real_incident",
            "precision_contribution": 1.0,
            "recall_contribution": 1.0,
            "lead_time_seconds": 45.0,
        },
        {
            "passed": True,
            "scenario_kind": "healthy_busy",
            "precision_contribution": None,
            "recall_contribution": None,
            "lead_time_seconds": None,
        },
    ]
    agg = _aggregate(cases)
    assert agg["all_passed"] is True
    assert agg["precision"] == 1.0
    assert agg["recall"] == 1.0
    assert agg["avg_lead_time_seconds"] == 45.0


def test_aggregate_false_alarm_reduces_precision():
    cases = [
        {
            "passed": False,
            "scenario_kind": "healthy_busy",
            "precision_contribution": 0.0,  # false alarm
            "recall_contribution": None,
            "lead_time_seconds": None,
        },
        {
            "passed": True,
            "scenario_kind": "real_incident",
            "precision_contribution": 1.0,
            "recall_contribution": 1.0,
            "lead_time_seconds": 90.0,
        },
    ]
    agg = _aggregate(cases)
    assert agg["precision"] == 0.5  # (0 + 1) / 2
    assert agg["all_passed"] is False


# ---------------------------------------------------------------------------
# Load scenarios
# ---------------------------------------------------------------------------


def test_load_scenarios_empty_lines(tmp_path: Path):
    path = tmp_path / "s.jsonl"
    path.write_text(
        textwrap.dedent("""\
            {"id": "a", "scenario_kind": "real_incident"}

            {"id": "b", "scenario_kind": "healthy_busy"}
        """),
        encoding="utf-8",
    )
    scenarios = _load_scenarios(path)
    assert len(scenarios) == 2
    assert scenarios[0]["id"] == "a"


def test_load_scenarios_bad_json(tmp_path: Path):
    path = tmp_path / "bad.jsonl"
    path.write_text("{not valid json}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON parse error at line 1"):
        _load_scenarios(path)


# ---------------------------------------------------------------------------
# End-to-end report shape
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
    assert "precision" in agg
    assert "recall" in agg
    assert "avg_lead_time_seconds" in agg
    assert "by_kind" in agg
