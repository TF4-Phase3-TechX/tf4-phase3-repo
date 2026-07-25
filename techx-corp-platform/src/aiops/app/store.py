from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from .models import AuditEvent, Incident, IncidentStatus, utcnow


class IncidentStore:
    def __init__(self, cooldown_seconds: int = 600, max_items: int = 200):
        self.cooldown = timedelta(seconds=cooldown_seconds)
        self.max_items = max_items
        self._items: dict[str, Incident] = {}
        self._active: dict[str, str] = {}
        self._recovery_streaks: dict[str, int] = {}
        # Process-local target quarantine after a post-mutation safety failure.
        # Survives incident auto-resolve so a new incident cannot re-mutate the
        # same Deployment until an operator clears the block.
        self._blocked_targets: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def upsert(self, candidate: Incident) -> tuple[Incident, bool]:
        async with self._lock:
            existing_id = self._active.get(candidate.dedup_key)
            existing = self._items.get(existing_id or "")
            if existing and existing.status not in {
                IncidentStatus.RESOLVED,
                IncidentStatus.REJECTED,
            }:
                self._recovery_streaks.pop(candidate.dedup_key, None)
                previous_routing = {
                    "severity": existing.severity,
                    "impact": existing.impact.get("level", "not_assessed"),
                }
                existing.last_observed_at = utcnow()
                existing.severity = candidate.severity
                existing.impact = candidate.impact
                existing.evidence = candidate.evidence
                existing.confidence = candidate.confidence
                existing.suspected_root_cause = candidate.suspected_root_cause
                existing.rca_candidates = candidate.rca_candidates
                current_routing = {
                    "severity": existing.severity,
                    "impact": existing.impact.get("level", "not_assessed"),
                }
                existing.audit_events.append(
                    AuditEvent(
                        event=(
                            "incident_routing_changed"
                            if previous_routing != current_routing
                            else "incident_observed_again"
                        ),
                        detail={
                            "previous": previous_routing,
                            "current": current_routing,
                        },
                    )
                )
                return existing, False
            recent = [
                i for i in self._items.values() if i.dedup_key == candidate.dedup_key
            ]
            if recent and utcnow() - max(i.last_observed_at for i in recent) < self.cooldown:
                suppressed = max(recent, key=lambda i: i.last_observed_at)
                suppressed.audit_events.append(
                    AuditEvent(event="incident_suppressed_cooldown")
                )
                return suppressed, False
            candidate.audit_events.append(AuditEvent(event="incident_created"))
            self._recovery_streaks.pop(candidate.dedup_key, None)
            self._items[candidate.incident_id] = candidate
            self._active[candidate.dedup_key] = candidate.incident_id
            while len(self._items) > self.max_items:
                oldest = min(self._items.values(), key=lambda i: i.detected_at)
                # Never prune an active or mutation-blocked safety record.
                if (
                    self._active.get(oldest.dedup_key) == oldest.incident_id
                    or oldest.mutation_blocked
                ):
                    break
                self._items.pop(oldest.incident_id, None)
            return candidate, True

    async def reset_recovery(self, incident_type: str, service: str) -> None:
        """Break a healthy streak when the signal breaches or lacks full coverage."""

        async with self._lock:
            self._recovery_streaks.pop(f"{incident_type}:{service}", None)

    async def observe_recovery(
        self, incident_type: str, service: str, required_polls: int
    ) -> Incident | None:
        """Resolve an inactive-remediation incident after consecutive healthy polls.

        Incidents that reached a post-mutation safety state (mutation_blocked)
        must not auto-resolve: that would drop the only in-process record of the
        quarantine and allow a later incident to re-mutate the same target.
        """

        key = f"{incident_type}:{service}"
        async with self._lock:
            incident = self._items.get(self._active.get(key, ""))
            recoverable = {
                IncidentStatus.OPEN,
                IncidentStatus.AWAITING_APPROVAL,
                IncidentStatus.APPROVED,
                IncidentStatus.ESCALATED,
                IncidentStatus.ROLLED_BACK,
            }
            if not incident or incident.status not in recoverable:
                self._recovery_streaks.pop(key, None)
                return None
            if incident.mutation_blocked:
                self._recovery_streaks.pop(key, None)
                incident.audit_events.append(
                    AuditEvent(
                        event="auto_resolve_suppressed_mutation_blocked",
                        detail={
                            "status": incident.status.value,
                            "escalation_reason": incident.escalation_reason,
                        },
                    )
                )
                return None
            if service in self._blocked_targets:
                self._recovery_streaks.pop(key, None)
                incident.audit_events.append(
                    AuditEvent(
                        event="auto_resolve_suppressed_target_quarantine",
                        detail=self._blocked_targets[service],
                    )
                )
                return None

            streak = self._recovery_streaks.get(key, 0) + 1
            self._recovery_streaks[key] = streak
            incident.audit_events.append(
                AuditEvent(
                    event="healthy_recovery_observed",
                    detail={
                        "poll": streak,
                        "required_polls": max(required_polls, 1),
                    },
                )
            )
            if streak < max(required_polls, 1):
                return None

            incident.status = IncidentStatus.RESOLVED
            incident.last_observed_at = utcnow()
            if incident.approval_status == "pending":
                incident.approval_status = "cancelled_recovered"
            incident.approval_expires_at = None
            incident.audit_events.append(
                AuditEvent(
                    event="incident_auto_resolved",
                    detail={"healthy_polls": streak},
                )
            )
            self._active.pop(key, None)
            self._recovery_streaks.pop(key, None)
            return incident

    async def block_target(
        self,
        service: str,
        *,
        reason: str,
        incident_id: str | None = None,
    ) -> None:
        """Quarantine a Deployment after post-mutation safety failure."""

        async with self._lock:
            self._blocked_targets[service] = {
                "reason": reason,
                "incident_id": incident_id,
                "blocked_at": utcnow().isoformat(),
            }

    async def clear_target_block(self, service: str) -> bool:
        """Operator-facing unlock after manual review (process-local)."""

        async with self._lock:
            return self._blocked_targets.pop(service, None) is not None

    async def is_target_blocked(self, service: str) -> bool:
        async with self._lock:
            return service in self._blocked_targets

    async def target_block(self, service: str) -> dict[str, Any] | None:
        async with self._lock:
            detail = self._blocked_targets.get(service)
            return dict(detail) if detail else None

    async def get(self, incident_id: str) -> Incident | None:
        return self._items.get(incident_id)

    async def list(self) -> list[Incident]:
        return sorted(self._items.values(), key=lambda i: i.detected_at, reverse=True)
