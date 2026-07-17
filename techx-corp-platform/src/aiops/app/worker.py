from __future__ import annotations

import asyncio
import json
import logging

from prometheus_client import Counter, Gauge

from .config import Settings
from .detection import Detector, error_rate_query, latency_query, llm_error_query
from .models import Evidence, Incident
from .remediation import RemediationController
from .store import IncidentStore
from .telemetry import TelemetryClient, TelemetryError

log = logging.getLogger("aiops.worker")
poll_failures = Counter("aiops_telemetry_poll_failures_total", "Telemetry poll failures", ["source"])
incidents_created = Counter(
    "aiops_incidents_created_total",
    "Incidents created",
    ["incident_type", "service", "severity"],
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


class AIOpsWorker:
    def __init__(self, settings: Settings, telemetry: TelemetryClient, detector: Detector, store: IncidentStore, remediation: RemediationController):
        self.settings = settings
        self.telemetry = telemetry
        self.detector = detector
        self.store = store
        self.remediation = remediation
        self.running = False

    async def poll_once(self) -> None:
        import time

        logs = await self.telemetry.search_logs(self.settings.llm_services, ("timeout", "rate_limit", "deadline", "error"))
        if logs is None:
            poll_failures.labels("opensearch").inc()
            log.warning(json.dumps({"event": "telemetry_degraded", "source": "opensearch"}))

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

        decisions = []
        for service in self.settings.services:
            query = latency_query(service)
            decisions.append(self.detector.latency(service, await query_range(query), query))
            query = error_rate_query(service, self.settings.minimum_request_count)
            decisions.append(self.detector.error_rate(service, await query_range(query), query))
        # app_llm_* is a single global metric family today, so it has exactly
        # one configured incident owner. llm_services remains the log scope.
        query = llm_error_query(self.settings.llm_signal_owner, self.settings.llm_minimum_call_count)
        decisions.append(
            self.detector.llm_error(
                self.settings.llm_signal_owner,
                await query_range(query),
                query,
                len(logs) if logs is not None else None,
            )
        )
        for decision in decisions:
            if decision.coverage_status != "available":
                coverage_degraded.labels(
                    "prometheus",
                    decision.incident_type,
                    decision.service,
                    decision.coverage_status,
                ).inc()
                await self.store.reset_recovery(decision.incident_type, decision.service)
                log.warning(
                    json.dumps(
                        {
                            "event": "signal_coverage_degraded",
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
            stored, created = await self.store.upsert(incident)
            if created:
                notification_severity = "critical" if incident.severity == "high" else "warning"
                incidents_created.labels(
                    incident.incident_type,
                    incident.affected_service,
                    notification_severity,
                ).inc()
                self.remediation.request_approval(stored)
                log.info(json.dumps({"event": "incident_created", "incident": stored.model_dump(mode="json")}, separators=(",", ":")))
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
