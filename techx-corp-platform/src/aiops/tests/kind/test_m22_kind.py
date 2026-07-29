"""Disposable-Kubernetes regression tests for the Mandate 22 recovery path.

Normal unit/CI runs skip this module. Set both kubeconfig variables to run it
against an explicitly disposable cluster; never point them at a shared cluster.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import pytest

from app.config import Settings
from app.models import Incident, IncidentStatus
from app.remediation import KubernetesRollbackAdapter, RemediationController
from app.saga import FileSagaStore, RemediationSaga, SagaOutcome


ADMIN_KUBECONFIG = os.getenv("M22_KIND_ADMIN_KUBECONFIG")
LIMITED_KUBECONFIG = os.getenv("KUBECONFIG")
if not ADMIN_KUBECONFIG or not LIMITED_KUBECONFIG:
    pytest.skip(
        "requires disposable Kind admin and limited-serviceaccount kubeconfigs",
        allow_module_level=True,
    )

KIND_DIR = Path(__file__).parent
NAMESPACE = "m22-local"
TARGET = "product-reviews"


class WaitReadyKubernetesAdapter(KubernetesRollbackAdapter):
    """Bound real rollout readiness to one controller verification call."""

    def rollout_ready(self, deployment: str) -> bool:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if super().rollout_ready(deployment):
                return True
            time.sleep(0.25)
        return False


def _admin_apply(manifest: str) -> None:
    subprocess.run(
        [
            "kubectl",
            "--kubeconfig",
            ADMIN_KUBECONFIG,
            "apply",
            "-f",
            str(KIND_DIR / manifest),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _settings() -> Settings:
    return replace(
        Settings(),
        namespace=NAMESPACE,
        remediation_mode="live",
        autonomous_remediation_enabled=False,
        allowed_deployments=(TARGET,),
        known_good_revisions={TARGET: "1"},
        verification_polls=1,
        rollback_verification_polls=1,
        verification_settle_seconds=0,
        verification_interval_seconds=0,
        verification_consecutive_healthy_polls=1,
        argo_window_enabled=True,
    )


def _adapter() -> WaitReadyKubernetesAdapter:
    return WaitReadyKubernetesAdapter(
        NAMESPACE,
        deployment_recency_hours=24,
        known_good_revisions={TARGET: "1"},
    )


@pytest.mark.asyncio
async def test_real_deployment_lease_action_verify_and_cleanup(tmp_path: Path):
    adapter = _adapter()
    store = FileSagaStore(tmp_path)

    async def verifier(_):
        return {
            "healthy": True,
            "p95_latency_ms": 10,
            "target_error_rate": 0,
            "request_count": 100,
        }

    controller = RemediationController(
        _settings(), adapter=adapter, verifier=verifier, saga_store=store
    )
    incident = Incident(
        incident_type="service_latency_spike",
        severity="high",
        affected_service=TARGET,
        confidence=0.9,
        suspected_root_cause="disposable Kind revision v2",
        runbook_id="deployment-latency-rollback",
        recommended_action="rollback",
    )
    controller.request_approval(incident)
    controller.approve(incident)

    await controller.execute(incident)

    if incident.status != IncidentStatus.RESOLVED:
        print(incident.model_dump_json(indent=2))
    assert incident.status == IncidentStatus.RESOLVED, {
        "reason": incident.escalation_reason,
        "verification": incident.verification_result,
        "rollback": incident.rollback_result,
        "audit": [event.event for event in incident.audit_events],
    }
    sagas = await store.list_all()
    assert len(sagas) == 1
    assert sagas[0].outcome == SagaOutcome.RESOLVED
    assert sagas[0].is_open is False
    current = adapter.read_template(TARGET)
    assert current["metadata"]["annotations"]["m22.test/revision"] == "v1-known-good"


@pytest.mark.asyncio
async def test_real_cleanup_rbac_loss_is_retryable_without_second_action(
    tmp_path: Path,
):
    adapter = _adapter()
    store = FileSagaStore(tmp_path)
    incident_id = "inc-kind-cleanup-rbac"
    assert adapter.acquire_lock(TARGET, incident_id, 300) is True
    adapter.begin_argo_window(TARGET, incident_id, 300)

    saga = RemediationSaga(
        incident_id=incident_id,
        target=TARGET,
        mutation_attempted=True,
        lease_held=True,
        argo_window_active=True,
    )
    saga.terminate(SagaOutcome.RESOLVED, "verification complete")
    await store.save(saga)
    controller = RemediationController(
        _settings(), adapter=adapter, saga_store=store
    )

    _admin_apply("m22-rbac-cleanup-denied.yaml")
    try:
        with pytest.raises(RuntimeError, match="Forbidden"):
            await controller.reconcile_open_sagas()
        blocked = await store.get(saga.saga_id)
        assert blocked.is_open is True
        assert blocked.argo_window_active is True
        assert blocked.lease_held is True
        # Reconciliation never calls patch_template, so it cannot repeat the
        # already-acknowledged remediation action.
        assert blocked.generation == saga.generation
    finally:
        _admin_apply("m22-rbac.yaml")

    results = await controller.reconcile_open_sagas()
    cleaned = await store.get(saga.saga_id)
    assert results[0]["cleanup"] == "complete"
    assert cleaned.is_open is False
    assert cleaned.argo_window_active is False
    assert cleaned.lease_held is False
