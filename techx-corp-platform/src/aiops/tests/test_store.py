import pytest

from app.models import Incident
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
