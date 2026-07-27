"""Bounded in-process episode tracker for cross-service RCA onset memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


@dataclass
class ServiceEpisodeState:
    service: str
    first_breached_at: datetime | None = None
    first_anomalous_at: datetime | None = None
    last_anomalous_at: datetime | None = None
    last_seen_at: datetime | None = None
    currently_anomalous: bool = False


@dataclass
class RCAEpisodeTracker:
    """Process-local episode memory. Lost on restart (documented limitation)."""

    analysis_window_seconds: float = 180.0
    _services: dict[str, ServiceEpisodeState] = field(default_factory=dict)

    def observe(
        self,
        service: str,
        *,
        anomalous: bool,
        breached: bool,
        at: datetime | None = None,
    ) -> ServiceEpisodeState:
        now = at or datetime.now(timezone.utc)
        state = self._services.get(service)
        if state is None:
            state = ServiceEpisodeState(service=service)
            self._services[service] = state
        state.last_seen_at = now
        if anomalous:
            state.currently_anomalous = True
            state.last_anomalous_at = now
            if state.first_anomalous_at is None:
                state.first_anomalous_at = now
            if breached and state.first_breached_at is None:
                state.first_breached_at = now
        else:
            state.currently_anomalous = False
        self.expire(now)
        return state

    def expire(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        window = timedelta(seconds=self.analysis_window_seconds)
        expired = [
            name
            for name, state in self._services.items()
            if state.last_seen_at is not None and now - state.last_seen_at > window
            and not state.currently_anomalous
        ]
        # Also expire if last anomalous is outside window and not currently anomalous
        for name, state in list(self._services.items()):
            if state.currently_anomalous:
                continue
            anchor = state.last_anomalous_at or state.last_seen_at
            if anchor is not None and now - anchor > window:
                expired.append(name)
        for name in set(expired):
            self._services.pop(name, None)

    def recent_affected(self, now: datetime | None = None) -> list[str]:
        now = now or datetime.now(timezone.utc)
        self.expire(now)
        window = timedelta(seconds=self.analysis_window_seconds)
        names: list[str] = []
        for name, state in self._services.items():
            anchor = state.last_anomalous_at
            if state.currently_anomalous:
                names.append(name)
            elif anchor is not None and now - anchor <= window:
                # Recovered root remains candidate until window expiry
                names.append(name)
        return sorted(set(names))

    def first_onset(self, service: str) -> datetime | None:
        state = self._services.get(service)
        if state is None:
            return None
        return state.first_breached_at or state.first_anomalous_at

    def clear(self) -> None:
        self._services.clear()
