from __future__ import annotations

import asyncio
import hmac
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .config import Settings
from .detection import Detector, latency_query, values
from .remediation import PolicyDenied, RemediationController
from .store import IncidentStore
from .summary import IncidentSummaryGenerator
from .telemetry import TelemetryClient
from .worker import AIOpsWorker

logging.basicConfig(level=logging.INFO, format="%(message)s")
settings = Settings()
store = IncidentStore(settings.cooldown_seconds)
telemetry = TelemetryClient(settings)


async def verify_service_slo(service: str) -> dict[str, object]:
    latency_series = await telemetry.query_range(
        latency_query(service, settings.namespace)
    )
    points = values(latency_series[0]) if latency_series else []
    current = points[-1] if points else None
    guard_query = (
        'sum(rate(traces_span_metrics_calls_total{service_name=~"frontend|checkout",span_kind="SPAN_KIND_SERVER",k8s_namespace_name="'
        + settings.namespace
        + '",status_code="STATUS_CODE_ERROR"}[5m])) '
        '/ clamp_min(sum(rate(traces_span_metrics_calls_total{service_name=~"frontend|checkout",span_kind="SPAN_KIND_SERVER",k8s_namespace_name="'
        + settings.namespace
        + '"}[5m])), 0.000001)'
    )
    guard_series = await telemetry.query_range(guard_query)
    guard_points = values(guard_series[0]) if guard_series else []
    guard_error_rate = guard_points[-1] if guard_points else None
    return {
        "healthy": current is not None
        and current < settings.latency_threshold_ms
        and guard_error_rate is not None
        and guard_error_rate < settings.verification_error_rate_threshold,
        "p95_latency_ms": current,
        "threshold_ms": settings.latency_threshold_ms,
        "checkout_storefront_error_rate": guard_error_rate,
        "checkout_storefront_error_rate_threshold": settings.verification_error_rate_threshold,
    }


remediation = RemediationController(settings, verifier=verify_service_slo)
worker = AIOpsWorker(settings, telemetry, Detector(settings), store, remediation)
summary_generator = IncidentSummaryGenerator(
    settings.grafana_url,
    settings.opensearch_datasource_uid,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(worker.run())
    yield
    worker.stop()
    task.cancel()
    await telemetry.close()


app = FastAPI(title="TF4 AIOps", version="0.1.0", lifespan=lifespan)


def require_token(authorization: str | None = Header(default=None)) -> None:
    expected = settings.approval_token
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not expected or not hmac.compare_digest(expected, supplied):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid approval bearer token required",
        )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    if not worker.running:
        raise HTTPException(503, "Worker is starting")
    return {"status": "ready"}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/v1/telemetry/status")
async def telemetry_status():
    return await telemetry.probe()


@app.get("/v1/incidents")
async def list_incidents():
    return await store.list()


@app.get("/v1/incidents/{incident_id}")
async def get_incident(incident_id: str):
    incident = await store.get(incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    return incident


@app.get("/v1/incidents/{incident_id}/summary", response_class=PlainTextResponse)
async def get_incident_summary(incident_id: str):
    incident = await store.get(incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    return PlainTextResponse(
        summary_generator.generate(incident),
        media_type="text/markdown; charset=utf-8",
    )


@app.post("/v1/incidents/{incident_id}/approve", dependencies=[Depends(require_token)])
async def approve(incident_id: str):
    incident = await store.get(incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    try:
        remediation.approve(incident)
        await remediation.execute(incident)
    except PolicyDenied as exc:
        raise HTTPException(409, str(exc)) from exc
    return incident


@app.post("/v1/incidents/{incident_id}/reject", dependencies=[Depends(require_token)])
async def reject(incident_id: str):
    incident = await store.get(incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    remediation.reject(incident)
    return incident


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080)
