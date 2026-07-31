from __future__ import annotations

from dataclasses import replace

import pytest

from app.config import Settings
from app.gitops import (
    GitObservation,
    GitOpsError,
    build_compensation_document,
    build_remediation_document,
    component,
    structured_hash,
)
from app.models import Evidence, Incident, IncidentStatus
from app.remediation import PolicyDenied, RemediationController
from app.saga import (
    GitTransaction,
    MemorySagaStore,
    RemediationSaga,
    SagaOutcome,
    SagaPhase,
)


def incident(**overrides):
    data = {
        "incident_id": "inc-m22-test",
        "incident_type": "service_latency_spike",
        "severity": "high",
        "affected_service": "product-reviews",
        "confidence": 0.95,
        "suspected_root_cause": "bounded review delay fault",
        "evidence": [
            Evidence(
                source="prometheus",
                query="review rpc",
                window="5m",
                value=5000,
            )
        ],
        "runbook_id": "product-reviews-config-rollback",
        "recommended_action": "gitops_restore_managed_env",
    }
    data.update(overrides)
    return Incident(**data)


def settings(**overrides):
    base = replace(
        Settings(),
        remediation_mode="gitops/live",
        autonomous_remediation_enabled=True,
        saga_backend="file",
        saga_path="test-sagas",
        allowed_deployments=("product-reviews",),
        verification_polls=3,
        verification_consecutive_healthy_polls=3,
        verification_settle_seconds=0,
        verification_interval_seconds=0,
        gitops_observe_interval_seconds=0,
        gitops_merge_timeout_seconds=1,
        gitops_runtime_timeout_seconds=1,
    )
    return replace(base, **overrides)


class FakeLock:
    def __init__(self):
        self.held = False
        self.acquires = 0
        self.releases = 0

    async def acquire(self, target, incident_id, ttl):
        self.acquires += 1
        if self.held:
            return False
        self.held = True
        return True

    async def renew(self, target, incident_id, ttl):
        return self.held

    async def release(self, target, incident_id):
        self.held = False
        self.releases += 1


class FakeGitOps:
    def __init__(self):
        self.current = {
            "components": {
                "product-reviews": {
                    "replicas": 2,
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
                    ],
                }
            }
        }
        self.known = {
            "components": {
                "product-reviews": {
                    "replicas": 2,
                    "envOverrides": [{"name": "AWS_REGION", "value": "us-east-1"}],
                }
            }
        }
        self.transactions = {}
        self.submit_writes = 0
        self.cancelled = []
        self.fail_checks = False
        self.fail_prepare = None
        self.last_merged_kind = None

    async def prepare(self, item, *, compensation_for=None):
        if self.fail_prepare:
            raise self.fail_prepare
        kind = "compensation" if compensation_for else "remediation"
        before = self.current
        after = (
            build_compensation_document(
                before, compensation_for, component_name="product-reviews"
            )
            if compensation_for
            else build_remediation_document(
                before,
                self.known,
                component_name="product-reviews",
                managed_env_names=(
                    "MANDATE22_REVIEW_DELAY_MS",
                    "MANDATE22_REVIEW_DELAY_TTL_SECONDS",
                    "MANDATE22_REVIEW_DELAY_MAX_REQUESTS",
                ),
                incident_id=item.incident_id,
            )
        )
        return GitTransaction(
            kind=kind,
            branch=f"aiops/{kind}/{item.incident_id}",
            base_sha="a" * 40,
            known_good_sha="b" * 40,
            target_file="environments/production/app-values.yaml",
            before_hash=structured_hash(component(before, "product-reviews")),
            after_hash=structured_hash(component(after, "product-reviews")),
            before_file_sha="c" * 40,
            after_file_sha="d" * 40,
            before_document=before,
            after_document=after,
        )

    async def submit(self, transaction, *, queue_merge=False):
        existing = self.transactions.get(transaction.branch)
        if existing is None:
            self.submit_writes += 1
            transaction.pr_number = self.submit_writes
            transaction.pr_node_id = f"PR_{self.submit_writes}"
            transaction.pr_url = f"https://github.test/pull/{self.submit_writes}"
            transaction.head_sha = str(self.submit_writes) * 40
            self.transactions[transaction.branch] = transaction
        if queue_merge:
            transaction.merge_queued = True
        return transaction

    async def observe(self, transaction):
        checks = {
            "validate": "failure" if self.fail_checks else "success",
            "check-pinned-dependencies": "success",
            "aiops-remediation-policy": "success",
        }
        if transaction.merge_queued and not self.fail_checks:
            transaction.merge_sha = (
                "e" if transaction.kind == "remediation" else "f"
            ) * 40
            transaction.state = "merged"
            self.current = transaction.after_document
            self.last_merged_kind = transaction.kind
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
        self.cancelled.append((transaction.branch, reason))


