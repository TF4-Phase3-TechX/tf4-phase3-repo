from __future__ import annotations

import asyncio
from datetime import timedelta

from .models import AuditEvent, Incident, IncidentStatus, utcnow


class IncidentStore:
    def __init__(self, cooldown_seconds: int = 600, max_items: int = 200):
        self.cooldown = timedelta(seconds=cooldown_seconds)
        self.max_items = max_items
        self._items: dict[str, Incident] = {}
        self._active: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def upsert(self, candidate: Incident) -> tuple[Incident, bool]:
        async with self._lock:
            existing_id = self._active.get(candidate.dedup_key)
            existing = self._items.get(existing_id or "")
            if existing and existing.status not in {IncidentStatus.RESOLVED, IncidentStatus.REJECTED}:
                existing.last_observed_at = utcnow()
                existing.evidence = candidate.evidence
                existing.confidence = candidate.confidence
                existing.audit_events.append(AuditEvent(event="incident_observed_again"))
                return existing, False
            recent = [i for i in self._items.values() if i.dedup_key == candidate.dedup_key]
            if recent and utcnow() - max(i.last_observed_at for i in recent) < self.cooldown:
                return max(recent, key=lambda i: i.last_observed_at), False
            candidate.audit_events.append(AuditEvent(event="incident_created"))
            self._items[candidate.incident_id] = candidate
            self._active[candidate.dedup_key] = candidate.incident_id
            while len(self._items) > self.max_items:
                oldest = min(self._items.values(), key=lambda i: i.detected_at)
                self._items.pop(oldest.incident_id, None)
            return candidate, True

    async def get(self, incident_id: str) -> Incident | None:
        return self._items.get(incident_id)

    async def list(self) -> list[Incident]:
        return sorted(self._items.values(), key=lambda i: i.detected_at, reverse=True)
