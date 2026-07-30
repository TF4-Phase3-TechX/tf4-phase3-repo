"""Persistent incident lifecycle with frozen baselines for Mandate 28."""

from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime, timedelta, timezone
from enum import Enum
from itertools import pairwise
from statistics import mean, median, pstdev
from typing import Any, Protocol

from pydantic import BaseModel, Field


class Lifecycle(str, Enum):
    NORMAL = "NORMAL"
    PENDING = "PENDING"
    FIRING = "FIRING"
    ACTIVE_SUSTAINED = "ACTIVE_SUSTAINED"
    RECOVERING = "RECOVERING"
    RESOLVED = "RESOLVED"


class AlertState(str, Enum):
    NORMAL = "NORMAL"
    INFO_LOAD_SHIFT = "INFO_LOAD_SHIFT"
    PENDING = "PENDING"
    FIRING = "FIRING"
    SUPPRESSED_DUPLICATE_BUT_ACTIVE = "SUPPRESSED_DUPLICATE_BUT_ACTIVE"
    RECOVERING = "RECOVERING"
    RESOLVED = "RESOLVED"
    PRIMARY_TELEMETRY_UNAVAILABLE = "PRIMARY_TELEMETRY_UNAVAILABLE"
    INSUFFICIENT_TRAFFIC = "INSUFFICIENT_TRAFFIC"


class DataQuality(str, Enum):
    AVAILABLE = "available"
    PRIMARY_TELEMETRY_UNAVAILABLE = "primary_telemetry_unavailable"
    INSUFFICIENT_TRAFFIC = "insufficient_traffic"


class FrozenBaseline(BaseModel):
    """Raw clean samples plus reviewable robust statistics."""

    values: list[float]
    captured_at: datetime
    median: float
    mad: float

    @classmethod
    def capture(cls, values: list[float], captured_at: datetime) -> FrozenBaseline:
        if len(values) < 4:
            raise ValueError("a frozen baseline requires at least four clean samples")
        clean = [float(value) for value in values]
        if not all(math.isfinite(value) for value in clean):
            raise ValueError("a frozen baseline cannot contain NaN or infinity")
        center = median(clean)
        return cls(
            values=clean,
            captured_at=captured_at,
            median=center,
            mad=median(abs(value - center) for value in clean),
        )


