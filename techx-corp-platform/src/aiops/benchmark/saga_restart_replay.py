#!/usr/bin/env python3
"""One-command offline repro for TF4AIO-89 durable saga restart cases.

Usage (from techx-corp-platform/src/aiops):

  python -m benchmark.saga_restart_replay \\
    ../../../docs/aio1/mandate-22/saga-restart-cases-v1.jsonl \\
    --output ../../../docs/aio1/mandate-22/saga-restart-report.json

Exit 0 only when every case matches its expected outcome (reviewer verdict PASS).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

from app.config import Settings
from app.remediation import RemediationController
from app.saga import (
    FileSagaStore,
    RemediationSaga,
    SagaOutcome,
    SagaPhase,
    decide_restart_action,
)


class ReplayAdapter:
    def __init__(self, case: dict):
        self.current = case.get("cluster_template") or case.get("selected_template")
        self.previous = case.get("selected_template")
        self.original = case.get("original_template")
        self.patches: list = []
        self.hold_lease = bool(case.get("lost_lease"))
        self.healthy = bool(case.get("verification_healthy", True))

    def acquire_lock(self, deployment, incident_id, ttl):
        return not self.hold_lease

    def release_lock(self, deployment, incident_id):
        return None

    def previous_template(self, deployment):
        return self.current, self.previous

    def patch_template(self, deployment, template):
        self.patches.append(template)
        self.current = template

    def dry_run_patch_template(self, deployment, template):
        return None

    def rollout_ready(self, deployment):
        return True

    def read_template(self, deployment):
        return self.current

    def begin_argo_window(self, deployment, incident_id, ttl):
        return {"aiops.techx/mutation-window": incident_id}

    def end_argo_window(self, deployment, incident_id):
        return None


async def run_case(case: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="aiops-saga-") as tmp:
        store = FileSagaStore(tmp)
        saga = RemediationSaga(
            saga_id=case.get("saga_id") or f"saga-{case['case_id']}",
            incident_id=case.get("incident_id") or f"inc-{case['case_id']}",
            target=case.get("target", "product-reviews"),
            phase=SagaPhase(case["phase"]),
            mutation_attempted=bool(case.get("mutation_attempted", False)),
            original_template=case.get("original_template"),
            selected_template=case.get("selected_template"),
            expected_template_after_action=case.get("expected_template_after_action")
            or case.get("selected_template"),
            known_good_revision=case.get("known_good_revision"),
            argo_window_active=bool(case.get("argo_window_active", False)),
            lease_held=bool(case.get("lease_held", True)),
        )
        await store.save(saga)

        adapter = ReplayAdapter(case)

        async def verifier(_):
            # When the case models a failed remediation verify window, only the
            # post-mutation template is unhealthy; restoring original recovers.
            if not adapter.healthy and adapter.previous is not None:
                still_on_mutation = adapter.current == adapter.previous
                ok = not still_on_mutation
            else:
                ok = adapter.healthy
            return {
                "healthy": ok,
                "p95_latency_ms": 10 if ok else 9000,
            }

        controller = RemediationController(
            replace(
                Settings(),
                remediation_mode="live",
                verification_polls=1,
                rollback_verification_polls=1,
                verification_settle_seconds=0,
                verification_interval_seconds=0,
                argo_window_enabled=True,
            ),
            adapter=adapter,
            verifier=verifier,
            saga_store=store,
        )
        decision = decide_restart_action(saga)
        results = await controller.reconcile_open_sagas()
        final = await store.get(saga.saga_id)
        expected = case["expected_outcome"]
        actual = final.outcome.value if final else "missing"
        passed = actual == expected and decision == case.get(
            "expected_decision", decision
        )
        return {
            "case_id": case["case_id"],
            "phase": case["phase"],
            "decision": decision,
            "expected_decision": case.get("expected_decision"),
            "expected_outcome": expected,
            "actual_outcome": actual,
            "mutation_blocked": bool(final.mutation_blocked) if final else None,
            "patches": len(adapter.patches),
            "resume_result": results[0] if results else None,
            "passed": passed,
            "verdict": "PASS" if passed else "FAIL",
        }


def load_cases(path: Path) -> list[dict]:
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(json.loads(line))
    return cases


async def main_async(args: argparse.Namespace) -> int:
    cases = load_cases(Path(args.cases))
    results = [await run_case(case) for case in cases]
    passed = sum(1 for r in results if r["passed"])
    report = {
        "suite": "tf4aio-89-saga-restart",
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "reviewer_verdict": "PASS" if passed == len(results) else "FAIL",
        "cases": results,
        "claim_boundary": (
            "Offline/integration evidence level 3 only. "
            "Does not enable live autonomous remediation or prove EKS/GitOps."
        ),
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"reviewer_verdict": report["reviewer_verdict"], "passed": passed, "total": len(results)}))
    return 0 if report["reviewer_verdict"] == "PASS" else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", help="JSONL case file")
    parser.add_argument(
        "--output",
        default="saga-restart-report.json",
        help="Machine-readable report path",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
