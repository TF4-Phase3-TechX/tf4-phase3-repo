"""Fail-closed controls for load tests that call paid AI endpoints."""

from dataclasses import dataclass
import math
import os
from threading import Lock
import time
from typing import Callable, Mapping


_TRUE_VALUES = {"1", "true", "yes", "on"}
_MAX_REQUESTS_HARD_LIMIT = 500
_MAX_WINDOW_MINUTES = 60
_MIN_WAIT_SECONDS = 1.0


def _required_text(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required when LOCUST_PAID_AI_ENABLED=true")
    return value


def _required_int(env: Mapping[str, str], name: str) -> int:
    raw_value = _required_text(env, name)
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


@dataclass(frozen=True)
class PaidAIConfig:
    enabled: bool
    owner: str = ""
    run_id: str = ""
    max_requests: int = 0
    window_seconds: int = 0
    wait_seconds: float = 5.0

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "PaidAIConfig":
        source = os.environ if env is None else env
        enabled = source.get("LOCUST_PAID_AI_ENABLED", "").strip().lower() in _TRUE_VALUES
        if not enabled:
            return cls(enabled=False)

        owner = _required_text(source, "LOCUST_PAID_AI_OWNER")
        run_id = _required_text(source, "LOCUST_PAID_AI_RUN_ID")
        max_requests = _required_int(source, "LOCUST_PAID_AI_MAX_REQUESTS")
        window_minutes = _required_int(source, "LOCUST_PAID_AI_WINDOW_MINUTES")

        try:
            wait_seconds = float(source.get("LOCUST_PAID_AI_WAIT_SECONDS", "5"))
        except ValueError as exc:
            raise ValueError("LOCUST_PAID_AI_WAIT_SECONDS must be numeric") from exc

        if not 1 <= max_requests <= _MAX_REQUESTS_HARD_LIMIT:
            raise ValueError(
                "LOCUST_PAID_AI_MAX_REQUESTS must be between "
                f"1 and {_MAX_REQUESTS_HARD_LIMIT}"
            )
        if not 1 <= window_minutes <= _MAX_WINDOW_MINUTES:
            raise ValueError(
                "LOCUST_PAID_AI_WINDOW_MINUTES must be between "
                f"1 and {_MAX_WINDOW_MINUTES}"
            )
        if not math.isfinite(wait_seconds) or wait_seconds < _MIN_WAIT_SECONDS:
            raise ValueError(
                "LOCUST_PAID_AI_WAIT_SECONDS must be finite and at least "
                f"{_MIN_WAIT_SECONDS:g}"
            )

        return cls(
            enabled=True,
            owner=owner,
            run_id=run_id,
            max_requests=max_requests,
            window_seconds=window_minutes * 60,
            wait_seconds=wait_seconds,
        )


class PaidAIRequestBudget:
    """Process-local request and time budget for the single paid-AI user."""

    def __init__(
        self,
        config: PaidAIConfig,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._clock = clock
        self._lock = Lock()
        self._started_at: float | None = None
        self._request_count = 0

    @property
    def request_count(self) -> int:
        return self._request_count

    def start(self) -> None:
        with self._lock:
            if self._started_at is None:
                self._started_at = self._clock()

    def claim(self) -> tuple[bool, str]:
        with self._lock:
            if not self._config.enabled:
                return False, "disabled"
            if self._started_at is None:
                self._started_at = self._clock()
            if self._clock() - self._started_at >= self._config.window_seconds:
                return False, "window_elapsed"
            if self._request_count >= self._config.max_requests:
                return False, "request_cap_reached"

            self._request_count += 1
            return True, "allowed"
