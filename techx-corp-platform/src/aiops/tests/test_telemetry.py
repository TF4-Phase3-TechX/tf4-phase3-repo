import json
from dataclasses import replace

import httpx
import pytest

from app.config import Settings
from app.telemetry import TelemetryClient


@pytest.mark.asyncio
async def test_prometheus_range_query_contract():
    async def handler(request: httpx.Request):
        assert request.url.path == "/api/v1/query_range"
        assert "query" in request.url.params
        return httpx.Response(200, json={"status": "success", "data": {"result": [{"values": [[1, "12"]]}]}})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    telemetry = TelemetryClient(replace(Settings(), prometheus_url="http://prometheus"), http)
    result = await telemetry.query_range("up")
    assert result[0]["values"][0][1] == "12"
    await telemetry.close()


@pytest.mark.asyncio
async def test_opensearch_query_is_bounded_to_log_index_and_source_fields():
    async def handler(request: httpx.Request):
        assert request.url.path == "/otel-logs-*/_search"
        payload = json.loads(request.content)
        assert payload["size"] == 20
        assert "body" in payload["_source"]
        assert "resource.service.name" in payload["_source"]
        assert "resource.deployment.environment" in payload["_source"]
        return httpx.Response(200, json={"hits": {"hits": [{"_id": "one"}]}})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    telemetry = TelemetryClient(replace(Settings(), opensearch_url="http://opensearch"), http)
    result = await telemetry.search_logs(("llm",), ("timeout",))
    assert result == [{"_id": "one"}]
    await telemetry.close()


@pytest.mark.asyncio
async def test_secondary_source_failure_is_unavailable_not_healthy_empty():
    async def handler(_: httpx.Request):
        return httpx.Response(503)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    telemetry = TelemetryClient(replace(Settings(), opensearch_url="http://opensearch"), http)
    assert await telemetry.search_logs(("llm",), ("timeout",)) is None
    await telemetry.close()


@pytest.mark.asyncio
async def test_read_only_observability_probe_uses_documented_api_paths():
    async def handler(request: httpx.Request):
        if request.url.host == "prometheus":
            assert request.url.path == "/api/v1/query"
            return httpx.Response(200, json={"status": "success", "data": {"result": [{"metric": {}}]}})
        if request.url.host == "opensearch":
            assert request.url.path == "/_cluster/health"
            return httpx.Response(200, json={"status": "green"})
        assert request.url.host == "jaeger"
        assert request.url.path == "/jaeger/ui/api/services"
        return httpx.Response(200, json={"data": ["checkout", "cart"]})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    telemetry = TelemetryClient(
        replace(
            Settings(),
            prometheus_url="http://prometheus",
            opensearch_url="http://opensearch",
            jaeger_url="http://jaeger/jaeger/ui",
        ),
        http,
    )
    status = await telemetry.probe()
    assert status == {
        "prometheus": {"available": True, "series": 1},
        "opensearch": {"available": True, "status": "green"},
        "jaeger": {"available": True, "services": 2},
    }
    await telemetry.close()
