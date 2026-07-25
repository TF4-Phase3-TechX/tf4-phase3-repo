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
    normalized = [
        dict(s, sample_interval_seconds=s.get("sample_interval_seconds", 15))
        for s in scenarios
    ]
    path.write_text("\n".join(json.dumps(s) for s in normalized), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Validation Tests
# ---------------------------------------------------------------------------


def test_validate_scenario_ok():
    scenario = {
        "id": "test-01",
        "schema_version": 1,
        "sample_interval_seconds": 15,
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
        "sample_interval_seconds": 15,
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
        "sample_interval_seconds": 15,
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
        "sample_interval_seconds": 15,
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


@pytest.mark.parametrize(
    ("signal", "series", "message"),
    [
        ("error_rate", [1.01], "between 0 and 1"),
        ("llm_error", [-0.01], "between 0 and 1"),
        ("latency", [-1.0], "must be >= 0"),
    ],
)
def test_validate_scenario_rejects_out_of_range_values(signal, series, message):
    scenario = {
        "id": f"bad-range-{signal}",
        "schema_version": 1,
        "sample_interval_seconds": 15,
        "scenario_kind": "real_incident",
        "description": "bad range",
        "expected_detected": True,
        "expected_severity": "high",
        "service": "frontend",
        "signal": signal,
        "baseline_series": [0.01] if signal != "latency" else [100.0],
        "incident_series": series,
    }
    with pytest.raises(ValueError, match=message):
        _validate_scenario(scenario, 1, set())


def test_validate_scenario_requires_severity_for_expected_incident():
    scenario = {
        "id": "missing-severity",
        "schema_version": 1,
        "sample_interval_seconds": 15,
        "scenario_kind": "real_incident",
        "description": "missing severity",
        "expected_detected": True,
        "expected_severity": None,
        "service": "frontend",
        "signal": "latency",
        "baseline_series": NORMAL_LATENCY,
        "incident_series": HIGH_LATENCY,
    }
    with pytest.raises(ValueError, match="expected_severity is required"):
        _validate_scenario(scenario, 1, set())


def test_replay_rejects_non_object_json_without_crashing(tmp_path: Path):
    path = tmp_path / "non-object.jsonl"
    path.write_text("[]\n", encoding="utf-8")
    report = replay(path)
    assert report["aggregate"]["all_passed"] is False
    assert "must be a JSON object" in report["errors"][0]["error"]


def test_replay_rejects_ambiguous_sample_to_poll_mapping(tmp_path: Path):
    scenario = {
        "id": "ambiguous-cadence",
        "schema_version": 1,
        "sample_interval_seconds": 20,
        "scenario_kind": "real_incident",
        "description": "45 second poll cannot contain an integer number of 20 second samples",
        "expected_detected": True,
        "expected_severity": "high",
        "service": "frontend",
        "signal": "latency",
        "baseline_series": NORMAL_LATENCY,
        "incident_series": HIGH_LATENCY,
    }
    report = replay(_write_jsonl(tmp_path, [scenario]))
    assert report["aggregate"]["all_passed"] is False
    assert "must divide poll_seconds exactly" in report["errors"][0]["error"]


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


def test_masking_noise_in_target_window_does_not_hide_subtle_incident(tmp_path: Path):
    """An isolated 20% sample is rejected and cannot inflate the target's 4% baseline."""
    normal = [0.04] * 30
    noisy_target_history = [*normal[:-2], 0.20, 0.04]
    scenarios = [
        {
            "id": "masking-01",
            "schema_version": 1,
            "scenario_kind": "masking",
            "description": "transient noise and subtle incident on the same service/signal window",
            "expected_detected": False,
            "expected_severity": "medium",
            "service": "checkout",
            "signal": "error_rate",
            "baseline_series": normal,
            "incident_series": [0.20, 0.04, 0.04],
            "hidden_incident_service": "checkout",
            "hidden_incident_signal": "error_rate",
            "hidden_expected_detected": True,
            "hidden_expected_severity": "medium",
            "hidden_baseline_series": noisy_target_history,
            "hidden_incident_series": [0.062, 0.064, 0.063],
        }
    ]
    report = replay(_write_jsonl(tmp_path, scenarios))
    case = report["cases"][0]
    assert case["actual_detected"] is False, "A single above-floor spike must not trigger an incident"
    assert case["hidden_event"] is not None
    assert case["hidden_event"]["service"] == "checkout"
    assert case["hidden_event"]["signal"] == "error_rate"
    assert case["hidden_event"]["actual_detected"] is True, "Subtle incident must survive the noisy baseline"
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


# ---------------------------------------------------------------------------
# Safety Floor Regression — no FP even when ratio gate fires
# ---------------------------------------------------------------------------


def test_transient_above_floor_no_false_alarm(tmp_path: Path):
    """One 20% scrape sample must not page even though it exceeds every acute gate."""
    noise_baseline = [0.04] * 30
    noise_spike = [0.20, 0.04, 0.04]
    scenarios = [
        {
            "id": "floor-guard-01",
            "schema_version": 1,
            "scenario_kind": "healthy_busy",
            "description": "one above-floor scrape spike followed by recovery",
            "expected_detected": False,
            "expected_severity": "medium",
            "service": "checkout",
            "signal": "error_rate",
            "baseline_series": noise_baseline,
            "incident_series": noise_spike,
        }
    ]
    report = replay(_write_jsonl(tmp_path, scenarios))
    case = report["cases"][0]
    assert case["actual_detected"] is False, (
        "Within-poll confirmation must block a single above-floor scrape spike"
    )
    assert case["passed"] is True


# ---------------------------------------------------------------------------
# Incident Summary Validation
# ---------------------------------------------------------------------------


def test_incident_summary_contains_service_severity_runbook(tmp_path: Path):
    """Incident summary rendered by IncidentSummaryGenerator must contain the
    affected service name, severity label, and runbook identifier so the BTC
    hidden-set replay artifact is auditable.
    """
    scenarios = [
        {
            "id": "summary-check-01",
            "schema_version": 1,
            "scenario_kind": "real_incident",
            "description": "high-confidence latency spike — validate summary artifact",
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
    assert case["actual_detected"] is True
    summary = case["incident_summary"]
    assert summary is not None, "Detected incident must include an incident_summary"
    # Service name must appear in the summary so the responder knows which service to act on
    assert "frontend" in summary, "Summary must name the affected service"
    # Severity label must be present
    assert "high" in summary.lower(), "Summary must include the severity"
    # Runbook identifier must be present for on-call routing
    assert case["runbook_id"] in summary, "Summary must embed the runbook_id"

