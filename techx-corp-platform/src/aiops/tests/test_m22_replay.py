"""Tests for the Mandate-22 closed-loop mitigation replay harness (benchmark/m22_replay.py).

Covers schema validation, per-scenario outcomes (success, rollback, policy denied),
aggregate metric computation, and full committed dataset pass.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.config import Settings
from benchmark.m22_replay import (
    _aggregate,
    _load_scenarios,
    _validate_scenario,
    replay,
)

# Path to the committed scenario dataset
COMMITTED_SCENARIOS = (
    Path(__file__).resolve().parents[4]
    / "docs/aio1/mandate-22/labeled-scenarios-v1.jsonl"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_jsonl(tmp_path: Path, scenarios: list[dict]) -> Path:
    p = tmp_path / "scenarios.jsonl"
    p.write_text("\n".join(json.dumps(s) for s in scenarios), encoding="utf-8")
    return p


def _live_settings() -> Settings:
    return replace(Settings(), remediation_mode="live")


def _base_scenario(**kwargs) -> dict:
    return {
        "id": "test-01",
        "schema_version": 1,
        "scenario_kind": "successful_mitigation",
        "incident_type": "service_latency_spike",
        "service": "product-reviews",
        "confidence": 0.92,
        "expected_final_status": "resolved",
        **kwargs,
    }


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


def test_validate_scenario_ok():
    seen: set[str] = set()
    _validate_scenario(_base_scenario(), 1, seen)  # should not raise
    assert "test-01" in seen


def test_validate_scenario_bad_schema_version():
    seen: set[str] = set()
    with pytest.raises(ValueError, match="schema_version"):
        _validate_scenario(_base_scenario(schema_version=2), 1, seen)


def test_validate_scenario_duplicate_id():
    seen = {"test-01"}
    with pytest.raises(ValueError, match="duplicate"):
        _validate_scenario(_base_scenario(), 1, seen)


def test_validate_scenario_unknown_kind():
    seen: set[str] = set()
    with pytest.raises(ValueError, match="unknown scenario_kind"):
        _validate_scenario(_base_scenario(scenario_kind="magic_auto_fix"), 1, seen)


def test_validate_scenario_missing_field():
    seen: set[str] = set()
    bad = {k: v for k, v in _base_scenario().items() if k != "confidence"}
    with pytest.raises(ValueError, match="missing fields"):
        _validate_scenario(bad, 1, seen)


def test_validate_scenario_unknown_expected_status():
    seen: set[str] = set()
    with pytest.raises(ValueError, match="unknown expected_final_status"):
        _validate_scenario(_base_scenario(expected_final_status="cosmic_resolved"), 1, seen)


# ---------------------------------------------------------------------------
# Per-scenario outcome tests
# ---------------------------------------------------------------------------


def test_successful_mitigation_resolves(tmp_path: Path):
    """successful_mitigation + allowlisted service + high confidence → resolved."""
    scenarios = [_base_scenario(id="succ-01", expected_final_status="resolved")]
    report = replay(_write_jsonl(tmp_path, scenarios), settings=_live_settings())
    case = report["cases"][0]
    assert case["passed"] is True
    assert case["actual_final_status"] == "resolved"
    assert case["auto_approved"] is True
    # Audit chain must contain the approval and verification events
    events = [e["event"] for e in case["audit_chain"]]
    assert "autonomous_policy_approved" in events
    assert "autonomous_remediation_verified" in events


def test_forced_wrong_rollback_triggers_rollback(tmp_path: Path):
    """forced_wrong_rollback → SLO unhealthy → rolled_back + original template restored."""
    scenarios = [
        _base_scenario(
            id="rollback-01",
            scenario_kind="forced_wrong_rollback",
            confidence=0.88,
            expected_final_status="rolled_back",
        )
    ]
    report = replay(_write_jsonl(tmp_path, scenarios), settings=_live_settings())
    case = report["cases"][0]
    assert case["passed"] is True
    assert case["actual_final_status"] == "rolled_back"
    assert case["rollback_result"]["restored_original_template"] is True
    assert case["patches_applied"] == 2  # rollback + restore
    events = [e["event"] for e in case["audit_chain"]]
    assert "autonomous_remediation_rolled_back" in events


def test_policy_denied_low_confidence_escalates(tmp_path: Path):
    """policy_denied: confidence below threshold → escalated + not auto_approved."""
    scenarios = [
        _base_scenario(
            id="denied-01",
            scenario_kind="policy_denied",
            confidence=0.40,
            expected_final_status="escalated",
        )
    ]
    report = replay(_write_jsonl(tmp_path, scenarios), settings=_live_settings())
    case = report["cases"][0]
    assert case["passed"] is True
    assert case["actual_final_status"] == "escalated"
    assert case["auto_approved"] is False
    events = [e["event"] for e in case["audit_chain"]]
    assert "autonomous_policy_denied" in events


def test_non_autonomous_incident_type_denied(tmp_path: Path):
    """Incident type not in AUTONOMOUS_INCIDENT_TYPES must be denied by policy gate."""
    scenarios = [
        _base_scenario(
            id="denied-type-01",
            scenario_kind="policy_denied",
            incident_type="service_error_rate_spike",
            confidence=0.92,
            expected_final_status="escalated",
        )
    ]
    report = replay(_write_jsonl(tmp_path, scenarios), settings=_live_settings())
    case = report["cases"][0]
    assert case["passed"] is True
    assert case["actual_final_status"] == "escalated"
    assert case["auto_approved"] is False


def test_audit_chain_contains_full_trigger_to_verify_sequence(tmp_path: Path):
    """Audit chain must reconstruct trigger → policy decision → execution → verify."""
    scenarios = [_base_scenario(id="chain-01", expected_final_status="resolved")]
    report = replay(_write_jsonl(tmp_path, scenarios), settings=_live_settings())
    events = [e["event"] for e in report["cases"][0]["audit_chain"]]
    assert "autonomous_policy_approved" in events
    assert "autonomous_execution_started" in events
    assert "autonomous_remediation_verified" in events


# ---------------------------------------------------------------------------
# Aggregate metric tests
# ---------------------------------------------------------------------------


def test_aggregate_all_passed_true_when_no_errors():
    cases = [
        {"passed": True, "scenario_kind": "successful_mitigation", "actual_final_status": "resolved",
         "elapsed_seconds": 0.5, "rollback_result": None},
        {"passed": True, "scenario_kind": "forced_wrong_rollback", "actual_final_status": "rolled_back",
         "elapsed_seconds": 0.3, "rollback_result": {"restored_original_template": True}},
    ]
    agg = _aggregate(cases, errors=[])
    assert agg["all_passed"] is True
    assert agg["total_cases"] == 2
    assert agg["passed_cases"] == 2
    assert agg["rollback_cases"] == 1
    assert agg["rollback_success"] == 1


def test_aggregate_mttr_only_for_resolved_mitigation():
    cases = [
        {"passed": True, "scenario_kind": "successful_mitigation", "actual_final_status": "resolved",
         "elapsed_seconds": 1.0, "rollback_result": None},
        {"passed": True, "scenario_kind": "forced_wrong_rollback", "actual_final_status": "rolled_back",
         "elapsed_seconds": 2.0, "rollback_result": {"restored_original_template": True}},
    ]
    agg = _aggregate(cases, errors=[])
    # Only the resolved case contributes to avg MTTR
    assert agg["avg_simulated_mttr_seconds"] == 1.0


def test_aggregate_all_passed_false_on_errors():
    cases = [{"passed": True, "scenario_kind": "successful_mitigation",
              "actual_final_status": "resolved", "elapsed_seconds": 0.1, "rollback_result": None}]
    agg = _aggregate(cases, errors=[{"scenario_id": "x", "error": "oops"}])
    assert agg["all_passed"] is False


# ---------------------------------------------------------------------------
# Committed dataset end-to-end test
# ---------------------------------------------------------------------------


def test_committed_labeled_scenarios_all_pass():
    """The committed docs/aio1/mandate-22/labeled-scenarios-v1.jsonl must pass 3/3."""
    assert COMMITTED_SCENARIOS.exists(), f"Dataset not found: {COMMITTED_SCENARIOS}"
    report = replay(COMMITTED_SCENARIOS, settings=_live_settings())
    agg = report["aggregate"]
    assert agg["total_cases"] == 3, f"Expected 3 scenarios, got {agg['total_cases']}"
    assert agg["passed_cases"] == agg["total_cases"], (
        f"Not all scenarios passed: {agg['passed_cases']}/{agg['total_cases']}\n"
        + json.dumps(report["cases"], indent=2)
    )
    assert agg["all_passed"] is True
    # At least one rollback must succeed (forced_wrong_rollback scenario)
    assert agg["rollback_success"] >= 1
