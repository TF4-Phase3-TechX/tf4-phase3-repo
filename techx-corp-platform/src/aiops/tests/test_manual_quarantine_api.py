from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.config import Settings
from app.models import AuditEvent, Evidence, Incident, IncidentStatus
from app.remediation import RemediationController
from app.saga import MemorySagaStore, RemediationSaga, SagaOutcome
from app.store import IncidentStore


def incident():
    return Incident(
        incident_id="inc-api-m22",
        incident_type="service_latency_spike",
        severity="high",
        affected_service="product-reviews",
        confidence=0.95,
        suspected_root_cause="bounded fault",
        evidence=[
            Evidence(source="prometheus", query="review rpc", window="5m", value=5000)
        ],
        runbook_id="product-reviews-config-rollback",
        recommended_action="gitops_restore_managed_env",
    )


@pytest.fixture
def api(monkeypatch):
    settings = replace(
        Settings(),
        remediation_mode="gitops/dry-run",
        autonomous_remediation_enabled=False,
        approval_token="test-token",
        verification_settle_seconds=0,
    )
    store = IncidentStore(cooldown_seconds=0)
    sagas = MemorySagaStore()
    controller = RemediationController(settings, saga_store=sagas)
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "saga_store", sagas)
    monkeypatch.setattr(main, "remediation", controller)
    return TestClient(main.app), store, sagas, controller


@pytest.mark.asyncio
async def test_approve_enqueues_and_remediation_api_is_sanitized(api):
    client, store, _, controller = api
    item = incident()
    await store.upsert(item)
    controller.request_approval(item)

    response = client.post(
        f"/v1/incidents/{item.incident_id}/approve",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "enqueued"

    evidence = client.get(f"/v1/incidents/{item.incident_id}/remediation")
    assert evidence.status_code == 200
    assert evidence.json()["phase"] == "TERMINAL"
    assert evidence.json()["outcome"] == "abandoned_pre_merge"


@pytest.mark.asyncio
async def test_approve_rejects_active_target_quarantine(api):
    client, store, _, controller = api
    item = incident()
    await store.upsert(item)
    controller.request_approval(item)
    item.mutation_blocked = True
    item.escalation_reason = "compensation unverified"
    item.audit_events.append(AuditEvent(event="gitops_remediation_merged"))
    item.status = IncidentStatus.ESCALATED
    await store.reconcile_post_execution_quarantine(item)
    item.status = IncidentStatus.AWAITING_APPROVAL

    response = client.post(
        f"/v1/incidents/{item.incident_id}/approve",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "target_mutation_quarantine_active"


@pytest.mark.asyncio
async def test_authenticated_operator_clear_removes_durable_quarantine(api):
    client, store, sagas, _ = api
    item = incident()
    item.status = IncidentStatus.ESCALATED
    item.mutation_blocked = True
    item.escalation_reason = "forced-wrong compensation restored"
    await store.upsert(item)
    await store.reconcile_post_execution_quarantine(item)
    saga = RemediationSaga(
        incident_id=item.incident_id,
        target=item.affected_service,
        mutation_blocked=True,
    )
    saga.terminate(SagaOutcome.COMPENSATED_ESCALATED, item.escalation_reason)
    await sagas.save(saga)

    response = client.delete(
        "/v1/targets/product-reviews/mutation-block",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    assert response.json()["cleared"] is True
    assert await sagas.list_open_for_target("product-reviews") == []
