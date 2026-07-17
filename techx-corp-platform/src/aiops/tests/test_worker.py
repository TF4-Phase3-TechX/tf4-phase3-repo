from dataclasses import replace

import pytest
from prometheus_client import REGISTRY

from app.config import Settings
from app.models import Decision, IncidentStatus
from app.store import IncidentStore
from app.worker import AIOpsWorker


class EmptyTelemetry:
    async def search_logs(self, services, terms):
        return []

    async def query_range(self, query):
        return []

    async def find_traces(self, service):
        return []


class RecordingDetector:
    def __init__(self):
        self.llm_services = []

    @staticmethod
    def latency(service, series, query):
        return Decision(anomalous=False, incident_type="service_latency_spike", service=service)

    @staticmethod
    def error_rate(service, series, query):
        return Decision(anomalous=False, incident_type="service_error_rate_spike", service=service)

    def llm_error(self, service, series, query, log_count):
        self.llm_services.append(service)
        return Decision(anomalous=False, incident_type="llm_timeout_error", service=service)


@pytest.mark.asyncio
async def test_global_llm_metric_creates_one_decision_for_configured_owner():
    settings = replace(
        Settings(),
        services=("frontend", "checkout"),
        llm_services=("llm", "product-reviews"),
        llm_signal_owner="product-reviews",
    )
    detector = RecordingDetector()
    worker = AIOpsWorker(
        settings,
        EmptyTelemetry(),
        detector,
        IncidentStore(),
        remediation=object(),
    )

    await worker.poll_once()

    assert detector.llm_services == ["product-reviews"]


class LifecycleDetector:
    def __init__(self):
        self.decisions = [
            Decision(anomalous=True, breached=True, incident_type="llm_timeout_error", service="product-reviews"),
            Decision(anomalous=False, breached=False, incident_type="llm_timeout_error", service="product-reviews"),
            Decision(anomalous=False, breached=False, incident_type="llm_timeout_error", service="product-reviews"),
            Decision(anomalous=True, breached=True, incident_type="llm_timeout_error", service="product-reviews"),
        ]

    def llm_error(self, service, series, query, log_count):
        return self.decisions.pop(0)


class ApprovalRecorder:
    def __init__(self):
        self.incident_ids = []

    def request_approval(self, incident):
        self.incident_ids.append(incident.incident_id)
        incident.status = IncidentStatus.AWAITING_APPROVAL
        incident.approval_status = "pending"


@pytest.mark.asyncio
async def test_worker_breach_recover_breach_notifies_for_two_incidents():
    settings = replace(Settings(), services=(), recovery_polls=2)
    recorder = ApprovalRecorder()
    worker = AIOpsWorker(
        settings,
        EmptyTelemetry(),
        LifecycleDetector(),
        IncidentStore(cooldown_seconds=0),
        remediation=recorder,
    )

    for _ in range(4):
        await worker.poll_once()

    assert len(recorder.incident_ids) == 2
    assert recorder.incident_ids[0] != recorder.incident_ids[1]


class DegradedEnrichmentTelemetry(EmptyTelemetry):
    async def search_logs(self, services, terms):
        return None

    async def find_traces(self, service):
        return None


@pytest.mark.asyncio
async def test_worker_counts_opensearch_and_jaeger_poll_failures():
    labels = lambda source: {"source": source}
    opensearch_before = REGISTRY.get_sample_value(
        "aiops_telemetry_poll_failures_total", labels("opensearch")
    ) or 0
    jaeger_before = REGISTRY.get_sample_value(
        "aiops_telemetry_poll_failures_total", labels("jaeger")
    ) or 0
    worker = AIOpsWorker(
        replace(Settings(), services=()),
        DegradedEnrichmentTelemetry(),
        LifecycleDetector(),
        IncidentStore(cooldown_seconds=0),
        remediation=ApprovalRecorder(),
    )

    await worker.poll_once()

    assert REGISTRY.get_sample_value(
        "aiops_telemetry_poll_failures_total", labels("opensearch")
    ) == opensearch_before + 1
    assert REGISTRY.get_sample_value(
        "aiops_telemetry_poll_failures_total", labels("jaeger")
    ) == jaeger_before + 1
