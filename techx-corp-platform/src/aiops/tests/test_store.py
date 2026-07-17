import pytest

from app.models import Incident, IncidentStatus
from app.store import IncidentStore


def incident():
    return Incident(
        incident_type="service_latency_spike", severity="high", affected_service="checkout",
        confidence=.9, suspected_root_cause="latency", runbook_id="deployment-latency-rollback",
        recommended_action="rollback",
    )


@pytest.mark.asyncio
async def test_active_incidents_are_deduplicated():
    store = IncidentStore()
    first, created = await store.upsert(incident())
    second, created_again = await store.upsert(incident())
    assert created is True
    assert created_again is False
    assert second.incident_id == first.incident_id
    assert len(await store.list()) == 1


@pytest.mark.asyncio
async def test_breach_recover_breach_creates_a_new_incident_after_cooldown():
    store = IncidentStore(cooldown_seconds=0)
    first, created = await store.upsert(incident())
    first.status = IncidentStatus.AWAITING_APPROVAL
    first.approval_status = "pending"

    assert await store.observe_recovery(first.incident_type, first.affected_service, 2) is None
    resolved = await store.observe_recovery(first.incident_type, first.affected_service, 2)
    assert resolved is first
    assert resolved.status == IncidentStatus.RESOLVED
    assert resolved.approval_status == "cancelled_recovered"

    second, created_again = await store.upsert(incident())
    assert created is True
    assert created_again is True
    assert second.incident_id != first.incident_id


@pytest.mark.asyncio
async def test_unknown_coverage_resets_consecutive_recovery_streak():
    store = IncidentStore(cooldown_seconds=0)
    active, _ = await store.upsert(incident())
    assert await store.observe_recovery(active.incident_type, active.affected_service, 2) is None
    await store.reset_recovery(active.incident_type, active.affected_service)
    assert await store.observe_recovery(active.incident_type, active.affected_service, 2) is None
    assert active.status == IncidentStatus.OPEN
