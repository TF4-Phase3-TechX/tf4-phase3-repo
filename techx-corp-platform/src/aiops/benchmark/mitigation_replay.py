#!/usr/bin/env python3
"""External JSONL replay for the canonical GitOps remediation controller."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.config import Settings
from app.gitops import (
    GitObservation,
    build_compensation_document,
    build_remediation_document,
    component,
    structured_hash,
)
from app.models import Evidence, Incident
from app.remediation import RemediationController
from app.saga import GitTransaction, MemorySagaStore


class ReplayLock:
    async def acquire(self, *_):
        return True

    async def renew(self, *_):
        return True

    async def release(self, *_):
        return None


class ReplayGitOps:
    def __init__(self):
        self.current = {
            "components": {
                "product-reviews": {
                    "envOverrides": [
                        {"name": "AWS_REGION", "value": "us-east-1"},
                        {"name": "MANDATE22_REVIEW_DELAY_MS", "value": "5000"},
                        {
                            "name": "MANDATE22_REVIEW_DELAY_TTL_SECONDS",
                            "value": "300",
                        },
                        {
                            "name": "MANDATE22_REVIEW_DELAY_MAX_REQUESTS",
                            "value": "100",
                        },
                    ]
                }
            }
        }
        self.known = {
            "components": {
                "product-reviews": {
                    "envOverrides": [{"name": "AWS_REGION", "value": "us-east-1"}]
                }
            }
        }
        self.prs: dict[str, GitTransaction] = {}
        self.timeline: list[dict[str, Any]] = []

    async def prepare(self, incident, *, compensation_for=None):
        kind = "compensation" if compensation_for else "remediation"
        after = (
            build_compensation_document(
                self.current,
                compensation_for,
                component_name="product-reviews",
            )
            if compensation_for
            else build_remediation_document(
                self.current,
                self.known,
                component_name="product-reviews",
                managed_env_names=(
                    "MANDATE22_REVIEW_DELAY_MS",
                    "MANDATE22_REVIEW_DELAY_TTL_SECONDS",
                    "MANDATE22_REVIEW_DELAY_MAX_REQUESTS",
                ),
                incident_id=incident.incident_id,
            )
        )
        return GitTransaction(
            kind=kind,
            branch=f"aiops/{kind}/{incident.incident_id}",
            base_sha="a" * 40,
            known_good_sha="b" * 40,
            target_file="environments/production/app-values.yaml",
            before_hash=structured_hash(component(self.current, "product-reviews")),
            after_hash=structured_hash(component(after, "product-reviews")),
            before_file_sha="c" * 40,
            after_file_sha="d" * 40,
            before_document=self.current,
            after_document=after,
        )

    async def submit(self, transaction, *, queue_merge=False):
        if transaction.branch not in self.prs:
            transaction.pr_number = len(self.prs) + 1
            transaction.pr_node_id = f"PR_{transaction.pr_number}"
            transaction.pr_url = f"https://replay.invalid/pull/{transaction.pr_number}"
            transaction.head_sha = str(transaction.pr_number) * 40
            self.prs[transaction.branch] = transaction
            self.timeline.append({"event": "pr_open", "branch": transaction.branch})
        if queue_merge:
            transaction.merge_queued = True
            self.timeline.append(
                {"event": "merge_queued", "branch": transaction.branch}
            )
        return transaction

    async def observe(self, transaction):
        checks = {
            "validate": "success",
            "check-pinned-dependencies": "success",
            "aiops-remediation-policy": "success",
        }
        if transaction.merge_queued:
            transaction.merge_sha = (
                "e" if transaction.kind == "remediation" else "f"
            ) * 40
            self.current = transaction.after_document
            self.timeline.append(
                {
                    "event": "merged",
                    "branch": transaction.branch,
                    "merge_sha": transaction.merge_sha,
                }
            )
            return GitObservation(
                state="merged",
                checks=checks,
                head_sha=transaction.head_sha,
                merge_sha=transaction.merge_sha,
                merge_queued=True,
            )
        return GitObservation(
            state="checks", checks=checks, head_sha=transaction.head_sha
        )

    async def cancel(self, transaction, reason):
        self.timeline.append(
            {"event": "cancelled", "branch": transaction.branch, "reason": reason}
        )


class ReplayRuntime:
    def __init__(self, gitops, *, compensation_ready=True):
        self.gitops = gitops
        self.compensation_ready = compensation_ready

    async def observe_deployment(self, deployment):
        target = component(self.gitops.current, "product-reviews")
        correlation = (target.get("podAnnotations") or {}).get(
            "aiops.techx.io/remediation-id"
        )
        managed = [
            item["name"]
            for item in target.get("envOverrides") or []
            if item["name"].startswith("MANDATE22_")
        ]
        compensation = any(
            item["event"] == "merged" and "/compensation/" in item["branch"]
            for item in self.gitops.timeline
        )
        return {
            "ready": self.compensation_ready if compensation else True,
            "remediation_id": correlation,
            "managed_env_present": sorted(managed),
            "deployment": deployment,
        }


class ReplayVerifier:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)

    async def __call__(self, service):
        try:
            healthy = bool(next(self.outcomes))
        except StopIteration:
            healthy = False
        return {
            "healthy": healthy,
            "request_count": 20,
            "rpc": "/api/product-reviews/<id>",
        }


def load(path: Path) -> list[dict[str, Any]]:
    result = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON line {line_number}: {exc}") from exc
    return result


async def evaluate(case: dict[str, Any]) -> dict[str, Any]:
    action_health = list(case.get("action_health") or [])
    if not action_health:
        raise ValueError("action_health must contain at least one poll")
    adapter = ReplayGitOps()
    runtime = ReplayRuntime(
        adapter,
        compensation_ready=bool(case.get("compensation_runtime_healthy", True)),
    )
    store = MemorySagaStore()
    settings = replace(
        Settings(),
        remediation_mode="gitops/live",
        autonomous_remediation_enabled=True,
        saga_backend="file",
        saga_path="replay-sagas",
        allowed_deployments=("product-reviews",),
        verification_polls=len(action_health),
        verification_consecutive_healthy_polls=len(action_health),
        verification_settle_seconds=0,
        verification_interval_seconds=0,
        gitops_observe_interval_seconds=0,
        gitops_merge_timeout_seconds=1,
        gitops_runtime_timeout_seconds=float(case.get("runtime_timeout_seconds", 1)),
    )
    controller = RemediationController(
        settings,
        adapter=adapter,
        runtime_observer=runtime,
        target_lock=ReplayLock(),
        verifier=ReplayVerifier(action_health),
        saga_store=store,
    )
    incident = Incident(
        incident_id=f"inc-{case['id']}",
        incident_type="service_latency_spike",
        severity="high",
        affected_service="product-reviews",
        confidence=0.95,
        suspected_root_cause="external replay",
        evidence=[
            Evidence(
                source="prometheus",
                query=f"scenario:{case['id']}",
                window="scenario",
                value="breached",
            )
        ],
        runbook_id="product-reviews-config-rollback",
        recommended_action="gitops_restore_managed_env",
    )
    await controller.handle_incident(incident)
    saga = (await store.list_all())[0]
    expected = case["expected_outcome"]
    return {
        "id": case["id"],
        "expected_outcome": expected,
        "actual_outcome": saga.outcome.value,
        "passed": saga.outcome.value == expected,
        "incident_status": incident.status.value,
        "mutation_blocked": incident.mutation_blocked,
        "timeline": adapter.timeline,
        "evidence": saga.public_evidence(),
    }


async def replay(path: Path) -> dict[str, Any]:
    cases = [await evaluate(case) for case in load(path)]
    return {
        "schema_version": 2,
        "source": str(path),
        "all_passed": all(case["passed"] for case in cases),
        "cases": cases,
        "limitations": [
            "Uses the production controller with bounded GitHub/Argo/telemetry adapters.",
            "Offline replay is evidence level 3 and does not replace Kind/Argo or production drills.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenarios", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.output and args.output.exists() and not args.force:
        parser.error(f"output exists: {args.output}; pass --force")
    report = asyncio.run(replay(args.scenarios))
    if args.output:
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["all_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
