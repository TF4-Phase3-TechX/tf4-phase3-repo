from datetime import datetime, timedelta, timezone

import pytest

from app.lifecycle import (
    AlertState,
    FrozenBaseline,
    FrozenSignalEvaluator,
    Lifecycle,
    LifecycleEngine,
    LifecyclePersistenceError,
    MemoryLifecycleStateStore,
    Observation,
    ValkeyLifecycleStateStore,
)

NOW = datetime(2026, 7, 30, tzinfo=timezone.utc)
BASELINE = [98.0, 100.0, 102.0, 99.0, 101.0, 100.0]


def observation(
    sequence: int,
    *,
    breached: bool,
    primary: bool = True,
    traffic: bool = True,
) -> Observation:
    return Observation(
        timestamp=NOW + timedelta(minutes=sequence),
        sequence=sequence,
        event_id=f"checkout-{sequence}",
        service="checkout",
        incident_type="service_latency_spike",
        breached=breached,
        primary_telemetry_available=primary,
        traffic_sufficient=traffic,
        value=1600.0 if breached else 100.0,
    )


@pytest.mark.asyncio
async def test_frozen_baseline_survives_sustained_incident_and_restart():
    store = MemoryLifecycleStateStore()
    engine = LifecycleEngine(store)

    await engine.process(observation(1, breached=True), BASELINE)
    await engine.process(observation(2, breached=True), [1600.0] * 6)
    restarted = LifecycleEngine(store)
    event = await restarted.process(observation(3, breached=True), [1700.0] * 6)
    state = (await store.list_all())[0]

    assert event.lifecycle == Lifecycle.ACTIVE_SUSTAINED
    assert event.incident_id == state.incident_id
    assert state.frozen_baseline.values == BASELINE
    assert state.baseline_version == 1


@pytest.mark.asyncio
async def test_coverage_gaps_hold_state_and_recovery_requires_three_polls():
    store = MemoryLifecycleStateStore()
    engine = LifecycleEngine(store)
    await engine.process(observation(1, breached=True), BASELINE)
    await engine.process(observation(2, breached=True), BASELINE)
    await engine.process(observation(3, breached=True), BASELINE)

    unavailable = await engine.process(
        observation(4, breached=False, primary=False), BASELINE
    )
    insufficient = await engine.process(
        observation(5, breached=False, traffic=False), BASELINE
    )
    recovering_one = await engine.process(observation(6, breached=False), BASELINE)
    recovering_two = await engine.process(observation(7, breached=False), BASELINE)
    resolved = await engine.process(observation(8, breached=False), BASELINE)

    assert unavailable.alert_state == AlertState.PRIMARY_TELEMETRY_UNAVAILABLE
    assert insufficient.alert_state == AlertState.INSUFFICIENT_TRAFFIC
    assert recovering_one.lifecycle == Lifecycle.RECOVERING
    assert recovering_two.lifecycle == Lifecycle.RECOVERING
    assert resolved.lifecycle == Lifecycle.RESOLVED


@pytest.mark.asyncio
async def test_recovery_flap_keeps_incident_and_resets_streak():
    store = MemoryLifecycleStateStore()
    engine = LifecycleEngine(store)
    for sequence in range(1, 4):
        await engine.process(observation(sequence, breached=True), BASELINE)
    await engine.process(observation(4, breached=False), BASELINE)
    await engine.process(observation(5, breached=False), BASELINE)
    flapped = await engine.process(observation(6, breached=True), BASELINE)

    assert flapped.lifecycle == Lifecycle.ACTIVE_SUSTAINED
    assert flapped.incident_id == (await store.list_all())[0].incident_id
    state = (await store.list_all())[0]
    assert state.healthy_streak == 0


class FakeValkey:
    def __init__(self):
        self.items = {}
        self.ttls = {}
        self.now = 0
        self.expires_at = {}

    async def get(self, key):
        if key in self.expires_at and self.now >= self.expires_at[key]:
            self.items.pop(key, None)
            self.expires_at.pop(key, None)
        return self.items.get(key)

    async def eval(self, script, number_of_keys, key, expected, payload, ttl):
        del script, number_of_keys
        import json

        current = (
            json.loads(self.items[key])["state_version"] if key in self.items else 0
        )
        if current != int(expected):
            return 0
        self.items[key] = payload
        self.ttls[key] = int(ttl)
        self.expires_at[key] = self.now + int(ttl)
        return 1

    async def scan_iter(self, match):
        prefix = match[:-1]
        for key in self.items:
            if key.startswith(prefix):
                yield key


@pytest.mark.asyncio
async def test_valkey_store_enforces_state_version_cas():
    client = FakeValkey()
    store = ValkeyLifecycleStateStore(client)
    engine = LifecycleEngine(store)
    await engine.process(observation(1, breached=True), BASELINE)
    record = (await store.list_all())[0]

    stale = record.model_copy(deep=True)
    stale.state_version = 0
    assert await store.compare_and_set(record.state_key, 0, stale, 3600) is False
    assert (await store.read(record.state_key)).state_version == 1
    assert store.client.ttls[f"aiops:lifecycle:{record.state_key}"] == 3600
    client.now = 3600
    assert await store.read(record.state_key) is None


