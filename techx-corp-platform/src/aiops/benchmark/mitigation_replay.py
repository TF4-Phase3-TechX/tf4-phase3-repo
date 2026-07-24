#!/usr/bin/env python3
"""External-scenario replay for the canonical Mandate-22 controller.

This deterministic harness exercises the same RemediationController used by the
service. Kubernetes and telemetry are bounded adapters so hidden scenarios can
force success, failed verification, verified rollback, or failed rollback
without mutating a cluster. It is implementation evidence, not live evidence.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.config import Settings
from app.models import Evidence, Incident
from app.remediation import RemediationController


class ReplayAdapter:
    def __init__(self) -> None:
        self.patches: list[dict[str, Any]] = []

    def previous_template(self, deployment: str):
        return ({"revision": "current"}, {"revision": "previous"})

    def patch_template(self, deployment: str, template: dict[str, Any]) -> None:
        self.patches.append(template)

    def dry_run_patch_template(
        self, deployment: str, template: dict[str, Any]
    ) -> None:
        return None

    def rollout_ready(self, deployment: str) -> bool:
        return True


class ReplayVerifier:
    def __init__(self, outcomes: list[bool]) -> None:
        self.outcomes = iter(outcomes)

    async def __call__(self, service: str) -> dict[str, Any]:
        try:
            healthy = next(self.outcomes)
        except StopIteration as exc:
            raise ValueError("Scenario did not provide enough telemetry outcomes") from exc
        return {"healthy": healthy, "source": "external_replay", "service": service}


def _load(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON at line {line_no}: {exc}") from exc
    return cases


def _validate(case: dict[str, Any]) -> None:
    required = {
        "id", "service", "expected_status", "action_health", "rollback_health"
    }
    missing = required - set(case)
    if missing:
        raise ValueError(f"Scenario {case.get('id')!r} missing {sorted(missing)}")
    if not case["action_health"]:
        raise ValueError("action_health must contain at least one telemetry poll")


async def evaluate(case: dict[str, Any]) -> dict[str, Any]:
    _validate(case)
    action_health = [bool(value) for value in case["action_health"]]
    rollback_health = [bool(value) for value in case["rollback_health"]]
    outcomes = [False, *action_health, *rollback_health]
    settings = replace(
        Settings(),
        autonomous_remediation_enabled=True,
        remediation_mode="live",
        allowed_deployments=(str(case["service"]),),
        verification_polls=len(action_health),
        rollback_verification_polls=max(len(rollback_health), 1),
        verification_interval_seconds=0,
    )
    adapter = ReplayAdapter()
    controller = RemediationController(
        settings, adapter=adapter, verifier=ReplayVerifier(outcomes)
    )
    incident = Incident(
        incident_type="service_latency_spike",
        severity="high",
        affected_service=str(case["service"]),
        confidence=float(case.get("confidence", 0.9)),
        suspected_root_cause="external replay scenario",
        evidence=[
            Evidence(
                source="external_replay",
                query=f"scenario:{case['id']}",
                window="scenario",
                value="breached",
            )
        ],
        runbook_id="deployment-latency-rollback",
        recommended_action="rollback previous ReplicaSet",
    )
    await controller.handle_incident(incident)
    actual = incident.status.value
    return {
        "id": case["id"],
        "expected_status": case["expected_status"],
        "actual_status": actual,
        "passed": actual == case["expected_status"],
        "patches": adapter.patches,
        "verification": incident.verification_result,
        "rollback_verification": incident.rollback_verification_result,
        "mutation_blocked": incident.mutation_blocked,
        "audit": [event.model_dump(mode="json") for event in incident.audit_events],
    }


async def replay(path: Path) -> dict[str, Any]:
    results = [await evaluate(case) for case in _load(path)]
    return {
        "schema_version": 1,
        "source": str(path),
        "all_passed": all(result["passed"] for result in results),
        "cases": results,
        "limitations": [
            "Uses the production controller with bounded Kubernetes/telemetry adapters.",
            "Does not replace the required in-cluster successful and forced-rollback drills.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay external Mandate-22 scenarios")
    parser.add_argument("scenarios", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.output and args.output.exists() and not args.force:
        parser.error(f"Output exists: {args.output}; pass --force")
    report = asyncio.run(replay(args.scenarios))
    if args.output:
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["all_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
