from __future__ import annotations

import time
import asyncio
from typing import Any, Awaitable, Callable

import httpx

from .config import Settings


class TelemetryError(RuntimeError):
    pass


class TelemetryClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=10.0)

    async def query_range(self, query: str, step: int = 60) -> list[dict[str, Any]]:
        end = int(time.time())
        start = end - self.settings.lookback_minutes * 60
        try:
            response = await self.client.get(
                f"{self.settings.prometheus_url.rstrip('/')}/api/v1/query_range",
                params={"query": query, "start": start, "end": end, "step": step},
            )
            response.raise_for_status()
            body = response.json()
            if body.get("status") != "success":
                raise TelemetryError(str(body))
            return body.get("data", {}).get("result", [])
        except (httpx.HTTPError, ValueError) as exc:
            raise TelemetryError(f"Prometheus query failed: {exc}") from exc

    async def query(self, query: str) -> list[dict[str, Any]]:
        """Run an instant Prometheus query for exact current-window ratios."""

        try:
            response = await self.client.get(
                f"{self.settings.prometheus_url.rstrip('/')}/api/v1/query",
                params={"query": query},
            )
            response.raise_for_status()
            body = response.json()
            if body.get("status") != "success":
                raise TelemetryError(str(body))
            return body.get("data", {}).get("result", [])
        except (httpx.HTTPError, ValueError) as exc:
            raise TelemetryError(f"Prometheus query failed: {exc}") from exc

    async def search_logs(
        self, services: tuple[str, ...], terms: tuple[str, ...]
    ) -> list[dict[str, Any]] | None:
        query = " OR ".join(terms)
        service_query = " OR ".join(services)
        payload = {
            "size": 20,
            "sort": [{"@timestamp": "desc"}],
            "query": {"bool": {"must": [
                {"query_string": {"query": query, "fields": ["body", "message", "log"]}},
                {"query_string": {"query": service_query, "fields": ["resource.service.name", "service.name"]}},
            ]}},
            "_source": [
                "@timestamp",
                "body",
                "message",
                "traceId",
                "spanId",
                "resource.service.name",
                "resource.deployment.environment",
            ],
        }
        try:
            response = await self.client.post(
                f"{self.settings.opensearch_url.rstrip('/')}/{self.settings.opensearch_index}/_search", json=payload
            )
            response.raise_for_status()
            return response.json().get("hits", {}).get("hits", [])
        except (httpx.HTTPError, ValueError):
            return None

    async def find_traces(self, service: str, lookback: str = "30m") -> list[dict[str, Any]] | None:
        try:
            response = await self.client.get(
                f"{self.settings.jaeger_url.rstrip('/')}/api/traces",
                params={"service": service, "lookback": lookback, "limit": 20},
            )
            response.raise_for_status()
            return response.json().get("data", [])
        except (httpx.HTTPError, ValueError):
            return None

    async def _probe(
        self, name: str, operation: Callable[[], Awaitable[dict[str, Any]]]
    ) -> tuple[str, dict[str, Any]]:
        try:
            detail = await operation()
            return name, {"available": True, **detail}
        except (httpx.HTTPError, ValueError, TelemetryError) as exc:
            return name, {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    async def probe(self) -> dict[str, dict[str, Any]]:
        """Read-only connectivity check for the three runtime telemetry sources."""

        async def prometheus() -> dict[str, Any]:
            response = await self.client.get(
                f"{self.settings.prometheus_url.rstrip('/')}/api/v1/query", params={"query": "up"}
            )
            response.raise_for_status()
            body = response.json()
            if body.get("status") != "success":
                raise TelemetryError(str(body))
            return {"series": len(body.get("data", {}).get("result", []))}

        async def opensearch() -> dict[str, Any]:
            response = await self.client.get(
                f"{self.settings.opensearch_url.rstrip('/')}/_cluster/health"
            )
            response.raise_for_status()
            body = response.json()
            return {"status": body.get("status", "unknown")}

        async def jaeger() -> dict[str, Any]:
            response = await self.client.get(
                f"{self.settings.jaeger_url.rstrip('/')}/api/services"
            )
            response.raise_for_status()
            body = response.json()
            return {"services": len(body.get("data", []))}

        pairs = await asyncio.gather(
            self._probe("prometheus", prometheus),
            self._probe("opensearch", opensearch),
            self._probe("jaeger", jaeger),
        )
        return dict(pairs)

    async def close(self) -> None:
        await self.client.aclose()
