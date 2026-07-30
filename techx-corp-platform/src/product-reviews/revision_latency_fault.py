"""Bounded, revision-coupled latency fault for the Mandate 22 live drill.

The fault is configured only through Deployment-template environment variables.
Rolling the Deployment back to its previous ReplicaSet therefore removes the
fault causally. Hard caps and two independent deadmen keep a failed drill from
leaving an unbounded production degradation.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import threading
import time
from typing import Callable, Mapping


DELAY_ENV = "MANDATE22_REVIEW_DELAY_MS"
TTL_ENV = "MANDATE22_REVIEW_DELAY_TTL_SECONDS"
REQUEST_BUDGET_ENV = "MANDATE22_REVIEW_DELAY_MAX_REQUESTS"

MAX_DELAY_MS = 3_000
MAX_TTL_SECONDS = 900
MAX_REQUESTS = 200


@dataclass(frozen=True)
class FaultApplication:
    delay_ms: int
    request_ordinal: int
    seconds_remaining: float


class RevisionLatencyFault:
    """Apply a bounded delay to ordinary review RPCs, never health checks."""

    def __init__(
        self,
        *,
        delay_ms: int = 0,
        ttl_seconds: int = 0,
        max_requests: int = 0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._validate(delay_ms, ttl_seconds, max_requests)
        self.delay_ms = delay_ms
        self.ttl_seconds = ttl_seconds
        self.max_requests = max_requests
        self._clock = clock
        self._sleep = sleep
        # Approval and GitOps reconciliation can legitimately take longer than
        # the drill TTL. Start the time deadman on the first eligible request,
        # while keeping the independent request-budget deadman unchanged.
        self._started_at: float | None = None
        self._requests = 0
        self._lock = threading.Lock()

    @classmethod
    def disabled(cls) -> "RevisionLatencyFault":
        return cls()

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> "RevisionLatencyFault":
        values = os.environ if environ is None else environ
        delay_ms = cls._parse_int(values, DELAY_ENV, default=0)
        if delay_ms == 0:
            return cls(clock=clock, sleep=sleep)
        return cls(
            delay_ms=delay_ms,
            ttl_seconds=cls._parse_int(values, TTL_ENV),
            max_requests=cls._parse_int(values, REQUEST_BUDGET_ENV),
            clock=clock,
            sleep=sleep,
        )

    @staticmethod
    def _parse_int(
        environ: Mapping[str, str], key: str, default: int | None = None
    ) -> int:
        raw = environ.get(key)
        if raw is None or raw == "":
            if default is not None:
                return default
            raise ValueError(f"{key} is required when {DELAY_ENV} is enabled")
        try:
            return int(raw)
        except ValueError as exc:
            raise ValueError(f"{key} must be an integer") from exc

    @staticmethod
    def _validate(delay_ms: int, ttl_seconds: int, max_requests: int) -> None:
        if delay_ms == ttl_seconds == max_requests == 0:
            return
        if not 1 <= delay_ms <= MAX_DELAY_MS:
            raise ValueError(f"delay_ms must be between 1 and {MAX_DELAY_MS}")
        if not 1 <= ttl_seconds <= MAX_TTL_SECONDS:
            raise ValueError(
                f"ttl_seconds must be between 1 and {MAX_TTL_SECONDS}"
            )
        if not 1 <= max_requests <= MAX_REQUESTS:
            raise ValueError(
                f"max_requests must be between 1 and {MAX_REQUESTS}"
            )

    @property
    def enabled(self) -> bool:
        return self.delay_ms > 0

    def apply(self) -> FaultApplication | None:
        """Sleep once if both deadmen still allow the request.

        The request budget is reserved under a lock, but the sleep occurs
        outside it so normal gRPC worker concurrency is preserved.
        """

        if not self.enabled:
            return None
        with self._lock:
            now = self._clock()
            if self._started_at is None:
                self._started_at = now
            elapsed = now - self._started_at
            if elapsed >= self.ttl_seconds or self._requests >= self.max_requests:
                return None
            self._requests += 1
            application = FaultApplication(
                delay_ms=self.delay_ms,
                request_ordinal=self._requests,
                seconds_remaining=max(0.0, self.ttl_seconds - elapsed),
            )
        self._sleep(self.delay_ms / 1_000)
        return application