class FakeRuntime:
    def __init__(self, gitops, incident_id="inc-m22-test"):
        self.gitops = gitops
        self.incident_id = incident_id
        self.ready = True
        self.wrong_identity = False

    async def observe_deployment(self, deployment):
        target = component(self.gitops.current, "product-reviews")
        managed = sorted(
            item["name"]
            for item in target.get("envOverrides") or []
            if item["name"].startswith("MANDATE22_REVIEW_DELAY_")
        )
        correlation = (target.get("podAnnotations") or {}).get(
            "aiops.techx.io/remediation-id"
        )
        return {
            "deployment": deployment,
            "ready": self.ready,
            "remediation_id": "wrong" if self.wrong_identity else correlation,
            "managed_env_present": managed,
            "template_hash": "runtime",
        }


def controller(
    *, healthy=True, adapter=None, runtime=None, lock=None, **setting_values
):
    adapter = adapter or FakeGitOps()
    runtime = runtime or FakeRuntime(adapter)
    lock = lock or FakeLock()

    async def verifier(_):
        return {
            "healthy": healthy,
            "request_count": 20,
            "rpc": "/api/product-reviews/<id>",
        }

    store = MemorySagaStore()
    value = RemediationController(
        settings(**setting_values),
        adapter=adapter,
        runtime_observer=runtime,
        target_lock=lock,
        verifier=verifier,
        saga_store=store,
    )
    return value, store, adapter, runtime, lock


@pytest.mark.asyncio
async def test_success_is_one_pr_merge_runtime_and_three_healthy_polls():
    value, store, adapter, _, lock = controller(healthy=True)
    item = incident()
    value.authorize_by_policy(item)
    await value.execute(item)

    saga = (await store.list_all())[0]
    assert item.status == IncidentStatus.RESOLVED
    assert saga.outcome == SagaOutcome.RESOLVED
    assert saga.phase == SagaPhase.TERMINAL
    assert saga.remediation.branch == "aiops/remediation/inc-m22-test"
    assert saga.remediation.merge_sha == "e" * 40
    assert set(saga.remediation.checks) == set(value.settings.gitops_required_checks)
    assert len(saga.verification_samples) == 3
    assert adapter.submit_writes == 1
    assert lock.releases == 1


@pytest.mark.asyncio
async def test_forced_wrong_opens_one_compensation_and_quarantines():
    value, store, adapter, _, _ = controller(healthy=False)
    item = incident()
    value.authorize_by_policy(item)
    await value.execute(item)

    saga = (await store.list_all())[0]
    assert item.status == IncidentStatus.ESCALATED
    assert item.mutation_blocked is True
    assert saga.outcome == SagaOutcome.COMPENSATED_ESCALATED
    assert saga.compensation.branch == "aiops/compensation/inc-m22-test"
    assert saga.compensation.merge_sha == "f" * 40
    assert adapter.submit_writes == 2
    restored = component(adapter.current, "product-reviews")
    assert {
        item["name"]
        for item in restored["envOverrides"]
        if item["name"].startswith("MANDATE22_")
    } == {
        "MANDATE22_REVIEW_DELAY_MS",
        "MANDATE22_REVIEW_DELAY_TTL_SECONDS",
        "MANDATE22_REVIEW_DELAY_MAX_REQUESTS",
    }


@pytest.mark.asyncio
async def test_failed_required_check_cancels_before_merge():
    adapter = FakeGitOps()
    adapter.fail_checks = True
    value, store, _, _, _ = controller(adapter=adapter)
    item = incident()
    value.authorize_by_policy(item)
    await value.execute(item)
    saga = (await store.list_all())[0]
    assert saga.outcome == SagaOutcome.CHECKS_FAILED
    assert item.mutation_blocked is False
    assert adapter.cancelled
    assert saga.remediation.merge_sha is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        GitOpsError("invalid GitHub App credentials"),
        GitOpsError("base managed fields changed"),
        GitOpsError("unauthorized bot edit"),
    ],
)
async def test_pre_submit_failures_escalate_without_quarantine(error):
    adapter = FakeGitOps()
    adapter.fail_prepare = error
    value, store, _, _, _ = controller(adapter=adapter)
    item = incident()
    value.authorize_by_policy(item)
    await value.execute(item)
    saga = (await store.list_all())[0]
    assert saga.outcome == SagaOutcome.ESCALATED
    assert saga.remediation is None
    assert item.mutation_blocked is False


