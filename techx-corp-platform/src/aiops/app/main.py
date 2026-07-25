from __future__ import annotations

import asyncio
import hmac
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .availability import KubernetesAvailabilityClient
from .config import Settings
from .detection import Detector, latency_query, values
from .remediation import PolicyDenied, RemediationController
from .store import IncidentStore
from .summary import IncidentSummaryGenerator
from .telemetry import TelemetryClient
from .verification import (
    evaluate_target_slo,
    target_error_rate_query,
    target_request_count_query,
)
from .worker import AIOpsWorker

logging.basicConfig(level=logging.INFO, format="%(message)s")
settings = Settings()
store = IncidentStore(settings.cooldown_seconds)
telemetry = TelemetryClient(settings)


async def verify_service_slo(service: str) -> dict[str, object]:
    window = settings.verification_metric_window
    latency_series = await telemetry.query_range(
        latency_query(service, settings.namespace, window)
    )
    points = values(latency_series[0]) if latency_series else []
    current = points[-1] if points else None
    guard_series = await telemetry.query_range(
        target_error_rate_query(service, settings.namespace, window)
    )
    guard_points = values(guard_series[0]) if guard_series else []
    target_error_rate = guard_points[-1] if guard_points else None
    volume_series = await telemetry.query_range(
        target_request_count_query(service, settings.namespace, window)
    )
    volume_points = values(volume_series[0]) if volume_series else []
    request_count = volume_points[-1] if volume_points else None
    return evaluate_target_slo(
        service=service,
        p95_latency_ms=current,
        latency_threshold_ms=settings.latency_threshold_ms,
        target_error_rate=target_error_rate,
        error_rate_threshold=settings.verification_error_rate_threshold,
        request_count=request_count,
        minimum_request_count=settings.verification_minimum_request_count,
    )


remediation = RemediationController(settings, verifier=verify_service_slo)
worker = AIOpsWorker(
    settings,
    telemetry,
    Detector(settings),
    store,
    remediation,
    availability=KubernetesAvailabilityClient(settings.namespace),
)
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


@app.get("/v1/targets/{service}/mutation-block")
async def get_mutation_block(service: str):
    detail = await store.target_block(service)
    return {"service": service, "blocked": detail is not None, "detail": detail}


@app.delete(
    "/v1/targets/{service}/mutation-block",
    dependencies=[Depends(require_token)],
)
async def clear_mutation_block(service: str):
    """Operator unlock after reviewing an escalated post-mutation quarantine."""

    cleared = await store.clear_target_block(service)
    if not cleared:
        raise HTTPException(404, "Target is not under mutation quarantine")
    return {"service": service, "cleared": True}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080)
