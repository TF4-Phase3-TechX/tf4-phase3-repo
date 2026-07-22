from dataclasses import replace

import pytest

from app.config import Settings
from app.models import Incident, IncidentStatus
from app.remediation import PolicyDenied, RemediationController


def incident(service="product-reviews"):
    return Incident(
        incident_type="service_latency_spike", severity="high", affected_service=service,
        confidence=.9, suspected_root_cause="recent deploy", runbook_id="deployment-latency-rollback",
        recommended_action="rollback",
    )


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


class FakeAdapter:
    def __init__(self):
        self.patches = []

    def previous_template(self, deployment):
        return {"metadata": {"labels": {"version": "current"}}}, {"metadata": {"labels": {"version": "previous"}}}

    def patch_template(self, deployment, template):
        self.patches.append(template)

    def rollout_ready(self, deployment):
        return True


@pytest.mark.asyncio
async def test_failed_slo_verification_restores_original_template():
    adapter = FakeAdapter()

    async def unhealthy(_):
        return {"healthy": False, "p95_latency_ms": 2000}

    controller = RemediationController(replace(Settings(), remediation_mode="live"), adapter=adapter, verifier=unhealthy)
    item = incident()
    controller.request_approval(item)
    controller.approve(item)
    await controller.execute(item)
    assert item.status == IncidentStatus.ROLLED_BACK
    assert len(adapter.patches) == 2
    assert adapter.patches[-1]["metadata"]["labels"]["version"] == "current"
