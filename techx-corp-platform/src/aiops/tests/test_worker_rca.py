import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from app.config import Settings
from app.models import Decision, Incident, IncidentStatus
from app.store import IncidentStore
from app.worker import AIOpsWorker


class EmptyTelemetry:
    async def search_logs(self, services, terms):
        return []

    async def query_range(self, query):
        return []

    async def query(self, query):
        return []

    async def find_traces(self, service):
        return []


class RecordingRemediation:
    def __init__(self):
        self.targets: list[str] = []

    def request_approval(self, incident: Incident):
        self.targets.append(incident.affected_service)
        incident.status = IncidentStatus.AWAITING_APPROVAL
        incident.approval_status = "pending"


class DualServiceDetector:
    """Two signals on checkout + one on payment → cross-service RCA."""

    def latency(self, service, series, query):
        if service == "checkout":
            return Decision(
                anomalous=True,
                breached=True,
                incident_type="service_latency_spike",
                service="checkout",
                confidence=0.8,
                severity="medium",
                root_cause="checkout latency",
                candidates=[{"service": "checkout", "score": 0.8, "signals": {"metric": 1}}],
                runbook_id="observe-and-escalate",
                recommended_action="Investigate",
            )
        return Decision(anomalous=False, incident_type="service_latency_spike", service=service)

    def error_rate(self, service, series, query, **kwargs):
        if service == "checkout":
            return Decision(
                anomalous=True,
                breached=True,
                incident_type="service_error_rate_spike",
                service="checkout",
                confidence=0.85,
                severity="high",
                root_cause="checkout errors",
                candidates=[{"service": "checkout", "score": 0.85, "signals": {"metric": 1}}],
                runbook_id="observe-and-escalate",
                recommended_action="Investigate",
            )
        if service == "payment":
            return Decision(
                anomalous=True,
                breached=True,
                incident_type="service_error_rate_spike",
                service="payment",
                confidence=0.9,
                severity="high",
                root_cause="payment errors",
                candidates=[{"service": "payment", "score": 0.9, "signals": {"metric": 1}}],
                runbook_id="observe-and-escalate",
                recommended_action="Investigate",
            )
        return Decision(anomalous=False, incident_type="service_error_rate_spike", service=service)

    def llm_error(self, service, series, query, log_count):
        return Decision(anomalous=False, incident_type="llm_timeout_error", service=service)


class SingleServiceMultiSignalDetector:
    def latency(self, service, series, query):
        if service == "checkout":
            return Decision(
                anomalous=True,
                breached=True,
                incident_type="service_latency_spike",
                service="checkout",
                confidence=0.8,
                root_cause="latency",
                candidates=[{"service": "checkout", "score": 0.8, "signals": {}}],
                runbook_id="observe-and-escalate",
                recommended_action="x",
            )
        return Decision(anomalous=False, incident_type="service_latency_spike", service=service)

    def error_rate(self, service, series, query, **kwargs):
        if service == "checkout":
            return Decision(
                anomalous=True,
                breached=True,
                incident_type="service_error_rate_spike",
                service="checkout",
                confidence=0.85,
                root_cause="errors",
                candidates=[{"service": "checkout", "score": 0.85, "signals": {}}],
                runbook_id="observe-and-escalate",
                recommended_action="x",
            )
        return Decision(anomalous=False, incident_type="service_error_rate_spike", service=service)

    def llm_error(self, service, series, query, log_count):
        return Decision(anomalous=False, incident_type="llm_timeout_error", service=service)


async def _await_remediation(worker: AIOpsWorker) -> None:
    if worker._remediation_tasks:
        await asyncio.gather(*list(worker._remediation_tasks), return_exceptions=True)


