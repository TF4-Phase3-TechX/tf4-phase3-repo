from dataclasses import replace

import pytest

from app.config import Settings
from app.models import Evidence, Incident, IncidentStatus
from app.remediation import PolicyDenied, RemediationController


def incident(
    service="product-reviews",
    *,
    with_evidence=False,
    severity="high",
    confidence=.9,
):
    return Incident(
        incident_type="service_latency_spike", severity=severity, affected_service=service,
        confidence=confidence, suspected_root_cause="recent deploy", runbook_id="deployment-latency-rollback",
        recommended_action="rollback",
        evidence=[Evidence(source="prometheus", query="p95", window="5m", value=2000)]
        if with_evidence else [],
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
        self.lock_acquired = False
        self.lock_released = False

    def acquire_lock(self, deployment, incident_id, ttl):
        self.lock_acquired = True
        return True

    def release_lock(self, deployment, incident_id):
        self.lock_released = True

    def previous_template(self, deployment):
        return {"metadata": {"labels": {"version": "current"}}}, {"metadata": {"labels": {"version": "previous"}}}

    def patch_template(self, deployment, template):
        self.patches.append(template)

    def rollout_ready(self, deployment):
        return True


@pytest.mark.asyncio
async def test_failed_slo_verification_restores_original_template():
    adapter = FakeAdapter()

    results = iter([
        {"healthy": False, "p95_latency_ms": 2000},  # before
        {"healthy": False, "p95_latency_ms": 2000},  # action verification
        {"healthy": True, "p95_latency_ms": 300},    # rollback verification
    ])

    async def unhealthy_then_recovered(_):
        return next(results)

    controller = RemediationController(
        replace(
            Settings(), remediation_mode="live", verification_polls=1,
            rollback_verification_polls=1, verification_settle_seconds=0,
            verification_interval_seconds=0,
            verification_consecutive_healthy_polls=1,
        ), adapter=adapter, verifier=unhealthy_then_recovered,
    )
    item = incident()
    controller.request_approval(item)
    controller.approve(item)
    await controller.execute(item)
    assert item.status == IncidentStatus.ROLLED_BACK
    assert len(adapter.patches) == 2
    assert adapter.patches[-1]["metadata"]["labels"]["version"] == "current"
    assert item.rollback_verification_result["healthy"] is True
    assert adapter.lock_acquired is True
    assert adapter.lock_released is True


@pytest.mark.asyncio
async def test_preauthorized_policy_needs_no_per_incident_button_in_dry_run():
    controller = RemediationController(
        replace(
            Settings(), autonomous_remediation_enabled=True,
            remediation_mode="dry-run", allowed_deployments=("product-reviews",),
        )
    )
    item = incident(with_evidence=True)

    await controller.handle_incident(item)

    assert item.approval_status == "preauthorized_policy"
    assert item.policy_version == "m22-v1"
    assert item.execution_attempts == 1
    assert item.verification_result["mode"] == "dry-run"
    assert any(event.event == "autonomous_policy_evaluated" for event in item.audit_events)


@pytest.mark.asyncio
async def test_calibrated_gate_allows_observed_high_severity_acute_incident():
    controller = RemediationController(
        replace(
            Settings(),
            autonomous_remediation_enabled=True,
            remediation_mode="dry-run",
            allowed_deployments=("product-reviews",),
        )
    )
    item = incident(with_evidence=True, confidence=.742)

    await controller.handle_incident(item)

    assert item.approval_status == "preauthorized_policy"
    assert item.execution_attempts == 1
    assert item.verification_result["mode"] == "dry-run"


@pytest.mark.asyncio
async def test_calibrated_gate_still_denies_medium_severity_at_same_confidence():
    controller = RemediationController(
        replace(
            Settings(),
            autonomous_remediation_enabled=True,
            remediation_mode="dry-run",
            allowed_deployments=("product-reviews",),
        )
    )
    item = incident(
        with_evidence=True,
        severity="medium",
        confidence=.743,
    )

    await controller.handle_incident(item)

    assert item.status == IncidentStatus.ESCALATED
    assert item.execution_attempts == 0
    assert "severity_high" in item.escalation_reason


@pytest.mark.asyncio
async def test_autonomous_policy_fails_closed_without_evidence():
    controller = RemediationController(
        replace(Settings(), autonomous_remediation_enabled=True)
    )
    item = incident()

    await controller.handle_incident(item)

    assert item.status == IncidentStatus.ESCALATED
    assert item.mutation_blocked is True
    assert "evidence_present" in item.escalation_reason


@pytest.mark.asyncio
async def test_unverified_rollback_escalates_and_blocks_mutation():
    adapter = FakeAdapter()

    async def always_unhealthy(_):
        return {"healthy": False, "p95_latency_ms": 2000}

    controller = RemediationController(
        replace(
            Settings(), remediation_mode="live", verification_polls=1,
            rollback_verification_polls=1, verification_settle_seconds=0,
            verification_interval_seconds=0,
            verification_consecutive_healthy_polls=1,
        ), adapter=adapter, verifier=always_unhealthy,
    )
    item = incident()
    controller.request_approval(item)
    controller.approve(item)

    await controller.execute(item)

    assert item.status == IncidentStatus.ESCALATED
    assert item.mutation_blocked is True
    assert item.rollback_result["restored_original_template"] is True
    assert item.rollback_result["verified"] is False


@pytest.mark.asyncio
async def test_held_target_lease_denies_action_before_mutation():
    class HeldAdapter(FakeAdapter):
        def acquire_lock(self, deployment, incident_id, ttl):
            return False

    adapter = HeldAdapter()
    controller = RemediationController(
        replace(Settings(), remediation_mode="live"), adapter=adapter,
    )
    item = incident()
    controller.request_approval(item)
    controller.approve(item)

    with pytest.raises(PolicyDenied, match="Lease"):
        await controller.execute(item)

    assert adapter.patches == []


@pytest.mark.asyncio
async def test_verification_waits_for_post_action_metric_window(monkeypatch):
    adapter = FakeAdapter()
    sleeps = []

    async def record_sleep(seconds):
        sleeps.append(seconds)

    async def healthy(_):
        return {"healthy": True, "p95_latency_ms": 300}

    monkeypatch.setattr("app.remediation.asyncio.sleep", record_sleep)
    controller = RemediationController(
        replace(
            Settings(),
            verification_settle_seconds=30,
            verification_metric_window="15s",
            verification_interval_seconds=0,
            verification_consecutive_healthy_polls=1,
        ),
        adapter=adapter,
        verifier=healthy,
    )

    result = await controller._verification_window(
        adapter,
        "product-reviews",
        polls=1,
    )

    assert result["healthy"] is True
    assert sleeps == [30]


@pytest.mark.asyncio
async def test_trailing_consecutive_polls_ignore_stale_first_sample():
    adapter = FakeAdapter()
    outcomes = iter(
        [
            {"healthy": False, "p95_latency_ms": 7000},
            {"healthy": True, "p95_latency_ms": 100},
            {"healthy": True, "p95_latency_ms": 100},
        ]
    )

    async def stale_then_healthy(_):
        return next(outcomes)

    controller = RemediationController(
        replace(
            Settings(),
            verification_settle_seconds=0,
            verification_interval_seconds=0,
            verification_polls=3,
            verification_consecutive_healthy_polls=2,
        ),
        adapter=adapter,
        verifier=stale_then_healthy,
    )

    result = await controller._verification_window(
        adapter, "product-reviews", polls=3
    )

    assert result["poll_healthy"] == [False, True, True]
    assert result["healthy"] is True
    assert result["consecutive_required"] == 2


@pytest.mark.asyncio
async def test_unavailable_prometheus_evidence_denies_autonomous_policy():
    controller = RemediationController(
        replace(
            Settings(),
            autonomous_remediation_enabled=True,
            remediation_mode="dry-run",
            allowed_deployments=("product-reviews",),
        )
    )
    item = incident(with_evidence=False)
    item.evidence = [
        Evidence(
            source="prometheus",
            query="p95",
            window="5m",
            value="unavailable",
        )
    ]

    await controller.handle_incident(item)

    assert item.status == IncidentStatus.ESCALATED
    assert "evidence_present" in (item.escalation_reason or "")
