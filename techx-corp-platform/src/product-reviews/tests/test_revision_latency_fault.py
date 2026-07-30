import pytest

from revision_latency_fault import (
    DELAY_ENV,
    MAX_DELAY_MS,
    MAX_REQUESTS,
    MAX_TTL_SECONDS,
    REQUEST_BUDGET_ENV,
    TTL_ENV,
    RevisionLatencyFault,
)


def test_fault_is_disabled_by_default():
    slept = []
    fault = RevisionLatencyFault.from_env({}, sleep=slept.append)

    assert fault.enabled is False
    assert fault.apply() is None
    assert slept == []


def test_fault_applies_configured_delay_and_reports_audit_fields():
    now = [100.0]
    slept = []
    fault = RevisionLatencyFault.from_env(
        {
            DELAY_ENV: "2500",
            TTL_ENV: "600",
            REQUEST_BUDGET_ENV: "30",
        },
        clock=lambda: now[0],
        sleep=slept.append,
    )

    applied = fault.apply()

    assert applied is not None
    assert applied.delay_ms == 2500
    assert applied.request_ordinal == 1
    assert applied.seconds_remaining == 600
    assert slept == [2.5]


def test_fault_auto_disables_after_ttl():
    now = [100.0]
    slept = []
    fault = RevisionLatencyFault(
        delay_ms=2500,
        ttl_seconds=10,
        max_requests=10,
        clock=lambda: now[0],
        sleep=slept.append,
    )

    assert fault.apply() is not None
    now[0] = 110.0
    assert fault.apply() is None
    assert slept == [2.5]


def test_fault_ttl_starts_on_first_request_not_process_start():
    now = [100.0]
    slept = []
    fault = RevisionLatencyFault(
        delay_ms=2500,
        ttl_seconds=10,
        max_requests=10,
        clock=lambda: now[0],
        sleep=slept.append,
    )

    # Simulate a GitOps approval window much longer than the bounded TTL.
    now[0] = 1_000.0
    first = fault.apply()
    now[0] = 1_009.0
    second = fault.apply()
    now[0] = 1_010.0

    assert first is not None
    assert first.seconds_remaining == 10
    assert second is not None
    assert second.seconds_remaining == 1
    assert fault.apply() is None
    assert slept == [2.5, 2.5]


def test_fault_auto_disables_after_request_budget():
    slept = []
    fault = RevisionLatencyFault(
        delay_ms=2500,
        ttl_seconds=10,
        max_requests=2,
        clock=lambda: 100.0,
        sleep=slept.append,
    )

    assert fault.apply().request_ordinal == 1
    assert fault.apply().request_ordinal == 2
    assert fault.apply() is None
    assert slept == [2.5, 2.5]


@pytest.mark.parametrize(
    ("key", "value", "match"),
    [
        (DELAY_ENV, str(MAX_DELAY_MS + 1), "delay_ms"),
        (TTL_ENV, str(MAX_TTL_SECONDS + 1), "ttl_seconds"),
        (REQUEST_BUDGET_ENV, str(MAX_REQUESTS + 1), "max_requests"),
    ],
)
def test_hard_caps_cannot_be_raised_by_configuration(key, value, match):
    values = {
        DELAY_ENV: "2500",
        TTL_ENV: "600",
        REQUEST_BUDGET_ENV: "30",
        key: value,
    }

    with pytest.raises(ValueError, match=match):
        RevisionLatencyFault.from_env(values)


@pytest.mark.parametrize("missing", [TTL_ENV, REQUEST_BUDGET_ENV])
def test_enabled_fault_requires_both_deadmen(missing):
    values = {
        DELAY_ENV: "2500",
        TTL_ENV: "600",
        REQUEST_BUDGET_ENV: "30",
    }
    values.pop(missing)

    with pytest.raises(ValueError, match=missing):
        RevisionLatencyFault.from_env(values)
