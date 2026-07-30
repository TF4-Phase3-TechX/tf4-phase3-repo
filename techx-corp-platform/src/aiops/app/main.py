from __future__ import annotations

import asyncio
import hmac
import json
import logging
from contextlib import asynccontextmanager
from datetime import timedelta

import uvicorn
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Response,
    status,
)
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .availability import KubernetesAvailabilityClient
from .config import Settings
from .detection import Detector, latency_query, values
from .gitops import (
    FileTokenProvider,
    GitHubAppTokenProvider,
    GitHubGitOpsRemediationAdapter,
    KubernetesLeaseTargetLock,
    KubernetesRuntimeObserver,
)
from .models import IncidentStatus, utcnow
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
# Constructed in lifespan so imports never require a kubeconfig or mounted
# GitHub App private key. Production wiring has no Deployment mutation client.
_remediation_adapter: GitHubGitOpsRemediationAdapter | None = None
_runtime_observer: KubernetesRuntimeObserver | None = None
_target_lock: KubernetesLeaseTargetLock | None = None


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


async def _reconcile_startup_state() -> None:
    """Reconcile durable ownership before the polling worker can start."""

    global _remediation_adapter, _runtime_observer, _target_lock
    saga_log = logging.getLogger("aiops.saga")
    open_sagas = await saga_store.list_open()
    needs_live_adapters = settings.remediation_mode == "gitops/live" or any(
        item.schema_version == 2 for item in open_sagas
    )
    if needs_live_adapters and remediation.adapter is None:
        try:
            reviewer_token_provider = None
            if settings.github_auth_mode == "token-files":
                token_provider = FileTokenProvider(
                    token_path=settings.github_creator_token_path,
                    expected_login=settings.github_creator_login,
                    api_url=settings.github_api_url,
                    proxy_url=settings.github_proxy_url or None,
                )
                if settings.gitops_merge_strategy == "dual-token":
                    reviewer_token_provider = FileTokenProvider(
                        token_path=settings.github_reviewer_token_path,
                        expected_login=settings.github_reviewer_login,
                        api_url=settings.github_api_url,
                        proxy_url=settings.github_proxy_url or None,
                    )
                    creator_login = await asyncio.to_thread(token_provider.login)
                    reviewer_login = await asyncio.to_thread(
                        reviewer_token_provider.login
                    )
                    if creator_login == reviewer_login:
                        raise RuntimeError(
                            "dual-token demo identities must be different"
                        )
            else:
                token_provider = GitHubAppTokenProvider(
                    app_id=settings.github_app_id,
                    installation_id=settings.github_app_installation_id,
                    private_key_path=settings.github_app_private_key_path,
                    api_url=settings.github_api_url,
                    proxy_url=settings.github_proxy_url or None,
                )
            if settings.remediation_mode == "gitops/live":
                # Fail readiness before detector polling when the mounted App
                # identity cannot obtain its repository-scoped token.
                await asyncio.to_thread(token_provider.token)
            _remediation_adapter = GitHubGitOpsRemediationAdapter(
                repository=settings.gitops_repository,
                base_branch=settings.gitops_base_branch,
                policy_path=settings.gitops_policy_path,
                token_provider=token_provider,
                reviewer_token_provider=reviewer_token_provider,
                merge_strategy=settings.gitops_merge_strategy,
                api_url=settings.github_api_url,
                proxy_url=settings.github_proxy_url or None,
            )
            _runtime_observer = KubernetesRuntimeObserver(settings.namespace)
            _target_lock = KubernetesLeaseTargetLock(settings.namespace)
            remediation.adapter = _remediation_adapter
            remediation.runtime_observer = _runtime_observer
            remediation.target_lock = _target_lock
        except Exception as exc:
            if open_sagas or settings.remediation_mode == "gitops/live":
                raise RuntimeError(
                    "GitOps live/open saga requires GitHub, runtime and Lease adapters"
                ) from exc
            saga_log.exception("GitOps adapters unavailable; dry-run remains read-only")

    reconcile_results = await remediation.reconcile_open_sagas()
    if reconcile_results:
        saga_log.warning(
            json.dumps(
                {
                    "event": "startup_saga_reconcile",
                    "results": reconcile_results,
                }
            )
        )
    pruned_sagas = await saga_store.prune_terminal_before(
        utcnow() - timedelta(hours=settings.saga_retention_hours)
    )
    if pruned_sagas:
        saga_log.info(
            json.dumps(
                {
                    "event": "startup_saga_retention_pruned",
                    "saga_ids": pruned_sagas,
                }
            )
        )