class FrozenSignalEvaluator:
    """Evaluate current signals against clean points that cannot absorb incidents."""

    def __init__(
        self,
        *,
        latency_floor_ms: float = 1000.0,
        ratio_threshold: float = 1.5,
        zscore_threshold: float = 3.0,
        ewma_threshold: float = 1.0,
        ewma_alpha: float = 0.35,
        warning_burn: float = 2.0,
        critical_burn: float = 10.0,
    ) -> None:
        self.latency_floor_ms = latency_floor_ms
        self.ratio_threshold = ratio_threshold
        self.zscore_threshold = zscore_threshold
        self.ewma_threshold = ewma_threshold
        self.ewma_alpha = ewma_alpha
        self.warning_burn = warning_burn
        self.critical_burn = critical_burn

    def latency_breached(
        self,
        frozen: FrozenBaseline,
        recent_values: list[float],
    ) -> bool:
        if not recent_values:
            return False
        candidates = recent_values[-3:]
        breaches = [self._latency_point(frozen, value) for value in candidates]
        acute = len(breaches) >= 3 and breaches[-1] and sum(breaches) >= 2
        return acute or self._slow_drift(frozen, recent_values)

    def _latency_point(self, frozen: FrozenBaseline, current: float) -> bool:
        baseline_mean = mean(frozen.values)
        deviation = abs(current - baseline_mean)
        std = pstdev(frozen.values) if len(frozen.values) > 1 else 0.0
        ratio = current / max(abs(baseline_mean), 1e-9)
        zscore = deviation / max(std, abs(baseline_mean) * 0.05, 1e-9)
        expected = frozen.values[0]
        residuals: list[float] = []
        for point in frozen.values[1:]:
            residuals.append(abs(point - expected))
            expected = self.ewma_alpha * point + (1 - self.ewma_alpha) * expected
        spread = (
            pstdev(residuals)
            if len(residuals) > 1
            else max(mean(residuals or [0.0]), 1.0)
        )
        ewma = abs(current - expected) / max(
            3.0 * spread,
            abs(expected) * 0.25,
            1.0,
        )
        return current >= self.latency_floor_ms and (
            ratio >= self.ratio_threshold
            or (zscore >= self.zscore_threshold and ewma >= self.ewma_threshold)
        )

    def _slow_drift(
        self,
        frozen: FrozenBaseline,
        recent_values: list[float],
    ) -> bool:
        recent = recent_values[-6:]
        if len(recent) < 5:
            return False
        deltas = [right - left for left, right in pairwise(recent)]
        consistency = sum(delta > 0 for delta in deltas) / len(deltas)
        baseline_mean = mean(frozen.values)
        trend = max(recent[-1] - recent[0], 0.0) / max(abs(baseline_mean), 1e-9)
        return (
            trend >= 0.25
            and consistency >= 0.75
            and recent[-1] / max(abs(baseline_mean), 1e-9) >= 1.2
            and recent[-1] >= self.latency_floor_ms * 0.7
        )

    def error_rate_breach(
        self,
        *,
        error_rate: float | None,
        request_count: float,
        minimum_request_count: float = 20,
        slo_target: float | None = None,
        short_burn: float | None = None,
        long_burn: float | None = None,
    ) -> tuple[bool, str | None]:
        if request_count < minimum_request_count or error_rate is None:
            return False, None
        if not 0 <= error_rate <= 1:
            raise ValueError("error_rate must be between zero and one")
        if slo_target is None:
            return (error_rate >= 0.05, "warning" if error_rate >= 0.05 else None)
        if not 0 < slo_target < 1:
            raise ValueError("slo_target must be between zero and one")
        if short_burn is None or long_burn is None:
            return False, None
        if short_burn >= self.critical_burn and long_burn >= self.critical_burn:
            return True, "critical"
        if short_burn >= self.warning_burn and long_burn >= self.warning_burn:
            return True, "warning"
        return False, None

    @staticmethod
    def llm_error_breach(
        *,
        error_count: float,
        call_count: float,
        minimum_calls: float = 5,
    ) -> bool:
        if error_count < 0 or call_count < 0 or error_count > call_count:
            raise ValueError("LLM counts must be non-negative and errors <= calls")
        return call_count >= minimum_calls and error_count / max(call_count, 1) >= 0.05


class LifecycleRecord(BaseModel):
    state_version: int = 0
    environment: str
    namespace: str
    service: str
    incident_type: str
    incident_id: str
    lifecycle: Lifecycle
    first_breach_at: datetime
    frozen_baseline: FrozenBaseline
    baseline_version: int = 1
    breach_streak: int = 1
    healthy_streak: int = 0
    last_processed_timestamp: datetime
    last_processed_sequence: int
    data_quality: DataQuality = DataQuality.AVAILABLE
    retention_expires_at: datetime
    evidence: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def state_key(self) -> str:
        return state_key(
            self.environment,
            self.namespace,
            self.service,
            self.incident_type,
        )


class Observation(BaseModel):
    timestamp: datetime
    sequence: int
    environment: str = "production"
    namespace: str = "techx-tf4"
    service: str
    incident_type: str
    breached: bool
    primary_telemetry_available: bool = True
    traffic_sufficient: bool = True
    load_shift: bool = False
    enrichment_degraded: bool = False
    value: float | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    incident_id_hint: str | None = None

    @property
    def state_key(self) -> str:
        return state_key(
            self.environment,
            self.namespace,
            self.service,
            self.incident_type,
        )