@pytest.mark.asyncio
async def test_wrong_runtime_identity_triggers_compensation():
    adapter = FakeGitOps()
    runtime = FakeRuntime(adapter)
    runtime.wrong_identity = True
    value, store, _, _, _ = controller(
        adapter=adapter,
        runtime=runtime,
        gitops_runtime_timeout_seconds=0.001,
    )
    item = incident()
    value.authorize_by_policy(item)
    await value.execute(item)
    saga = (await store.list_all())[0]
    assert saga.mutation_blocked is True
    assert saga.outcome == SagaOutcome.COMPENSATION_FAILED


@pytest.mark.asyncio
async def test_dry_run_writes_no_branch_or_pr():
    value, store, adapter, _, _ = controller(remediation_mode="gitops/dry-run")
    item = incident()
    value.authorize_by_policy(item)
    await value.execute(item)
    saga = (await store.list_all())[0]
    assert saga.outcome == SagaOutcome.ABANDONED_PRE_MERGE
    assert adapter.submit_writes == 0


def test_policy_rejects_every_target_but_product_reviews():
    value, *_ = controller()
    item = incident(affected_service="checkout")
    with pytest.raises(PolicyDenied, match="exact_target"):
        value.authorize_by_policy(item)


def test_policy_rejects_low_volume_or_absent_prometheus_evidence():
    value, *_ = controller()
    item = incident(evidence=[])
    with pytest.raises(PolicyDenied, match="evidence_present"):
        value.authorize_by_policy(item)


def test_structured_document_change_preserves_protected_fields():
    adapter = FakeGitOps()
    changed = build_remediation_document(
        adapter.current,
        adapter.known,
        component_name="product-reviews",
        managed_env_names=tuple(
            sorted(
                {
                    "MANDATE22_REVIEW_DELAY_MS",
                    "MANDATE22_REVIEW_DELAY_TTL_SECONDS",
                    "MANDATE22_REVIEW_DELAY_MAX_REQUESTS",
                }
            )
        ),
        incident_id="inc-m22-test",
    )
    original = component(adapter.current, "product-reviews")
    after = component(changed, "product-reviews")
    assert after["replicas"] == original["replicas"]
    assert after["envOverrides"] == [{"name": "AWS_REGION", "value": "us-east-1"}]
    assert after["podAnnotations"]["aiops.techx.io/remediation-id"] == "inc-m22-test"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phase",
    [
        SagaPhase.PR_OPEN,
        SagaPhase.CHECKS_PENDING,
        SagaPhase.MERGE_QUEUED,
        SagaPhase.MERGED,
        SagaPhase.RUNTIME_PENDING,
        SagaPhase.VERIFYING,
    ],
)
async def test_restart_from_each_post_prepare_phase_reuses_one_pr(phase):
    adapter = FakeGitOps()
    item = incident()
    tx = await adapter.prepare(item)
    await adapter.submit(tx)
    adapter.transactions[tx.branch] = tx
    store = MemorySagaStore()
    saga = RemediationSaga(
        incident_id=item.incident_id,
        target="product-reviews",
        phase=phase,
        remediation=tx,
        expected_runtime_identity={
            "remediation_id": item.incident_id,
            "managed_env_present": [],
        },
        lock_held=True,
    )
    await store.save(saga)
    runtime = FakeRuntime(adapter)

    async def verifier(_):
        return {"healthy": True, "request_count": 20}

    value = RemediationController(
        settings(),
        adapter=adapter,
        runtime_observer=runtime,
        target_lock=FakeLock(),
        verifier=verifier,
        saga_store=store,
    )
    # Model a lock already held by this incident across process restart.
    value.target_lock.held = True
    result = await value.resume_saga(saga)
    final = await store.get(saga.saga_id)
    assert result["outcome"] == SagaOutcome.RESOLVED.value
    assert final.outcome == SagaOutcome.RESOLVED
    assert adapter.submit_writes == 1
    assert len(adapter.transactions) == 1
