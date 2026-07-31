import pytest

from app.models import AuditEvent, Incident, IncidentStatus
from app.store import IncidentStore


def incident(service: str = "checkout"):
    return Incident(
        incident_type="service_latency_spike",
        severity="high",
        affected_service=service,
        confidence=0.9,
        suspected_root_cause="latency",
        runbook_id="product-reviews-config-rollback",
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
async def test_active_incident_refreshes_impact_and_severity():
    store = IncidentStore()
    first, _ = await store.upsert(incident())
    candidate = incident()
    candidate.severity = "medium"
    candidate.impact = {"level": "warning_budget_burn"}

    refreshed, created = await store.upsert(candidate)

    assert created is False
    assert refreshed.incident_id == first.incident_id
    assert refreshed.severity == "medium"
    assert refreshed.impact["level"] == "warning_budget_burn"
    assert refreshed.audit_events[-1].event == "incident_routing_changed"


@pytest.mark.asyncio
async def test_breach_recover_breach_creates_a_new_incident_after_cooldown():
    store = IncidentStore(cooldown_seconds=0)
    first, created = await store.upsert(incident())
    first.status = IncidentStatus.AWAITING_APPROVAL
    first.approval_status = "pending"

    assert (
        await store.observe_recovery(first.incident_type, first.affected_service, 2)
        is None
    )
    resolved = await store.observe_recovery(
        first.incident_type, first.affected_service, 2
    )
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
    assert (
        await store.observe_recovery(active.incident_type, active.affected_service, 2)
        is None
    )
    await store.reset_recovery(active.incident_type, active.affected_service)
    assert (
        await store.observe_recovery(active.incident_type, active.affected_service, 2)
        is None
    )
    assert active.status == IncidentStatus.OPEN


@pytest.mark.asyncio
async def test_mutation_blocked_incident_never_auto_resolves():
    store = IncidentStore(cooldown_seconds=0)
    active, _ = await store.upsert(incident())
    active.status = IncidentStatus.ESCALATED
    active.mutation_blocked = True
    active.escalation_reason = "rollback unverified"

    assert (
        await store.observe_recovery(active.incident_type, active.affected_service, 1)
        is None
    )
    assert (
        await store.observe_recovery(active.incident_type, active.affected_service, 1)
        is None
    )
    assert active.status == IncidentStatus.ESCALATED
    suppress_events = [
        event
        for event in active.audit_events
        if event.event == "auto_resolve_suppressed_mutation_blocked"
    ]
    # Continuous recovery polls must not flood the audit trail.
    assert len(suppress_events) == 1


@pytest.mark.asyncio
async def test_pre_mutation_escalation_without_block_can_auto_resolve():
    """Policy deny without mutation_blocked must remain recoverable."""

    store = IncidentStore(cooldown_seconds=0)
    active, _ = await store.upsert(incident())
    active.status = IncidentStatus.ESCALATED
    active.mutation_blocked = False
    active.escalation_reason = "Autonomous policy denied: evidence_present"

    assert (
        await store.observe_recovery(active.incident_type, active.affected_service, 2)
        is None
    )
    resolved = await store.observe_recovery(
        active.incident_type, active.affected_service, 2
    )
    assert resolved is not None
    assert resolved.status == IncidentStatus.RESOLVED


@pytest.mark.asyncio
async def test_target_quarantine_blocks_auto_resolve_and_survives_clear_cycle():
    store = IncidentStore(cooldown_seconds=0)
    active, _ = await store.upsert(incident())
    active.status = IncidentStatus.ESCALATED
    active.mutation_blocked = True
    active.escalation_reason = "post-mutation safety failure"
    await store.block_target(
        active.affected_service,
        reason="post-mutation safety failure",
        incident_id=active.incident_id,
    )

    assert await store.is_target_blocked(active.affected_service) is True
    assert (
        await store.observe_recovery(active.incident_type, active.affected_service, 1)
        is None
    )
    assert active.status == IncidentStatus.ESCALATED
    assert active.mutation_blocked is True

    assert await store.clear_target_block(active.affected_service) is True
    assert await store.is_target_blocked(active.affected_service) is False
    # Operator clear must unlock the incident flag so recovery can finish.
    assert active.mutation_blocked is False
    assert any(
        event.event == "mutation_block_cleared_by_operator"
        for event in active.audit_events
    )
    assert (
        await store.observe_recovery(active.incident_type, active.affected_service, 1)
        is active
    )
    assert active.status == IncidentStatus.RESOLVED


@pytest.mark.asyncio
async def test_reconcile_post_execution_quarantines_ambiguous_mutation():
    store = IncidentStore(cooldown_seconds=0)
    active, _ = await store.upsert(incident())
    active.status = IncidentStatus.ESCALATED
    active.mutation_blocked = True
    active.escalation_reason = "Live mutation outcome is unknown"
    active.audit_events.append(
        AuditEvent(
            event="action_outcome_unknown",
            detail={"operator_reconciliation_required": True},
        )
    )

    assert await store.reconcile_post_execution_quarantine(active) is True
    assert await store.is_target_blocked(active.affected_service) is True
    detail = await store.target_block(active.affected_service)
    assert detail is not None
    assert detail["incident_id"] == active.incident_id


@pytest.mark.asyncio
async def test_reconcile_skips_pre_mutation_policy_deny():
    store = IncidentStore(cooldown_seconds=0)
    active, _ = await store.upsert(incident())
    active.status = IncidentStatus.ESCALATED
    active.mutation_blocked = False
    active.escalation_reason = "Autonomous policy denied"

    assert await store.reconcile_post_execution_quarantine(active) is False
    assert await store.is_target_blocked(active.affected_service) is False


@pytest.mark.asyncio
async def test_pruning_skips_protected_oldest_and_removes_terminal_record():
    store = IncidentStore(cooldown_seconds=0, max_items=2)
    protected, _ = await store.upsert(incident("checkout"))

    terminal, _ = await store.upsert(incident("frontend"))
    resolved = await store.observe_recovery(
        terminal.incident_type, terminal.affected_service, 1
    )
    assert resolved is terminal

    newest, _ = await store.upsert(incident("product-reviews"))

    retained_ids = {item.incident_id for item in await store.list()}
    assert retained_ids == {protected.incident_id, newest.incident_id}
