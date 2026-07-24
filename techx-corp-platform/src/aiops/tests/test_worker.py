import asyncio
import time
from dataclasses import replace

import pytest
from prometheus_client import REGISTRY

from app.availability import AvailabilitySnapshot
from app.config import Settings
from app.detection import Detector
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


class BlockingDetector(RecordingDetector):
    @staticmethod
    def latency(service, series, query):
        time.sleep(0.1)
        return Decision(
            anomalous=False,
            incident_type="service_latency_spike",
            service=service,
        )


@pytest.mark.asyncio
async def test_cpu_bound_detection_does_not_block_health_event_loop():
    worker = AIOpsWorker(
        replace(
            Settings(),
            services=("checkout",),
            llm_services=(),
            llm_log_services=(),
        ),
        EmptyTelemetry(),
        BlockingDetector(),
        IncidentStore(),
        remediation=object(),
    )

    poll = asyncio.create_task(worker.poll_once())
    # This timer represents a health/readiness request sharing FastAPI's event
    # loop. It must run while synchronous detector CPU work is in progress.
    await asyncio.wait_for(asyncio.sleep(0.02), timeout=0.08)
    assert not poll.done()
    await poll


@pytest.mark.asyncio
async def test_missing_llm_metric_reports_coverage_for_expected_caller():
    settings = replace(
        Settings(),
        services=("frontend", "checkout"),
        llm_services=("product-reviews",),
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


class MultiCallerTelemetry(EmptyTelemetry):
    async def query_range(self, query):
        if "app_llm_errors_total" not in query:
            return []
        values = [[index, str(value)] for index, value in enumerate([0.01] * 8 + [0.08])]
        return [
            {"metric": {"service_name": "product-reviews"}, "values": values},
            {"metric": {"service_name": "shopping-copilot"}, "values": values},
        ]

    async def search_logs(self, services, terms):
        return [
            {"_source": {"resource.service.name": "shopping-copilot"}},
            {"_source": {"resource": {"service": {"name": "product-reviews"}}}},
        ]


@pytest.mark.asyncio
async def test_llm_incident_owner_is_discovered_per_metric_series():
    detector = RecordingDetector()
    worker = AIOpsWorker(
        replace(Settings(), services=(), llm_services=("product-reviews",)),
        MultiCallerTelemetry(),
        detector,
        IncidentStore(),
        remediation=object(),
    )

    await worker.poll_once()

    assert detector.llm_services == ["product-reviews", "shopping-copilot"]


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


class DownAvailability:
    @staticmethod
    def snapshot(service):
        return AvailabilitySnapshot(
            service=service,
            state="down",
            desired_replicas=1,
            available_replicas=0,
            ready_replicas=0,
            updated_replicas=1,
            reason="no_available_or_ready_replicas",
        )


@pytest.mark.asyncio
async def test_confirmed_service_down_creates_pageable_incident():
    settings = replace(
        Settings(),
        services=("checkout",),
        llm_services=(),
        llm_log_services=(),
        availability_sustained_polls=2,
    )
    recorder = ApprovalRecorder()
    store = IncidentStore(cooldown_seconds=0)
    counter_labels = {
        "incident_type": "service_availability",
        "service": "checkout",
        "severity": "critical",
    }
    created_before = REGISTRY.get_sample_value(
        "aiops_incidents_created_total", counter_labels
    ) or 0
    worker = AIOpsWorker(
        settings,
        EmptyTelemetry(),
        Detector(settings),
        store,
        remediation=recorder,
        availability=DownAvailability(),
    )

    await worker.poll_once()
    assert await store.list() == []

    await worker.poll_once()
    incidents = await store.list()

    assert len(incidents) == 1
    assert incidents[0].incident_type == "service_availability"
    assert incidents[0].affected_service == "checkout"
    assert incidents[0].severity == "high"
    assert incidents[0].execution_attempts == 0
    assert recorder.incident_ids == [incidents[0].incident_id]
    assert REGISTRY.get_sample_value(
        "aiops_incidents_created_total", counter_labels
    ) == created_before + 1
