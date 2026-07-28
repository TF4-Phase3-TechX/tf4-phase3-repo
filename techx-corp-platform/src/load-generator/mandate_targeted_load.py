"""Bounded targeted load for Mandate 15/22 production drills.

This runner complements the mixed Locust UI workload. It targets one service
path at a time, emits a machine-readable result, and fails closed on missing
ownership, unsafe request/concurrency limits, or a rolling failure breach.
"""

from __future__ import annotations

import argparse
from collections import Counter
import concurrent.futures
import copy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import re
import threading
import time
from typing import Any, Callable, Mapping, Sequence
import uuid

import requests


DEFAULT_BASE_URL = "http://frontend-proxy:8080"
DEFAULT_PRODUCT_ID = "0PUK6V6EV0"
MAX_REQUESTS = 5_000
MAX_WORKERS = 50
MIN_PACE_SECONDS = 0.05
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$")


@dataclass(frozen=True)
class TargetedLoadConfig:
    scenario: str
    owner: str
    run_id: str
    max_requests: int
    workers: int
    pace_seconds: float
    failure_stop_ratio: float = 0.10
    failure_window: int = 100
    base_url: str = DEFAULT_BASE_URL
    product_id: str = DEFAULT_PRODUCT_ID
    execute: bool = False

    def validate(self) -> None:
        if self.scenario not in {"product-reviews", "checkout"}:
            raise ValueError("scenario must be product-reviews or checkout")
        if not self.owner.strip():
            raise ValueError("owner is required")
        if not RUN_ID_PATTERN.fullmatch(self.run_id):
            raise ValueError("run-id must be 3-80 safe attribution characters")
        if not 1 <= self.max_requests <= MAX_REQUESTS:
            raise ValueError(f"max-requests must be between 1 and {MAX_REQUESTS}")
        if not 1 <= self.workers <= MAX_WORKERS:
            raise ValueError(f"workers must be between 1 and {MAX_WORKERS}")
        if not math.isfinite(self.pace_seconds) or self.pace_seconds < MIN_PACE_SECONDS:
            raise ValueError(
                f"pace-seconds must be finite and at least {MIN_PACE_SECONDS}"
            )
        if not 0.01 <= self.failure_stop_ratio <= 0.25:
            raise ValueError("failure-stop-ratio must be between 0.01 and 0.25")
        if not 20 <= self.failure_window <= 1_000:
            raise ValueError("failure-window must be between 20 and 1000")
        if self.base_url.rstrip("/") != DEFAULT_BASE_URL:
            raise ValueError(
                f"base-url is pinned to the in-cluster proxy {DEFAULT_BASE_URL}"
            )
        if not self.product_id.strip():
            raise ValueError("product-id is required")


@dataclass(frozen=True)
class Attempt:
    latency_ms: float
    status: int | None
    failed: bool
    stage: str
    error: str | None
    observed_at_utc: str


class _AtomicIndex:
    def __init__(self, limit: int):
        self._next = 0
        self._limit = limit
        self._lock = threading.Lock()

    def take(self) -> int | None:
        with self._lock:
            if self._next >= self._limit:
                return None
            value = self._next
            self._next += 1
            return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * percentile))]


def _load_people(path: Path | None = None) -> list[dict[str, Any]]:
    source = path or Path(__file__).with_name("people.json")
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("people.json must contain at least one checkout payload")
    return data


def _record_attempt(
    *,
    started: float,
    status: int | None,
    stage: str,
    error: Exception | None,
    monotonic: Callable[[], float],
    utc_now: Callable[[], str],
) -> Attempt:
    return Attempt(
        latency_ms=(monotonic() - started) * 1_000,
        status=status,
        failed=error is not None,
        stage=stage,
        error=(
            f"{type(error).__name__}:{str(error)[:200]}" if error is not None else None
        ),
        observed_at_utc=utc_now(),
    )


