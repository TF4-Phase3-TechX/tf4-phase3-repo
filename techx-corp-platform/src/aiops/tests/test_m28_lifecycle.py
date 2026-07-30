from datetime import datetime, timedelta, timezone

import pytest

from app.lifecycle import (
    AlertState,
    FrozenBaseline,
    FrozenSignalEvaluator,
    Lifecycle,
    LifecycleEngine,
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
        service="checkout",
        incident_type="service_latency_spike",
        breached=breached,
        primary_telemetry_available=primary,
        traffic_sufficient=traffic,
        value=1600.0 if breached else 100.0,
        incident_id_hint="incident-a",
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
    assert event.incident_id == "incident-a"
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
    assert flapped.incident_id == "incident-a"
    state = (await store.list_all())[0]
    assert state.healthy_streak == 0


class FakeValkey:
    def __init__(self):
        self.items = {}

    async def get(self, key):
        return self.items.get(key)

    async def eval(self, script, number_of_keys, key, expected, payload, ttl):
        del script, number_of_keys, ttl
        import json

        current = (
            json.loads(self.items[key])["state_version"] if key in self.items else 0
        )
        if current != int(expected):
            return 0
        self.items[key] = payload
        return 1

    async def scan_iter(self, match):
        prefix = match[:-1]
        for key in self.items:
            if key.startswith(prefix):
                yield key


@pytest.mark.asyncio
async def test_valkey_store_enforces_state_version_cas():
    store = ValkeyLifecycleStateStore(FakeValkey())
    engine = LifecycleEngine(store)
    await engine.process(observation(1, breached=True), BASELINE)
    record = (await store.list_all())[0]

    stale = record.model_copy(deep=True)
    stale.state_version = 0
    assert await store.compare_and_set(record.state_key, 0, stale, 3600) is False
    assert (await store.read(record.state_key)).state_version == 1


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


def test_signal_contracts_reject_invalid_evidence():
    evaluator = FrozenSignalEvaluator()
    with pytest.raises(ValueError, match="NaN"):
        FrozenBaseline.capture([1.0, 2.0, 3.0, float("nan")], NOW)
    with pytest.raises(ValueError, match="between zero and one"):
        evaluator.error_rate_breach(error_rate=1.2, request_count=100)
    with pytest.raises(ValueError, match="errors <= calls"):
        evaluator.llm_error_breach(error_count=6, call_count=5)
