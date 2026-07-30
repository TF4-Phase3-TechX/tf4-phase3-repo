#!/usr/bin/env python3
"""Replay schema-V2 restart decisions without Git or cluster writes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.saga import (
    GitTransaction,
    RemediationSaga,
    SagaOutcome,
    SagaPhase,
    decide_restart_action,
)


def transaction(case: dict) -> GitTransaction:
    kind = case.get("transaction_kind", "remediation")
    return GitTransaction(
        kind=kind,
        branch=f"aiops/{kind}/{case['incident_id']}",
        base_sha="a" * 40,
        known_good_sha="b" * 40,
        target_file="environments/production/app-values.yaml",
        before_hash="c" * 64,
        after_hash="d" * 64,
        pr_number=1 if case.get("pr_exists", True) else None,
        merge_sha="e" * 40 if case.get("merged") else None,
    )


def run_case(case: dict) -> dict:
    saga = RemediationSaga(
        schema_version=int(case.get("schema_version", 2)),
        saga_id=f"saga-{case['case_id']}",
        incident_id=case["incident_id"],
        target="product-reviews",
        phase=SagaPhase(case["phase"]),
        outcome=SagaOutcome(case.get("outcome", "none")),
        remediation=transaction(case) if case.get("has_transaction") else None,
        mutation_blocked=bool(case.get("mutation_blocked", False)),
    )
    if saga.schema_version == 1:
        saga.legacy_phase = case.get("legacy_phase", "verifying")
    decision = decide_restart_action(saga)
    expected = case["expected_decision"]
    return {
        "case_id": case["case_id"],
        "phase": case["phase"],
        "decision": decision,
        "expected_decision": expected,
        "passed": decision == expected,
        "verdict": "PASS" if decision == expected else "FAIL",
        "idempotent_branch": (saga.remediation.branch if saga.remediation else None),
    }


def load_cases(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cases", type=Path)
    parser.add_argument("--output", type=Path, default=Path("saga-restart-report.json"))
    args = parser.parse_args()
    cases = [run_case(case) for case in load_cases(args.cases)]
    report = {
        "schema_version": 2,
        "suite": "tf4aio-89-gitops-saga-restart",
        "total": len(cases),
        "passed": sum(case["passed"] for case in cases),
        "failed": sum(not case["passed"] for case in cases),
        "reviewer_verdict": (
            "PASS" if all(case["passed"] for case in cases) else "FAIL"
        ),
        "cases": cases,
        "claim_boundary": (
            "Offline decision evidence level 3 only; GitHub ambiguity and Argo "
            "convergence are covered by controller adapter tests and sandbox drills."
        ),
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    raise SystemExit(0 if report["reviewer_verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
