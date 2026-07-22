from dataclasses import replace

import pytest

from app.config import Settings
from app.models import Incident, IncidentStatus
from app.remediation import AUTONOMOUS_INCIDENT_TYPES, PolicyDenied, RemediationController


def incident(service="product-reviews", confidence=0.9):
    return Incident(
        incident_type="service_latency_spike", severity="high", affected_service=service,
        confidence=confidence, suspected_root_cause="recent deploy",
        runbook_id="deployment-latency-rollback", recommended_action="rollback",
    )


class FakeAdapter:
    def __init__(self):
        self.patches = []

    def previous_template(self, deployment):
        return (
            {"metadata": {"labels": {"version": "current"}}},
            {"metadata": {"labels": {"version": "previous"}}},
        )

    def patch_template(self, deployment, template):
        self.patches.append(template)

    def rollout_ready(self, deployment):
        return True


# ---------------------------------------------------------------------------
# Human-approval path (preserved, unmodified)
# ---------------------------------------------------------------------------


def test_approval_is_required_and_bound_to_state():
    controller = RemediationController(Settings())
    item = incident()
    with pytest.raises(PolicyDenied):
        controller.approve(item)
    controller.request_approval(item)
    controller.approve(item)
    assert item.status == IncidentStatus.APPROVED


@pytest.mark.asyncio
async def test_dry_run_never_claims_recovery():
    controller = RemediationController(replace(Settings(), remediation_mode="dry-run"))
    item = incident()
    controller.request_approval(item)
    controller.approve(item)
    await controller.execute(item)
    assert item.status == IncidentStatus.ESCALATED
    assert item.verification_result["mode"] == "dry-run"


@pytest.mark.asyncio
async def test_target_outside_allowlist_is_denied():
    controller = RemediationController(Settings())
    item = incident("flagd")
    controller.request_approval(item)
    controller.approve(item)
    with pytest.raises(PolicyDenied):
        await controller.execute(item)


@pytest.mark.asyncio
async def test_failed_slo_verification_restores_original_template():
    adapter = FakeAdapter()

    async def unhealthy(_):
        return {"healthy": False, "p95_latency_ms": 2000}

    controller = RemediationController(
        replace(Settings(), remediation_mode="live"), adapter=adapter, verifier=unhealthy
    )
    item = incident()
    controller.request_approval(item)
    controller.approve(item)
    await controller.execute(item)
    assert item.status == IncidentStatus.ROLLED_BACK
    assert len(adapter.patches) == 2
    assert adapter.patches[-1]["metadata"]["labels"]["version"] == "current"


# ---------------------------------------------------------------------------
# Autonomous execution tests (pre-authorized policy gate)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_autonomous_execute_success_resolves_incident():
    """Happy path: policy gate approves → rollback → SLO healthy → resolved."""
    adapter = FakeAdapter()

    async def healthy(_):
        return {"healthy": True, "latency_ok": True}

    settings = replace(Settings(), remediation_mode="live")
    controller = RemediationController(settings, adapter=adapter, verifier=healthy)
    item = incident(confidence=0.92)

    eligible, reason = controller.should_auto_execute(item)
    assert eligible, f"Expected policy gate to approve, got: {reason}"

    await controller.autonomous_execute(item)
    assert item.status == IncidentStatus.RESOLVED
    assert item.auto_approved is True
    assert item.approval_status == "auto_approved"
    assert any(e.event == "autonomous_remediation_verified" for e in item.audit_events)
    assert len(adapter.patches) >= 1


@pytest.mark.asyncio
async def test_autonomous_execute_low_confidence_denied():
    """Policy gate must block incidents below the confidence threshold."""
    controller = RemediationController(replace(Settings(), remediation_mode="live"))
    item = incident(confidence=0.50)  # threshold default 0.75

    eligible, reason = controller.should_auto_execute(item)
    assert not eligible
    assert "confidence" in reason

    await controller.autonomous_execute(item)
    assert item.status == IncidentStatus.ESCALATED
    assert item.auto_approved is False
    assert any(e.event == "autonomous_policy_denied" for e in item.audit_events)


@pytest.mark.asyncio
async def test_autonomous_execute_verify_fail_triggers_rollback():
    """SLO verification failure must restore original template and mark ROLLED_BACK."""
    adapter = FakeAdapter()

    async def unhealthy(_):
        return {"healthy": False, "latency_ok": False}

    settings = replace(Settings(), remediation_mode="live")
    controller = RemediationController(settings, adapter=adapter, verifier=unhealthy)
    item = incident(confidence=0.88)

    await controller.autonomous_execute(item)
    assert item.status == IncidentStatus.ROLLED_BACK
    assert item.rollback_result is not None
    assert item.rollback_result["restored_original_template"] is True
    assert item.rollback_result.get("policy") == "autonomous"
    # Two patches: rollback to previous + restore to original
    assert len(adapter.patches) == 2
    assert adapter.patches[-1]["metadata"]["labels"]["version"] == "current"
    assert any(e.event == "autonomous_remediation_rolled_back" for e in item.audit_events)


@pytest.mark.asyncio
async def test_autonomous_execute_cooldown_blocks_repeat():
    """After a successful autonomous execution, cooldown must block a second attempt."""
    adapter = FakeAdapter()

    async def healthy(_):
        return {"healthy": True}

    settings = replace(Settings(), remediation_mode="live", cooldown_seconds=600)
    controller = RemediationController(settings, adapter=adapter, verifier=healthy)

    # First execution — should succeed
    item1 = incident(confidence=0.92)
    await controller.autonomous_execute(item1)
    assert item1.status == IncidentStatus.RESOLVED

    # Second attempt on same target — cooldown must block
    item2 = incident(confidence=0.92)
    eligible, reason = controller.should_auto_execute(item2)
    assert not eligible
    assert "cooldown" in reason

    await controller.autonomous_execute(item2)
    assert item2.status == IncidentStatus.ESCALATED
    assert any(e.event == "autonomous_policy_denied" for e in item2.audit_events)


@pytest.mark.asyncio
async def test_autonomous_execute_blast_radius_blocks_second_attempt():
    """Blast-radius guard: execution_attempts > 0 must block autonomous retry loop."""
    controller = RemediationController(replace(Settings(), remediation_mode="live"))
    item = incident(confidence=0.92)
    item.execution_attempts = 1  # simulate a previous attempt

    eligible, reason = controller.should_auto_execute(item)
    assert not eligible
    assert "blast-radius" in reason

    await controller.autonomous_execute(item)
    assert item.status == IncidentStatus.ESCALATED