def run_targeted_load(
    config: TargetedLoadConfig,
    *,
    people: Sequence[Mapping[str, Any]] | None = None,
    session_factory: Callable[[], Any] = requests.Session,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    utc_now: Callable[[], str] = _utc_now,
) -> dict[str, Any]:
    config.validate()
    started_at = utc_now()
    if not config.execute:
        return {
            "schema_version": "tf4-targeted-load-v1",
            "status": "planned",
            "started_at_utc": started_at,
            "config": asdict(config),
            "claim_boundary": "No traffic sent; pass --execute after named approval.",
        }

    checkout_people = list(people) if people is not None else _load_people()
    if config.scenario == "checkout" and not checkout_people:
        raise ValueError("checkout scenario requires at least one person payload")
    index = _AtomicIndex(config.max_requests)
    stop = threading.Event()
    lock = threading.Lock()
    attempts: list[Attempt] = []

    def execute_one(session: Any, sequence: int) -> Attempt:
        started = monotonic()
        stage = "product-reviews" if config.scenario == "product-reviews" else "cart"
        status: int | None = None
        caught: Exception | None = None
        headers = {
            "X-TF4-Load-Owner": config.owner,
            "X-TF4-Load-Run-ID": config.run_id,
        }
        try:
            if config.scenario == "product-reviews":
                response = session.get(
                    f"{config.base_url}/api/product-reviews/{config.product_id}",
                    headers=headers,
                    timeout=12,
                )
                status = response.status_code
                response.raise_for_status()
            else:
                user_id = f"{config.run_id}-{sequence}-{uuid.uuid4()}"
                response = session.post(
                    f"{config.base_url}/api/cart",
                    json={
                        "item": {"productId": config.product_id, "quantity": 1},
                        "userId": user_id,
                    },
                    headers=headers,
                    timeout=5,
                )
                status = response.status_code
                response.raise_for_status()
                stage = "checkout"
                person = copy.deepcopy(random.choice(checkout_people))
                person["userId"] = user_id
                response = session.post(
                    f"{config.base_url}/api/checkout",
                    json=person,
                    headers=headers,
                    timeout=12,
                )
                status = response.status_code
                response.raise_for_status()
        except Exception as exc:  # Requests exposes several transport subclasses.
            caught = exc
        return _record_attempt(
            started=started,
            status=status,
            stage=stage,
            error=caught,
            monotonic=monotonic,
            utc_now=utc_now,
        )

    def worker() -> None:
        session = session_factory()
        while not stop.is_set():
            sequence = index.take()
            if sequence is None:
                return
            attempt = execute_one(session, sequence)
            with lock:
                attempts.append(attempt)
                recent = attempts[-config.failure_window :]
                if (
                    len(recent) == config.failure_window
                    and sum(item.failed for item in recent) / len(recent)
                    > config.failure_stop_ratio
                ):
                    stop.set()
            sleep(config.pace_seconds)

    with concurrent.futures.ThreadPoolExecutor(max_workers=config.workers) as executor:
        list(executor.map(lambda _: worker(), range(config.workers)))

    latencies = [item.latency_ms for item in attempts]
    failures = [item for item in attempts if item.failed]
    return {
        "schema_version": "tf4-targeted-load-v1",
        "status": "stopped_by_failure_guard" if stop.is_set() else "completed",
        "started_at_utc": started_at,
        "ended_at_utc": utc_now(),
        "owner": config.owner,
        "run_id": config.run_id,
        "scenario": config.scenario,
        "base_url": config.base_url,
        "product_id": config.product_id,
        "workers": config.workers,
        "pace_seconds": config.pace_seconds,
        "attempt_cap": config.max_requests,
        "maximum_http_requests": config.max_requests
        * (2 if config.scenario == "checkout" else 1),
        "attempts": len(attempts),
        "failures": len(failures),
        "failure_ratio": len(failures) / max(1, len(attempts)),
        "p50_ms": _percentile(latencies, 0.50),
        "p95_ms": _percentile(latencies, 0.95),
        "p99_ms": _percentile(latencies, 0.99),
        "status_counts": dict(Counter(str(item.status) for item in attempts)),
        "failure_stages": dict(Counter(item.stage for item in failures)),
        "failure_samples": [asdict(item) for item in failures[:10]],
        "claim_boundary": (
            "Traffic result only; correlate timestamps with detector, telemetry, "
            "readiness and final restore before making a mandate claim."
        ),
    }


def _parse_args(argv: Sequence[str] | None = None) -> TargetedLoadConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario", required=True, choices=("product-reviews", "checkout")
    )
    parser.add_argument("--owner", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--max-requests", type=int, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--pace-seconds", type=float, required=True)
    parser.add_argument("--failure-stop-ratio", type=float, default=0.10)
    parser.add_argument("--failure-window", type=int, default=100)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--product-id", default=DEFAULT_PRODUCT_ID)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Send traffic. Without this flag the command prints a plan only.",
    )
    return TargetedLoadConfig(**vars(parser.parse_args(argv)))


def main(argv: Sequence[str] | None = None) -> int:
    config = _parse_args(argv)
    try:
        result = run_targeted_load(config)
    except ValueError as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