@pytest.mark.asyncio
async def test_two_signals_one_service_does_not_trigger_cross_service_rca():
    rem = RecordingRemediation()
    worker = AIOpsWorker(
        replace(
            Settings(),
            services=("checkout",),
            generic_signal_services=("checkout",),
            llm_services=(),
            llm_log_services=(),
            rca_enabled=True,
        ),
        EmptyTelemetry(),
        SingleServiceMultiSignalDetector(),
        IncidentStore(cooldown_seconds=0),
        remediation=rem,
    )
    await worker.poll_once()
    await _await_remediation(worker)
    items = await worker.store.list()
    assert items
    # Skipped because only one distinct service
    assert any("rca_skipped=single_service" in i.suspected_root_cause for i in items)
    assert all(i.suspected_root_service is None for i in items)


@pytest.mark.asyncio
async def test_two_distinct_services_trigger_rca_and_keep_remediation_target():
    rem = RecordingRemediation()
    worker = AIOpsWorker(
        replace(
            Settings(),
            services=("checkout", "payment"),
            generic_signal_services=("checkout", "payment"),
            llm_services=(),
            llm_log_services=(),
            rca_enabled=True,
        ),
        EmptyTelemetry(),
        DualServiceDetector(),
        IncidentStore(cooldown_seconds=0),
        remediation=rem,
    )
    await worker.poll_once()
    await _await_remediation(worker)
    items = await worker.store.list()
    assert len(items) >= 2
    # At least one incident enriched with cross-service root
    assert any(i.suspected_root_service == "payment" for i in items)
    assert any(i.rca_result is not None for i in items)
    # Remediation still targets detector-owned affected services
    assert set(rem.targets) <= {"checkout", "payment"}
    assert "payment" in rem.targets or "checkout" in rem.targets
    for target in rem.targets:
        assert target in {"checkout", "payment"}


@pytest.mark.asyncio
async def test_rca_timeout_does_not_block_incident_creation():
    rem = RecordingRemediation()

    class SlowTelemetry(EmptyTelemetry):
        async def find_traces(self, service):
            await asyncio.sleep(1.0)
            return []

    worker = AIOpsWorker(
        replace(
            Settings(),
            services=("checkout", "payment"),
            generic_signal_services=("checkout", "payment"),
            llm_services=(),
            llm_log_services=(),
            rca_enabled=True,
            rca_timeout_seconds=0.05,
        ),
        SlowTelemetry(),
        DualServiceDetector(),
        IncidentStore(cooldown_seconds=0),
        remediation=rem,
    )
    await asyncio.wait_for(worker.poll_once(), timeout=2.0)
    await _await_remediation(worker)
    items = await worker.store.list()
    assert items
    assert any("rca_skipped=timeout" in i.suspected_root_cause for i in items)


@pytest.mark.asyncio
async def test_rca_exception_does_not_block_incident_creation(monkeypatch):
    rem = RecordingRemediation()
    worker = AIOpsWorker(
        replace(
            Settings(),
            services=("checkout", "payment"),
            generic_signal_services=("checkout", "payment"),
            llm_services=(),
            llm_log_services=(),
            rca_enabled=True,
        ),
        EmptyTelemetry(),
        DualServiceDetector(),
        IncidentStore(cooldown_seconds=0),
        remediation=rem,
    )

    async def boom(*args, **kwargs):
        raise RuntimeError("rca boom")

    monkeypatch.setattr(worker, "_run_cross_service_rca", boom)
    await worker.poll_once()
    await _await_remediation(worker)
    items = await worker.store.list()
    assert items


@pytest.mark.asyncio
async def test_legacy_summary_still_renders_with_rca_fields():
    from app.summary import IncidentSummaryGenerator

    rem = RecordingRemediation()
    worker = AIOpsWorker(
        replace(
            Settings(),
            services=("checkout", "payment"),
            generic_signal_services=("checkout", "payment"),
            llm_services=(),
            llm_log_services=(),
        ),
        EmptyTelemetry(),
        DualServiceDetector(),
        IncidentStore(cooldown_seconds=0),
        remediation=rem,
    )
    await worker.poll_once()
    items = await worker.store.list()
    summary = IncidentSummaryGenerator("http://grafana", "os").generate(items[0])
    assert "RCA candidates" in summary
    assert "Cross-service suspected root" in summary
    assert "does not retarget remediation" in summary
