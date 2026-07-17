from dataclasses import replace

import pytest

from app.config import Settings
from app.models import Decision
from app.store import IncidentStore
from app.worker import AIOpsWorker


class HealthyTelemetry:
    async def search_logs(self, services, terms):
        return []

    async def query_range(self, query):
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
        HealthyTelemetry(),
        detector,
        IncidentStore(),
        remediation=object(),
    )

    await worker.poll_once()

    assert detector.llm_services == ["product-reviews"]
