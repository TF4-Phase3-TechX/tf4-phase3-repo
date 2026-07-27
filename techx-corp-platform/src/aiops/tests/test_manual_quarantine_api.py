"""API-path coverage for manual approval quarantine and operator clear.

These tests exercise the same module-level store/remediation wiring used by
``POST /v1/incidents/{id}/approve`` and ``DELETE /v1/targets/{service}/mutation-block``
without starting the long-running poll worker.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

import app.main as main_mod
from app.config import Settings
from app.models import AuditEvent, Incident, IncidentStatus
from app.remediation import PolicyDenied, RemediationController
from app.store import IncidentStore


class AmbiguousTimeoutAdapter:
    def __init__(self):
        self.patch_attempts = 0

    def acquire_lock(self, deployment, incident_id, ttl):
        return True

    def release_lock(self, deployment, incident_id):
        return None

    def previous_template(self, deployment):
        return (
            {"metadata": {"labels": {"version": "current"}}},
            {"metadata": {"labels": {"version": "previous"}}},
        )

    def patch_template(self, deployment, template):
        self.patch_attempts += 1
        raise TimeoutError("response lost after possible server commit")

    def rollout_ready(self, deployment):
        return True


def _pending_incident(service: str = "product-reviews", incident_type: str = "service_latency_spike"):
    item = Incident(
        incident_type=incident_type,
        severity="high",
        affected_service=service,
        confidence=0.9,
        suspected_root_cause="recent deploy",
        runbook_id="deployment-latency-rollback",
        recommended_action="rollback",
    )
    item.status = IncidentStatus.AWAITING_APPROVAL
    item.approval_status = "pending"
    return item


@pytest.fixture
def api_path(monkeypatch):
    store = IncidentStore(cooldown_seconds=0)
    controller = RemediationController(
        replace(
            Settings(),
            remediation_mode="live",
            known_good_revisions={"product-reviews": "1"},
            verification_settle_seconds=0,
            verification_interval_seconds=0,
            approval_token="test-token",
        ),
        adapter=AmbiguousTimeoutAdapter(),
    )
    monkeypatch.setattr(main_mod, "store", store)
    monkeypatch.setattr(main_mod, "remediation", controller)
    monkeypatch.setattr(
        main_mod,
        "settings",
        replace(main_mod.settings, approval_token="test-token"),
    )
    return store, controller


@pytest.mark.asyncio
async def test_manual_approve_ambiguous_mutation_quarantines_target(api_path):
    store, controller = api_path
    first, _ = await store.upsert(_pending_incident())
    controller.request_approval(first)

    result = await main_mod.approve(first.incident_id)

    assert result.incident_id == first.incident_id
    assert first.mutation_blocked is True
    assert any(event.event == "action_outcome_unknown" for event in first.audit_events)
    assert await store.is_target_blocked("product-reviews") is True
    detail = await store.target_block("product-reviews")
    assert detail is not None
    assert detail["incident_id"] == first.incident_id


@pytest.mark.asyncio
async def test_manual_approve_blocked_when_target_already_quarantined(api_path):
    store, controller = api_path
    first, _ = await store.upsert(_pending_incident())
    controller.request_approval(first)
    await main_mod.approve(first.incident_id)
    assert await store.is_target_blocked("product-reviews") is True

    # Different incident type on the same service must not be able to mutate.
    second, _ = await store.upsert(
        _pending_incident(incident_type="service_error_rate_spike")
    )
    controller.request_approval(second)

    with pytest.raises(main_mod.HTTPException) as exc_info:
        await main_mod.approve(second.incident_id)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "target_mutation_quarantine_active"
    assert second.execution_attempts == 0
    assert second.mutation_blocked is False


@pytest.mark.asyncio
async def test_clear_quarantine_unlocks_incident_for_recovery(api_path):
    store, controller = api_path
    active, _ = await store.upsert(_pending_incident())
    controller.request_approval(active)
    await main_mod.approve(active.incident_id)
    assert active.mutation_blocked is True
    assert await store.is_target_blocked("product-reviews") is True

    # Before clear: recovery must stay suppressed.
    assert (
        await store.observe_recovery(active.incident_type, active.affected_service, 1)
        is None
    )
    assert active.status == IncidentStatus.ESCALATED

    cleared = await main_mod.clear_mutation_block("product-reviews")
    assert cleared["cleared"] is True
    assert await store.is_target_blocked("product-reviews") is False
    assert active.mutation_blocked is False
    assert any(
        event.event == "mutation_block_cleared_by_operator"
        for event in active.audit_events
    )

    resolved = await store.observe_recovery(
        active.incident_type, active.affected_service, 1
    )
    assert resolved is active
    assert active.status == IncidentStatus.RESOLVED

    # New remediation cycle can start after operator unlock + resolve.
    fresh, created = await store.upsert(
        _pending_incident(incident_type="service_error_rate_spike")
    )
    assert created is True
    assert await store.is_target_blocked(fresh.affected_service) is False


@pytest.mark.asyncio
async def test_manual_approve_reconciles_when_execute_raises_after_ambiguous_mutation(
    api_path, monkeypatch
):
    """If execute records an ambiguous mutation then raises, still quarantine."""

    store, controller = api_path
    active, _ = await store.upsert(_pending_incident())
    controller.request_approval(active)

    async def execute_then_raise(incident: Incident) -> None:
        incident.status = IncidentStatus.ESCALATED
        incident.mutation_blocked = True
        incident.escalation_reason = "Live mutation outcome is unknown"
        incident.audit_events.append(AuditEvent(event="action_outcome_unknown"))
        raise PolicyDenied("simulated post-mutation policy surface")

    monkeypatch.setattr(controller, "execute", execute_then_raise)

    with pytest.raises(main_mod.HTTPException) as exc_info:
        await main_mod.approve(active.incident_id)
    assert exc_info.value.status_code == 409
    assert await store.is_target_blocked("product-reviews") is True