class AlertEvent(BaseModel):
    timestamp: str
    observed_at: datetime
    state_key: str
    incident_id: str | None
    lifecycle: Lifecycle
    alert_state: AlertState
    baseline_version: int | None
    state_version: int | None
    data_quality: DataQuality
    enrichment_degraded: bool = False


class LifecycleStateStore(Protocol):
    async def read(self, key: str) -> LifecycleRecord | None: ...

    async def compare_and_set(
        self,
        key: str,
        expected_version: int,
        record: LifecycleRecord,
        ttl_seconds: int,
    ) -> bool: ...

    async def list_all(self) -> list[LifecycleRecord]: ...


class MemoryLifecycleStateStore:
    """Deterministic CAS store for tests/replay; not a production fallback."""

    def __init__(self) -> None:
        self._items: dict[str, LifecycleRecord] = {}
        self._lock = asyncio.Lock()

    async def read(self, key: str) -> LifecycleRecord | None:
        async with self._lock:
            item = self._items.get(key)
            return item.model_copy(deep=True) if item else None

    async def compare_and_set(
        self,
        key: str,
        expected_version: int,
        record: LifecycleRecord,
        ttl_seconds: int,
    ) -> bool:
        del ttl_seconds
        async with self._lock:
            current = self._items.get(key)
            current_version = current.state_version if current else 0
            if current_version != expected_version:
                return False
            saved = record.model_copy(deep=True)
            saved.state_version = expected_version + 1
            self._items[key] = saved
            return True

    async def list_all(self) -> list[LifecycleRecord]:
        async with self._lock:
            return [item.model_copy(deep=True) for item in self._items.values()]


class ValkeyLifecycleStateStore:
    """Atomic state-version CAS over a dedicated Valkey connection.

    The supplied client must use decoded string responses. Production activation
    additionally requires a dedicated noeviction Valkey with AOF/RDB; this class
    deliberately does not reuse or configure ``valkey-cart``.
    """

    _CAS_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
local version = 0
if raw then
  local decoded = cjson.decode(raw)
  version = tonumber(decoded['state_version'])
