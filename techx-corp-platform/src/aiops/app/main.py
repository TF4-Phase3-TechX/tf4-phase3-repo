from __future__ import annotations

import asyncio
import hmac
import json
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
from .saga import build_saga_store
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
saga_store = build_saga_store(settings.saga_backend, settings.saga_path or None)


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


remediation = RemediationController(
    settings, verifier=verify_service_slo, saga_store=saga_store
)
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
    # TF4AIO-89: finish or fail-closed any durable sagas before accepting work.
    try:
        reconcile_results = await remediation.reconcile_open_sagas()
        if reconcile_results:
            logging.getLogger("aiops.saga").warning(
                json.dumps(
                    {
                        "event": "startup_saga_reconcile",
                        "results": reconcile_results,
                    }
                )
            )
    except Exception:
        logging.getLogger("aiops.saga").exception("startup saga reconcile failed")
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
    if await store.is_target_blocked(incident.affected_service):
        block = await store.target_block(incident.affected_service)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "target_mutation_quarantine_active",
                "service": incident.affected_service,
                "block": block,
            },
        )
    try:
        remediation.approve(incident)
        await remediation.execute(incident)
    except PolicyDenied as exc:
        # Reconcile even on policy denial: execute may have already mutated and
        # marked mutation_blocked before raising (or left an ambiguous outcome).
        await _reconcile_manual_quarantine(incident)
        raise HTTPException(409, str(exc)) from exc
    await _reconcile_manual_quarantine(incident)
    return incident


async def _reconcile_manual_quarantine(incident) -> None:
    """Same post-execution quarantine path as the background worker."""

    if await store.reconcile_post_execution_quarantine(incident):
        logging.getLogger("aiops.operator").warning(
            json.dumps(
                {
                    "event": "target_mutation_quarantined",
                    "service": incident.affected_service,
                    "incident_id": incident.incident_id,
                    "reason": incident.escalation_reason,
                    "source": "manual_approval",
                }
            )
        )


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
    """Operator unlock after reviewing an escalated post-mutation quarantine.

    Clears the process-local target block and unlocks related
    ``mutation_blocked`` incidents so recovery / a new cycle can proceed.
    """

    detail = await store.target_block(service)
    cleared = await store.clear_target_block(service)
    if not cleared:
        raise HTTPException(404, "Target is not under mutation quarantine")
    logging.getLogger("aiops.operator").warning(
        json.dumps(
            {
                "event": "target_quarantine_cleared",
                "service": service,
                "previous_block": detail,
            }
        )
    )
    return {"service": service, "cleared": True, "previous_block": detail}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080)
