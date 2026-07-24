from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter as ValueCounter
from typing import Any

from prometheus_client import Counter, Gauge

from .availability import KubernetesAvailabilityClient
from .config import Settings
from .detection import (
    Detector,
    classify_service_state,
    error_budget_burn_rate_query,
    error_rate_query,
    instant_value,
    latency_query,
    llm_error_query,
    request_rate_query,
    values,
)
from .models import Evidence, Incident, IncidentStatus
from .remediation import RemediationController
from .store import IncidentStore
from .telemetry import TelemetryClient, TelemetryError

log = logging.getLogger("aiops.worker")
poll_failures = Counter("aiops_telemetry_poll_failures_total", "Telemetry poll failures", ["source"])
incidents_created = Counter(
    "aiops_incidents_created_total",
    "Incidents created",
    ["incident_type", "service", "severity", "impact"],
)
incidents_active = Gauge(
    "aiops_incident_active",
    "Whether an incident is currently active and should remain routed to on-call",
    ["incident_type", "service", "severity", "impact"],
)
error_budget_burn_rate = Gauge(
    "aiops_error_budget_burn_rate",
    "Current request-weighted error-budget burn rate for an approved service SLO",
    ["service", "window"],
)
incidents_resolved = Counter(
    "aiops_incidents_auto_resolved_total",
    "Incidents resolved after consecutive fully covered healthy polls",
    ["incident_type", "service"],
)
coverage_degraded = Counter(
    "aiops_telemetry_coverage_degraded_total",
    "Detector observations without a complete ready baseline",
    ["source", "signal", "service", "state"],
)
last_poll_success = Gauge("aiops_last_poll_success_unixtime", "Last successful telemetry polling time")
service_state = Gauge(
    "aiops_service_state",
    "Current combined workload, traffic and SLO state",
    ["service", "state"],
)
SERVICE_STATES = ("healthy", "busy", "idle", "degraded", "down", "unknown")


def _notification_severity(incident_severity: str) -> str:
    return "critical" if incident_severity == "high" else "warning"


def _impact_level(impact: dict[str, Any]) -> str:
    return str(impact.get("level") or "not_assessed")


def _series_service(series: dict[str, Any]) -> str | None:
    metric = series.get("metric", {})
    return metric.get("service_name") or metric.get("service")


def _log_service(hit: dict[str, Any]) -> str | None:
    source = hit.get("_source", hit)
    direct = source.get("resource.service.name") or source.get("service.name")
    if direct:
        return str(direct)
    resource = source.get("resource", {})
    if isinstance(resource, dict):
        service = resource.get("service", {})
        if isinstance(service, dict) and service.get("name"):
            return str(service["name"])
    return None