def test_valkey_cart_is_rejected():
    from app import lifecycle

    with pytest.raises(ValueError, match="cannot reuse valkey-cart"):
        lifecycle.valkey_client("redis://valkey-cart:6379/0")


def test_signal_contracts_use_frozen_raw_window():
    evaluator = FrozenSignalEvaluator()
    frozen = FrozenBaseline.capture(BASELINE, NOW)

    assert evaluator.latency_breached(frozen, [1600.0, 1650.0, 1700.0]) is True
    assert evaluator.latency_breached(frozen, [1600.0, 100.0, 1700.0]) is True
    assert evaluator.latency_breached(frozen, [1600.0, 1700.0, 100.0]) is False
    assert (
        evaluator.latency_breached(frozen, [600.0, 650.0, 700.0, 750.0, 800.0]) is True
    )
    # Sustained incident values are deliberately not admitted to the reference.
    assert frozen.values == BASELINE
    assert evaluator.latency_breached(frozen, [100.0, 102.0, 101.0]) is False
    assert evaluator.error_rate_breach(
        error_rate=0.02,
        request_count=100,
        slo_target=0.99,
        short_burn=2.5,
        long_burn=2.1,
    ) == (True, "warning")
    assert evaluator.error_rate_breach(
        error_rate=0.11,
        request_count=100,
        slo_target=0.99,
        short_burn=12,
        long_burn=11,
    ) == (True, "critical")
    assert evaluator.error_rate_breach(
        error_rate=0.12,
        request_count=10,
    ) == (False, None)
    assert evaluator.llm_error_breach(error_count=1, call_count=5) is True
    assert evaluator.llm_error_breach(error_count=1, call_count=4) is False


def test_robust_baseline_rejects_extreme_outlier_and_missing_burn_fails_safe():
    evaluator = FrozenSignalEvaluator()
    frozen = FrozenBaseline.capture([100, 100, 100, 100, 100, 10000], NOW)

    assert frozen.values[-1] == 10000
    assert frozen.cleaned_values == [100.0] * 5
    assert evaluator.latency_breached(frozen, [1600, 1620, 1640]) is True
    assert evaluator.error_rate_breach(
        error_rate=1.0,
        request_count=100,
        slo_target=0.99,
        short_burn=None,
        long_burn=None,
    ) == (True, "critical")


@pytest.mark.asyncio
async def test_restart_serialization_high_water_and_bounded_evidence():
    store = MemoryLifecycleStateStore()
    engine = LifecycleEngine(store, evidence_capacity=4)
    for sequence in range(1, 9):
        item = observation(sequence, breached=True)
        item.evidence = {"sequence": sequence}
        await engine.process(item, BASELINE)

    restored = MemoryLifecycleStateStore.from_json(await store.export_json())
    restarted = LifecycleEngine(restored, evidence_capacity=4)
    reset_sequence = observation(0, breached=True)
    reset_sequence.timestamp = NOW + timedelta(minutes=9)
    reset_sequence.event_id = "producer-restart-new-event"
    await restarted.process(reset_sequence, BASELINE)
    late = observation(99, breached=True)
    late.timestamp = NOW + timedelta(minutes=2)
    late.event_id = "late-old-event"
    ignored = await restarted.process(late, BASELINE)
    state = (await restored.list_all())[0]

    assert ignored.alert_state == AlertState.OUT_OF_ORDER_IGNORED
    assert state.last_processed_timestamp == reset_sequence.timestamp
    assert len(state.evidence_samples) == 4
    assert state.evidence_count == 8
    assert state.evidence_digest


class AlwaysConflictStore(MemoryLifecycleStateStore):
    async def compare_and_set(self, key, expected_version, record, ttl_seconds):
        return False


@pytest.mark.asyncio
async def test_cas_retry_exhaustion_fails_closed():
    engine = LifecycleEngine(AlwaysConflictStore(), max_conflict_retries=1)
    with pytest.raises(RuntimeError, match="CAS retries exhausted"):
        await engine.process(observation(1, breached=True), BASELINE)


class UnavailableValkey(FakeValkey):
    async def get(self, key):
        raise ConnectionError("unavailable")


@pytest.mark.asyncio
async def test_valkey_unavailable_is_explicit_persistence_failure():
    store = ValkeyLifecycleStateStore(UnavailableValkey())
    with pytest.raises(LifecyclePersistenceError, match="read failed"):
        await store.read("production::techx-tf4::checkout::latency")


def test_signal_contracts_reject_invalid_evidence():
    evaluator = FrozenSignalEvaluator()
    with pytest.raises(ValueError, match="NaN"):
        FrozenBaseline.capture([1.0, 2.0, 3.0, float("nan")], NOW)
    with pytest.raises(ValueError, match="between zero and one"):
        evaluator.error_rate_breach(error_rate=1.2, request_count=100)
    with pytest.raises(ValueError, match="errors <= calls"):
        evaluator.llm_error_breach(error_count=6, call_count=5)
