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
async def test_single_observed_service_can_trigger_from_multiservice_error_trace():
    class TraceTelemetry(EmptyTelemetry):
        async def find_traces(self, service):
            return [
                {
                    "traceID": "trace-cross-service",
                    "processes": {"p1": {"serviceName": "checkout"}},
                    "spans": [
                        {
                            "spanID": "client",
                            "processID": "p1",
                            "operationName": "Charge",
                            "startTime": 1,
                            "duration": 10,
                            "tags": [
                                {"key": "span.kind", "value": "client"},
                                {"key": "peer.service", "value": "payment"},
                                {"key": "error", "value": True},
                            ],
                            "references": [],
                        }
                    ],
                }
            ]

    worker = AIOpsWorker(
        replace(
            Settings(),
            services=("checkout",),
            generic_signal_services=("checkout",),
            llm_services=(),
            llm_log_services=(),
            rca_enabled=True,
        ),
        TraceTelemetry(),
        SingleServiceMultiSignalDetector(),
        IncidentStore(cooldown_seconds=0),
        remediation=RecordingRemediation(),
    )
    await worker.poll_once()
    items = await worker.store.list()
    assert items
    assert any(item.suspected_root_service == "payment" for item in items)


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
    assert any(
        item.affected_service == "checkout"
        and item.suspected_root_service == "payment"
        for item in items
    )
    assert "checkout" in rem.targets
    assert set(rem.targets) <= {"checkout", "payment"}


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


@pytest.mark.asyncio
async def test_episode_update_aggregates_all_signals_before_marking_recovered():
    class MixedSignalDetector(SingleServiceMultiSignalDetector):
        def error_rate(self, service, series, query, **kwargs):
            return Decision(
                anomalous=False,
                breached=False,
                incident_type="service_error_rate_spike",
                service=service,
            )

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
        MixedSignalDetector(),
        IncidentStore(cooldown_seconds=0),
        remediation=RecordingRemediation(),
    )
    await worker.poll_once()
    state = worker._episode.state("checkout")
    assert state is not None
    assert state.currently_anomalous is True


@pytest.mark.asyncio
async def test_recovered_unseen_root_remains_in_rca_candidate_universe():
    worker = AIOpsWorker(
        replace(
            Settings(),
            services=("checkout", "frontend"),
            generic_signal_services=("checkout", "frontend"),
            llm_services=(),
            llm_log_services=(),
            rca_enabled=True,
        ),
        EmptyTelemetry(),
        DualServiceDetector(),
        IncidentStore(cooldown_seconds=0),
        remediation=RecordingRemediation(),
    )
    worker._episode.observe(
        "novel-root", anomalous=True, breached=True
    )
    worker._episode.observe(
        "novel-root", anomalous=False, breached=False
    )
    decisions = [
        Decision(
            anomalous=True,
            breached=True,
            incident_type="service_error_rate_spike",
            service=service,
            confidence=0.8,
        )
        for service in ("checkout", "frontend")
    ]
    result, skipped, _ = await worker._run_cross_service_rca(decisions)
    assert skipped is None
    assert result is not None
    assert "novel-root" in {candidate.service for candidate in result.candidates}


@pytest.mark.asyncio
async def test_store_clears_stale_rca_when_latest_observation_abstains():
    store = IncidentStore(cooldown_seconds=0)
    base = Incident(
        incident_type="service_error_rate_spike",
        severity="high",
        affected_service="checkout",
        confidence=0.9,
        suspected_root_cause="local",
        suspected_root_service="payment",
        rca_result={
            "model_version": "m26-v1",
            "attribution_status": "attributed",
            "suspected_root_service": "payment",
            "confidence": 0.9,
            "score_margin": 0.2,
            "explanation": "payment",
            "candidates": [],
            "analysis_started_at": "2026-07-20T00:00:00Z",
            "analysis_ended_at": "2026-07-20T00:00:01Z",
        },
        runbook_id="observe-and-escalate",
        recommended_action="Investigate",
    )
    stored, created = await store.upsert(base)
    assert created is True
    latest = base.model_copy(
        update={
            "incident_id": "new-observation",
            "suspected_root_service": None,
            "rca_result": None,
        }
    )
    stored, created = await store.upsert(latest)
    assert created is False
    assert stored.suspected_root_service is None
    assert stored.rca_result is None