end
if version ~= tonumber(ARGV[1]) then return 0 end
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
return 1
"""

    def __init__(self, client: Any, prefix: str = "aiops:lifecycle:") -> None:
        self.client = client
        self.prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self.prefix}{key}"

    async def read(self, key: str) -> LifecycleRecord | None:
        raw = await self.client.get(self._key(key))
        return LifecycleRecord.model_validate_json(raw) if raw else None

    async def compare_and_set(
        self,
        key: str,
        expected_version: int,
        record: LifecycleRecord,
        ttl_seconds: int,
    ) -> bool:
        saved = record.model_copy(deep=True)
        saved.state_version = expected_version + 1
        result = await self.client.eval(
            self._CAS_SCRIPT,
            1,
            self._key(key),
            expected_version,
            saved.model_dump_json(),
            ttl_seconds,
        )
        return int(result) == 1

    async def list_all(self) -> list[LifecycleRecord]:
        items: list[LifecycleRecord] = []
        async for key in self.client.scan_iter(match=f"{self.prefix}*"):
            raw = await self.client.get(key)
            if raw:
                items.append(LifecycleRecord.model_validate_json(raw))
        return items


def state_key(
    environment: str,
    namespace: str,
    service: str,
    incident_type: str,
) -> str:
    parts = (environment, namespace, service, incident_type)
    if any("::" in part or not part for part in parts):
        raise ValueError(
            "state-key components must be non-empty and cannot contain '::'"
        )
    return "::".join(parts)


class LifecycleEngine:
    def __init__(
        self,
        store: LifecycleStateStore,
        *,
        retention_seconds: int = 3600,
        max_conflict_retries: int = 3,
    ) -> None:
        if retention_seconds <= 0 or max_conflict_retries < 0:
            raise ValueError("retention and retry settings must be non-negative")
        self.store = store
        self.retention_seconds = retention_seconds
        self.max_conflict_retries = max_conflict_retries
        self.concurrency_conflicts_observed = 0

    async def process(
        self,
        observation: Observation,
        clean_baseline: list[float],
        *,
        timestamp_label: str | None = None,
    ) -> AlertEvent:
        if observation.timestamp.tzinfo is None:
            raise ValueError("observation timestamps must include a timezone")
        for attempt in range(self.max_conflict_retries + 1):
            current = await self.store.read(observation.state_key)
            if current and observation.sequence <= current.last_processed_sequence:
                return self._event(
                    current,
                    observation,
                    self._alert_for_lifecycle(current.lifecycle),
                    timestamp_label,
                )
            quality = self._quality(observation)
            if (
                current
                and current.lifecycle == Lifecycle.RESOLVED
                and (quality != DataQuality.AVAILABLE or not observation.breached)
            ):
                alert_state = AlertState.NORMAL
                if quality == DataQuality.PRIMARY_TELEMETRY_UNAVAILABLE:
                    alert_state = AlertState.PRIMARY_TELEMETRY_UNAVAILABLE
                elif quality == DataQuality.INSUFFICIENT_TRAFFIC:
                    alert_state = AlertState.INSUFFICIENT_TRAFFIC
                elif observation.load_shift:
                    alert_state = AlertState.INFO_LOAD_SHIFT
                # Do not rewrite terminal state on every healthy poll: doing so
                # would extend the Valkey TTL forever and defeat retention.
                return self._event(current, observation, alert_state, timestamp_label)
            updated, alert_state = self._transition(
                current, observation, clean_baseline
            )
            if updated is None:
                return AlertEvent(
                    timestamp=timestamp_label or observation.timestamp.isoformat(),
                    observed_at=observation.timestamp,
                    state_key=observation.state_key,
                    incident_id=None,
                    lifecycle=Lifecycle.NORMAL,
                    alert_state=alert_state,
                    baseline_version=None,
                    state_version=None,
                    data_quality=self._quality(observation),
                    enrichment_degraded=observation.enrichment_degraded,
                )
            expected = current.state_version if current else 0
            if await self.store.compare_and_set(
                observation.state_key,
                expected,
                updated,
                self.retention_seconds,
            ):
                saved = await self.store.read(observation.state_key)
                if saved is None:  # pragma: no cover - defensive store contract
                    raise RuntimeError("state disappeared after successful CAS")
                return self._event(saved, observation, alert_state, timestamp_label)
            self.concurrency_conflicts_observed += 1
            if attempt == self.max_conflict_retries:
                break
        raise RuntimeError(
            f"CAS retries exhausted for {observation.state_key}; transition not written"
        )

    def _transition(
        self,
        current: LifecycleRecord | None,
        observation: Observation,
        clean_baseline: list[float],
    ) -> tuple[LifecycleRecord | None, AlertState]:
        quality = self._quality(observation)
        if current is None and quality != DataQuality.AVAILABLE:
            alert = (
                AlertState.PRIMARY_TELEMETRY_UNAVAILABLE
                if quality == DataQuality.PRIMARY_TELEMETRY_UNAVAILABLE
                else AlertState.INSUFFICIENT_TRAFFIC
            )
            return None, alert
        if current is None and not observation.breached:
            return (
                None,
                AlertState.INFO_LOAD_SHIFT
                if observation.load_shift
                else AlertState.NORMAL,
            )
        if current is None or current.lifecycle == Lifecycle.RESOLVED:
            if quality != DataQuality.AVAILABLE or not observation.breached:
                return current, (
                    AlertState.INFO_LOAD_SHIFT
                    if observation.load_shift
                    else AlertState.NORMAL
                )
            record = LifecycleRecord(
                environment=observation.environment,
                namespace=observation.namespace,
                service=observation.service,
                incident_type=observation.incident_type,
                incident_id=observation.incident_id_hint
                or f"inc-{observation.service}-{observation.sequence}",
                lifecycle=Lifecycle.PENDING,
                first_breach_at=observation.timestamp,
                frozen_baseline=FrozenBaseline.capture(
                    clean_baseline, observation.timestamp
                ),
                last_processed_timestamp=observation.timestamp,
                last_processed_sequence=observation.sequence,
                retention_expires_at=observation.timestamp
                + timedelta(seconds=self.retention_seconds),
                evidence=[observation.evidence],
            )
            return record, AlertState.PENDING

        updated = current.model_copy(deep=True)
        updated.last_processed_timestamp = observation.timestamp
        updated.last_processed_sequence = observation.sequence
        updated.retention_expires_at = observation.timestamp + timedelta(
            seconds=self.retention_seconds
        )
        updated.data_quality = quality
        if observation.evidence:
            updated.evidence.append(observation.evidence)

        if quality != DataQuality.AVAILABLE:
            return updated, (
                AlertState.PRIMARY_TELEMETRY_UNAVAILABLE
                if quality == DataQuality.PRIMARY_TELEMETRY_UNAVAILABLE
                else AlertState.INSUFFICIENT_TRAFFIC
            )

        if observation.breached:
            updated.breach_streak += 1
            updated.healthy_streak = 0
            if updated.lifecycle == Lifecycle.PENDING:
                updated.lifecycle = Lifecycle.FIRING
                return updated, AlertState.FIRING
            updated.lifecycle = Lifecycle.ACTIVE_SUSTAINED
            return updated, AlertState.SUPPRESSED_DUPLICATE_BUT_ACTIVE

        updated.healthy_streak += 1
        if updated.healthy_streak < 3:
            updated.lifecycle = Lifecycle.RECOVERING
            return updated, AlertState.RECOVERING
        updated.lifecycle = Lifecycle.RESOLVED
        updated.baseline_version += 1
        if observation.value is not None:
            values = [*updated.frozen_baseline.values[1:], observation.value]
            updated.frozen_baseline = FrozenBaseline.capture(
                values, observation.timestamp
            )
        return updated, AlertState.RESOLVED

    @staticmethod
    def _alert_for_lifecycle(lifecycle: Lifecycle) -> AlertState:
        return {
            Lifecycle.NORMAL: AlertState.NORMAL,
            Lifecycle.PENDING: AlertState.PENDING,
            Lifecycle.FIRING: AlertState.FIRING,
            Lifecycle.ACTIVE_SUSTAINED: AlertState.SUPPRESSED_DUPLICATE_BUT_ACTIVE,
            Lifecycle.RECOVERING: AlertState.RECOVERING,
            Lifecycle.RESOLVED: AlertState.RESOLVED,
        }[lifecycle]

    @staticmethod
    def _quality(observation: Observation) -> DataQuality:
        if not observation.primary_telemetry_available:
            return DataQuality.PRIMARY_TELEMETRY_UNAVAILABLE
        if not observation.traffic_sufficient:
            return DataQuality.INSUFFICIENT_TRAFFIC
        return DataQuality.AVAILABLE

    @staticmethod
    def _event(
        record: LifecycleRecord,
        observation: Observation,
        alert_state: AlertState,
        timestamp_label: str | None,
    ) -> AlertEvent:
        return AlertEvent(
            timestamp=timestamp_label or observation.timestamp.isoformat(),
            observed_at=observation.timestamp,
            state_key=record.state_key,
            incident_id=record.incident_id,
            lifecycle=record.lifecycle,
            alert_state=alert_state,
            baseline_version=record.baseline_version,
            state_version=record.state_version,
            data_quality=record.data_quality,
            enrichment_degraded=observation.enrichment_degraded,
        )


def valkey_client(url: str) -> Any:
    """Build a decoded async client without hiding a missing dependency."""

    if "valkey-cart" in url:
        raise ValueError("Mandate 28 cannot reuse valkey-cart")
    from redis.asyncio import Redis

    return Redis.from_url(url, decode_responses=True)


def record_json(record: LifecycleRecord) -> dict[str, Any]:
    return json.loads(record.model_dump_json())


UTC = timezone.utc