async def _recover_then_run_worker(stop_event: asyncio.Event) -> None:
    """Keep liveness responsive while recovery gates readiness and polling."""

    saga_log = logging.getLogger("aiops.saga")
    attempt = 0
    while not stop_event.is_set():
        attempt += 1
        try:
            await _reconcile_startup_state()
            break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            saga_log.exception(
                json.dumps(
                    {
                        "event": "startup_saga_reconcile_retry",
                        "attempt": attempt,
                        "retry_seconds": (settings.startup_reconcile_retry_seconds),
                        "error": str(exc),
                    }
                )
            )
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=settings.startup_reconcile_retry_seconds,
                )
            except TimeoutError:
                continue

    if not stop_event.is_set():
        await worker.run()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Recovery is deliberately asynchronous with respect to API bind:
    # /healthz keeps the pod alive, while /readyz stays closed because the
    # worker cannot run until all durable ownership is reconciled. This avoids
    # the V7 liveness restart loop without allowing a second mutation.
    stop_event = asyncio.Event()
    task = asyncio.create_task(_recover_then_run_worker(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        worker.stop()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
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


@app.get("/v1/incidents/{incident_id}/remediation")
async def get_remediation(incident_id: str):
    incident = await store.get(incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    saga = await saga_store.get_by_incident(incident_id)
    if not saga:
        raise HTTPException(404, "Remediation transaction not found")
    return saga.public_evidence()


async def _execute_approved_incident(incident) -> None:
    try:
        await remediation.execute(incident)
    except PolicyDenied as exc:
        incident.status = IncidentStatus.ESCALATED
        incident.escalation_reason = str(exc)
    finally:
        await _reconcile_manual_quarantine(incident)


@app.post(
    "/v1/incidents/{incident_id}/approve",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_token)],
)
async def approve(incident_id: str, background_tasks: BackgroundTasks):
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
    except PolicyDenied as exc:
        raise HTTPException(409, str(exc)) from exc
    background_tasks.add_task(_execute_approved_incident, incident)
    return {
        "incident_id": incident.incident_id,
        "status": "enqueued",
        "remediation_url": f"/v1/incidents/{incident.incident_id}/remediation",
    }


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
    durable = [
        saga.saga_id
        for saga in await saga_store.list_open_for_target(service)
        if saga.mutation_blocked
    ]
    return {
        "service": service,
        "blocked": detail is not None or bool(durable),
        "detail": detail,
        "durable_saga_ids": durable,
    }


@app.delete(
    "/v1/targets/{service}/mutation-block",
    dependencies=[Depends(require_token)],
)
async def clear_mutation_block(service: str):
    """Operator unlock after reviewing an escalated post-mutation quarantine.

    Clears both the durable saga quarantine and the process-local target block,
    then unlocks related incidents so recovery / a new cycle can proceed.
    """

    detail = await store.target_block(service)
    durable = [
        saga.saga_id
        for saga in await saga_store.list_open_for_target(service)
        if saga.mutation_blocked
    ]
    if detail is None and not durable:
        raise HTTPException(404, "Target is not under mutation quarantine")
    cleared_sagas = await saga_store.clear_mutation_block_for_target(service)
    cleared = await store.clear_target_block(service)
    logging.getLogger("aiops.operator").warning(
        json.dumps(
            {
                "event": "target_quarantine_cleared",
                "service": service,
                "previous_block": detail,
                "cleared_saga_ids": cleared_sagas,
            }
        )
    )
    return {
        "service": service,
        "cleared": cleared or bool(cleared_sagas),
        "previous_block": detail,
        "cleared_saga_ids": cleared_sagas,
    }


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080)