class AIOpsWorker:
    def __init__(
        self,
        settings: Settings,
        telemetry: TelemetryClient,
        detector: Detector,
        store: IncidentStore,
        remediation: RemediationController,
        availability: KubernetesAvailabilityClient | None = None,
    ):
        self.settings = settings
        self.telemetry = telemetry
        self.detector = detector
        self.store = store
        self.remediation = remediation
        self.availability = availability
        self.running = False

    async def poll_once(self) -> None:
        import time

        prometheus_ok = True

        async def query_range(query: str):
            nonlocal prometheus_ok
            try:
                return await self.telemetry.query_range(query)
            except TelemetryError as exc:
                prometheus_ok = False
                poll_failures.labels("prometheus").inc()
                log.error(json.dumps({"event": "telemetry_degraded", "source": "prometheus", "error": str(exc)}))
                return []

        async def query_instant(query: str):
            nonlocal prometheus_ok
            try:
                return await self.telemetry.query(query)
            except TelemetryError as exc:
                prometheus_ok = False
                poll_failures.labels("prometheus").inc()
                log.error(
                    json.dumps(
                        {
                            "event": "telemetry_degraded",
                            "source": "prometheus",
                            "error": str(exc),
                        }
                    )
                )
                return []

        decisions = []
        for service in self.settings.services:
            query = latency_query(service, self.settings.namespace)
            latency_decision = (
                await asyncio.to_thread(
                    self.detector.latency,
                    service,
                    await query_range(query),
                    query,
                )
            )
            decisions.append(latency_decision)
            query = error_rate_query(
                service, self.settings.minimum_request_count, self.settings.namespace
            )
            burn_rates: tuple[float | None, float | None] | None = None
            slo_target = self.settings.service_slo_targets.get(service)
            if slo_target is not None:
                observed_burn_rates: list[float | None] = []
                for window in (
                    self.settings.burn_rate_short_window_minutes,
                    self.settings.burn_rate_long_window_minutes,
                ):
                    burn_query = error_budget_burn_rate_query(
                        service,
                        slo_target,
                        window,
                        self.settings.minimum_request_count,
                        self.settings.namespace,
                    )
                    observed = instant_value(await query_instant(burn_query))
                    observed_burn_rates.append(observed)
                    error_budget_burn_rate.labels(service, f"{window}m").set(
                        observed if observed is not None else float("nan")
                    )
                burn_rates = (observed_burn_rates[0], observed_burn_rates[1])
            error_decision = (
                await asyncio.to_thread(
                    self.detector.error_rate,
                    service,
                    await query_range(query),
                    query,
                    burn_rates=burn_rates,
                )
            )
            decisions.append(error_decision)

            if self.availability:
                snapshot = await asyncio.to_thread(
                    self.availability.snapshot, service
                )
                decisions.append(
                    await asyncio.to_thread(
                        self.detector.availability, snapshot
                    )
                )
                traffic_series = await query_range(
                    request_rate_query(service, self.settings.namespace)
                )
                traffic_points = (
                    values(traffic_series[0]) if traffic_series else []
                )
                state = classify_service_state(
                    snapshot,
                    traffic_points[-1] if traffic_points else None,
                    latency_breached=latency_decision.breached,
                    error_rate_breached=error_decision.breached,
                    busy_request_rate_threshold=(
                        self.settings.busy_request_rate_threshold
                    ),
                )
                for candidate_state in SERVICE_STATES:
                    service_state.labels(service, candidate_state).set(
                        1 if candidate_state == state else 0
                    )

        # Discover every instrumented LLM caller from the metric label. This
        # prevents a failure in a future caller (for example shopping-copilot)
        # from being attributed to product-reviews.
        query = llm_error_query(
            "", self.settings.llm_minimum_call_count, self.settings.namespace
        )
        llm_series = await query_range(query)
        attributed_series: list[tuple[str, dict[str, Any]]] = []
        for item in llm_series:
            service = _series_service(item)
            if service:
                attributed_series.append((service, item))
            else:
                coverage_degraded.labels(
                    "prometheus", "llm_timeout_error", "unattributed", "unavailable"
                ).inc()
                log.error(
                    json.dumps(
                        {
                            "event": "llm_metric_missing_service_label",
                            "metric": item.get("metric", {}),
                        }
                    )
                )

        log_scope = tuple(
            sorted(
                set(self.settings.llm_log_services)
                | {service for service, _ in attributed_series}
            )
        )
        logs = await self.telemetry.search_logs(
            log_scope, ("timeout", "rate_limit", "deadline", "error")
        )
        if logs is None:
            poll_failures.labels("opensearch").inc()
            log.warning(json.dumps({"event": "telemetry_degraded", "source": "opensearch"}))
        log_counts = ValueCounter(
            service for hit in (logs or []) if (service := _log_service(hit))
        )

        if attributed_series:
            for service, item in attributed_series:
                decisions.append(
                    await asyncio.to_thread(
                        self.detector.llm_error,
                        service,
                        [item],
                        query,
                        log_counts.get(service, 0) if logs is not None else None,
                    )
                )
        else:
            # No series above the minimum-call gate is a coverage state, not a
            # healthy zero. Expected callers are used only for that status.
            for service in self.settings.llm_services:
                decisions.append(
                    await asyncio.to_thread(
                        self.detector.llm_error,
                        service,
                        [],
                        query,
                        None if logs is None else log_counts.get(service, 0),
                    )
                )
        for decision in decisions:
            if decision.coverage_status != "available":
                source = (
                    "kubernetes"
                    if decision.incident_type == "service_availability"
                    else "prometheus"
                )
                coverage_degraded.labels(
                    source,
                    decision.incident_type,
                    decision.service,
                    decision.coverage_status,
                ).inc()
                await self.store.reset_recovery(decision.incident_type, decision.service)
                log.warning(
                    json.dumps(
                        {
                            "event": "signal_coverage_degraded",
                            "source": source,
                            "signal": decision.incident_type,
                            "service": decision.service,
                            "state": decision.coverage_status,
                        }
                    )
                )
            elif not decision.breached:
                resolved = await self.store.observe_recovery(
                    decision.incident_type,
                    decision.service,
                    self.settings.recovery_polls,
                )
                if resolved:
                    incidents_active.labels(
                        resolved.incident_type,
                        resolved.affected_service,
                        _notification_severity(resolved.severity),
                        _impact_level(resolved.impact),
                    ).set(0)
                    incidents_resolved.labels(
                        resolved.incident_type, resolved.affected_service
                    ).inc()
                    log.info(
                        json.dumps(
                            {
                                "event": "incident_auto_resolved",
                                "incident_id": resolved.incident_id,
                                "incident_type": resolved.incident_type,
                                "service": resolved.affected_service,
                            }
                        )
                    )
            else:
                await self.store.reset_recovery(decision.incident_type, decision.service)

            if not decision.anomalous:
                continue
            incident = Incident(
                incident_type=decision.incident_type,
                severity=decision.severity,
                affected_service=decision.service,
                environment=self.settings.environment,
                tenant_id=self.settings.tenant_id,
                confidence=decision.confidence,
                suspected_root_cause=decision.root_cause,
                impact=decision.impact,
                evidence=decision.evidence,
                rca_candidates=decision.candidates,
                runbook_id=decision.runbook_id,
                recommended_action=decision.recommended_action,
            )
            traces = await self.telemetry.find_traces(decision.service)
            if traces is None:
                poll_failures.labels("jaeger").inc()
                log.warning(json.dumps({"event": "telemetry_degraded", "source": "jaeger", "service": decision.service}))
                incident.evidence.append(
                    Evidence(
                        source="jaeger",
                        query=f"service={decision.service}",
                        window=f"{self.settings.lookback_minutes}m",
                        value="unavailable",
                    )
                )
            elif traces:
                trace_id = traces[0].get("traceID") or traces[0].get("traceId")
                incident.evidence.append(Evidence(
                    source="jaeger", query=f"service={decision.service}", window=f"{self.settings.lookback_minutes}m",
                    value=len(traces), reference=str(trace_id) if trace_id else None,
                ))
            active_before = next(
                (
                    existing
                    for existing in await self.store.list()
                    if existing.dedup_key == incident.dedup_key
                    and existing.status
                    not in {IncidentStatus.RESOLVED, IncidentStatus.REJECTED}
                ),
                None,
            )
            previous_routing = (
                (
                    _notification_severity(active_before.severity),
                    _impact_level(active_before.impact),
                )
                if active_before
                else None
            )
            stored, created = await self.store.upsert(incident)
            if created:
                notification_severity = _notification_severity(incident.severity)
                incidents_created.labels(
                    incident.incident_type,
                    incident.affected_service,
                    notification_severity,
                    _impact_level(incident.impact),
                ).inc()
                incidents_active.labels(
                    incident.incident_type,
                    incident.affected_service,
                    notification_severity,
                    _impact_level(incident.impact),
                ).set(1)
                handler = getattr(self.remediation, "handle_incident", None)
                if handler:
                    await handler(stored)
                else:
                    # Backward-compatible seam for test doubles and manual-mode adapters.
                    self.remediation.request_approval(stored)
                log.info(json.dumps({"event": "incident_created", "incident": stored.model_dump(mode="json")}, separators=(",", ":")))
            elif active_before and stored.incident_id == active_before.incident_id:
                current_routing = (
                    _notification_severity(stored.severity),
                    _impact_level(stored.impact),
                )
                if previous_routing != current_routing:
                    incidents_active.labels(
                        stored.incident_type,
                        stored.affected_service,
                        previous_routing[0],
                        previous_routing[1],
                    ).set(0)
                    incidents_active.labels(
                        stored.incident_type,
                        stored.affected_service,
                        current_routing[0],
                        current_routing[1],
                    ).set(1)
                    log.info(
                        json.dumps(
                            {
                                "event": "incident_routing_changed",
                                "incident_id": stored.incident_id,
                                "previous": previous_routing,
                                "current": current_routing,
                            }
                        )
                    )
        if prometheus_ok:
            last_poll_success.set(time.time())

    async def run(self) -> None:
        self.running = True
        while self.running:
            try:
                await self.poll_once()
            except TelemetryError as exc:
                poll_failures.labels("prometheus").inc()
                log.error(json.dumps({"event": "telemetry_degraded", "error": str(exc)}))
            except Exception:
                log.exception("unexpected polling failure")
            await asyncio.sleep(self.settings.poll_seconds)

    def stop(self) -> None:
        self.running = False
