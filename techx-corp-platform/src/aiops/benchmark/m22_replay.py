#!/usr/bin/env python3
"""Mandate-22 closed-loop mitigation replay entry point.

Accepts an external JSONL labeled scenario file and simulates the full
autonomous remediation pipeline: policy gate → action → verify → rollback/escalate.
Produces a structured JSON report with per-case audit chains and aggregate
MTTR/metrics, matching the format expected on grading day.

Usage (one-command repro from techx-corp-platform/src/aiops):
    cd techx-corp-platform/src/aiops
    .venv/bin/python -m benchmark.m22_replay \\
      ../../../docs/aio1/mandate-22/labeled-scenarios-v1.jsonl \\
      --output /tmp/m22-replay-report.json

On grading day, BTC supplies a hidden scenario file:
    .venv/bin/python -m benchmark.m22_replay <hidden-scenarios.jsonl>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

try:
    from app.config import Settings
    from app.models import Incident, IncidentStatus
    from app.remediation import AUTONOMOUS_INCIDENT_TYPES, RemediationController
    from app.runbooks import RunbookCatalog
except ImportError:
    _src = Path(__file__).resolve().parents[1]
    if str(_src) not in sys.path:
        sys.path.insert(0, str(_src))
    from app.config import Settings
    from app.models import Incident, IncidentStatus
    from app.remediation import AUTONOMOUS_INCIDENT_TYPES, RemediationController
    from app.runbooks import RunbookCatalog


SCHEMA_VERSION = 1
ALLOWED_KINDS = {"successful_mitigation", "forced_wrong_rollback", "policy_denied"}
ALLOWED_STATUSES = {s.value for s in IncidentStatus}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Fake adapters for offline simulation
# ---------------------------------------------------------------------------


class _FakeAdapter:
    """Simulates Kubernetes rollback adapter for offline replay."""

    def __init__(self, rollout_ready: bool = True):
        self._rollout_ready = rollout_ready
        self.patches: list[dict[str, Any]] = []

    def previous_template(self, deployment: str) -> tuple[dict[str, Any], dict[str, Any]]:
        current = {"metadata": {"labels": {"version": "current"}}, "spec": {"containers": [{"image": "app:v2"}]}}
        previous = {"metadata": {"labels": {"version": "previous"}}, "spec": {"containers": [{"image": "app:v1"}]}}
        return current, previous

    def patch_template(self, deployment: str, template: dict[str, Any]) -> None:
        self.patches.append(template)

    def rollout_ready(self, deployment: str) -> bool:
        return self._rollout_ready


# ---------------------------------------------------------------------------
# Scenario loading and validation
# ---------------------------------------------------------------------------


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
        raise ValueError(f"No valid scenarios found in: {path}")
    return scenarios


def _validate_scenario(scenario: dict[str, Any], index: int, seen_ids: set[str]) -> None:
    sc_id = scenario.get("id")
    if not sc_id or not isinstance(sc_id, str):
        raise ValueError(f"Scenario #{index}: 'id' must be a non-empty string")
    if sc_id in seen_ids:
        raise ValueError(f"Scenario #{index}: duplicate scenario id {sc_id!r}")
    seen_ids.add(sc_id)

    if scenario.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Scenario #{index} ({sc_id!r}): schema_version must be {SCHEMA_VERSION}")

    required = {"id", "schema_version", "scenario_kind", "incident_type", "service",
                "confidence", "expected_final_status"}
    missing = required - set(scenario)
    if missing:
        raise ValueError(f"Scenario #{index} ({sc_id!r}): missing fields {sorted(missing)}")

    kind = scenario["scenario_kind"]
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"Scenario #{index} ({sc_id!r}): unknown scenario_kind {kind!r}; allowed: {sorted(ALLOWED_KINDS)}")

    if not isinstance(scenario["confidence"], (int, float)):
        raise ValueError(f"Scenario #{index} ({sc_id!r}): 'confidence' must be numeric")

    exp = scenario["expected_final_status"]
    if exp not in ALLOWED_STATUSES:
        raise ValueError(f"Scenario #{index} ({sc_id!r}): unknown expected_final_status {exp!r}")


# ---------------------------------------------------------------------------
# Scenario evaluation
# ---------------------------------------------------------------------------


async def _evaluate_scenario(
    scenario: dict[str, Any],
    settings: Settings,
    controller: RemediationController,
) -> dict[str, Any]:
    sc_id = scenario["id"]
    kind = scenario["scenario_kind"]
    incident_type = scenario["incident_type"]
    service = scenario["service"]
    confidence = float(scenario["confidence"])
    expected_status = scenario["expected_final_status"]

    runbook_id = "deployment-latency-rollback" if incident_type == "service_latency_spike" else "observe-and-escalate"
    recommended_action = "rollback" if incident_type == "service_latency_spike" else "escalate"

    # Determine rollout/SLO behavior based on scenario kind
    if kind == "forced_wrong_rollback":
        # Rollout succeeds but SLO unhealthy → triggers rollback path
        rollout_ready = True
        slo_healthy = False
    else:
        rollout_ready = True
        slo_healthy = True

    adapter = _FakeAdapter(rollout_ready=rollout_ready)
    slo_h = slo_healthy

    async def verifier(svc: str) -> dict[str, Any]:
        return {"healthy": slo_h, "latency_ok": slo_h, "error_rate_ok": slo_h}

    # Build a per-scenario controller to avoid cooldown cross-contamination,
    # but share the same settings so policy is consistent.
    sc_controller = RemediationController(
        settings=settings,
        adapter=adapter,
        verifier=verifier,
    )

    incident = Incident(
        incident_type=incident_type,
        severity="high",
        affected_service=service,
        environment=settings.environment,
        tenant_id=settings.tenant_id,
        confidence=confidence,
        suspected_root_cause=f"Replay scenario {sc_id}",
        runbook_id=runbook_id,
        recommended_action=recommended_action,
    )

    t_start = datetime.now(timezone.utc)
    await sc_controller.autonomous_execute(incident)
    t_end = datetime.now(timezone.utc)

    elapsed_seconds = (t_end - t_start).total_seconds()
    actual_status = incident.status.value
    passed = actual_status == expected_status

    audit_events = [
        {"at": e.at.isoformat(), "event": e.event, "detail": e.detail}
        for e in incident.audit_events
    ]

    return {
        "scenario_id": sc_id,
        "scenario_kind": kind,
        "service": service,
        "incident_type": incident_type,
        "confidence": confidence,
        "expected_final_status": expected_status,
        "actual_final_status": actual_status,
        "auto_approved": incident.auto_approved,
        "execution_attempts": incident.execution_attempts,
        "verification_result": incident.verification_result,
        "rollback_result": incident.rollback_result,
        "escalation_reason": incident.escalation_reason,
        "audit_chain": audit_events,
        "patches_applied": len(adapter.patches),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "passed": passed,
    }


def _aggregate(cases: list[dict[str, Any]], errors: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(cases)
    passed = sum(1 for c in cases if c["passed"])
    all_passed = (total > 0) and (passed == total) and (len(errors) == 0)

    resolved_times = [
        c["elapsed_seconds"]
        for c in cases
        if c["scenario_kind"] == "successful_mitigation" and c["actual_final_status"] == "resolved"
    ]
    rollback_cases = [c for c in cases if c.get("rollback_result")]
    rollback_success = sum(
        1 for c in rollback_cases
        if c.get("rollback_result", {}).get("restored_original_template") is True
    )

    by_kind: dict[str, dict[str, int]] = {}
    for kind in sorted(ALLOWED_KINDS):
        subset = [c for c in cases if c["scenario_kind"] == kind]
        by_kind[kind] = {"count": len(subset), "passed": sum(1 for c in subset if c["passed"])}

    return {
        "total_cases": total,
        "passed_cases": passed,
        "all_passed": all_passed,
        "avg_simulated_mttr_seconds": round(mean(resolved_times), 3) if resolved_times else None,
        "rollback_cases": len(rollback_cases),
        "rollback_success": rollback_success,
        "by_kind": by_kind,
    }


async def _replay_async(scenarios_path: Path, *, settings: Settings) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    try:
        raw = _load_scenarios(scenarios_path)
    except Exception as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": _utc_now(),
            "scenarios_file": str(scenarios_path),
            "aggregate": {"total_cases": 0, "passed_cases": 0, "all_passed": False},
            "cases": [],
            "errors": [{"scenario_id": "load_error", "error": f"{type(exc).__name__}: {exc}"}],
        }

    # Shared settings; per-scenario controller used to isolate state
    for i, scenario in enumerate(raw, 1):
        sc_id = scenario.get("id", f"#{i}")
        try:
            _validate_scenario(scenario, i, seen_ids)
            result = await _evaluate_scenario(scenario, settings, controller=None)
            results.append(result)
            status = "PASS" if result["passed"] else "FAIL"
            print(
                f"[{i}/{len(raw)}] {sc_id} ({scenario['scenario_kind']}): {status}"
                f"  final={result['actual_final_status']}"
                f"  auto_approved={result['auto_approved']}",
                flush=True,
            )
        except Exception as exc:
            errors.append({"scenario_id": sc_id, "error": f"{type(exc).__name__}: {exc}"})
            print(f"[{i}/{len(raw)}] {sc_id}: ERROR {exc}", flush=True)

    aggregate = _aggregate(results, errors)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "scenarios_file": str(scenarios_path),
        "detector_config": {
            "remediation_mode": settings.remediation_mode,
            "remediation_confidence_threshold": settings.remediation_confidence_threshold,
            "allowed_deployments": list(settings.allowed_deployments),
            "cooldown_seconds": settings.cooldown_seconds,
        },
        "aggregate": aggregate,
        "cases": results,
        "errors": errors,
        "limitations": [
            "This replay uses simulated Kubernetes adapter and SLO verifier — not live cluster.",
            "elapsed_seconds is wall-clock time for offline simulation, not live MTTR.",
            "Cooldown and blast-radius are enforced per-scenario-controller (isolated state).",
        ],
    }


def replay(scenarios_path: Path, *, settings: Settings | None = None) -> dict[str, Any]:
    """Run all scenarios and return the full report dict (sync wrapper)."""
    settings = settings or Settings()
    return asyncio.run(_replay_async(scenarios_path, settings=settings))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mandate-22 closed-loop mitigation replay — deterministic offline evaluation"
    )
    parser.add_argument(
        "scenarios",
        type=Path,
        help="Path to a JSONL file with labeled mitigation scenarios",
    )
    parser.add_argument("--output", type=Path, default=None, help="Write JSON report to this path")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output file")
    args = parser.parse_args()

    if not args.scenarios.exists():
        parser.error(f"Scenarios file not found: {args.scenarios}")
    if args.output and args.output.exists() and not args.force:
        parser.error(f"Output file exists: {args.output}. Pass --force to overwrite.")

    report = replay(args.scenarios)
    agg = report["aggregate"]

    print(
        f"\n{'='*60}\n"
        f"MANDATE-22 REPLAY RESULT\n"
        f"  Total cases        : {agg['total_cases']}\n"
        f"  Passed             : {agg['passed_cases']} / {agg['total_cases']}\n"
        f"  All passed         : {agg['all_passed']}\n"
        f"  Avg sim MTTR       : {agg['avg_simulated_mttr_seconds']}s\n"
        f"  Rollback cases     : {agg['rollback_cases']} / success: {agg['rollback_success']}\n"
        f"  Errors             : {len(report['errors'])}\n"
        f"{'='*60}"
    )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report written to: {args.output}")

    return 0 if (agg["all_passed"] and len(report["errors"]) == 0) else 2


if __name__ == "__main__":
    raise SystemExit(main())
