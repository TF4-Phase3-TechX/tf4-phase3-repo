"""Startup recovery gates readiness without entering a liveness restart loop."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

import app.main as main_mod


class ControlledRemediation:
    def __init__(self, *, failures: int = 0, gate: asyncio.Event | None = None):
        self.adapter = object()
        self.failures = failures
        self.gate = gate
        self.calls = 0

    async def reconcile_open_sagas(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise PermissionError("deployment patch permission temporarily unavailable")
        if self.gate is not None:
            await self.gate.wait()
        return []


class EmptySagaStore:
    def __init__(self):
        self.prune_calls = 0

    async def list_open(self):
        return []

    async def prune_terminal_before(self, _):
        self.prune_calls += 1
        return []


class ControlledWorker:
    def __init__(self):
        self.running = False
        self.started = asyncio.Event()
        self.stopped = asyncio.Event()
        self.run_calls = 0

    async def run(self):
        self.run_calls += 1
        self.running = True
        self.started.set()
        try:
            await self.stopped.wait()
        finally:
            self.running = False

    def stop(self):
        self.stopped.set()


class FakeTelemetry:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


def install_runtime(monkeypatch, remediation):
    saga_store = EmptySagaStore()
    worker = ControlledWorker()
    telemetry = FakeTelemetry()
    monkeypatch.setattr(main_mod, "remediation", remediation)
    monkeypatch.setattr(main_mod, "saga_store", saga_store)
    monkeypatch.setattr(main_mod, "worker", worker)
    monkeypatch.setattr(main_mod, "telemetry", telemetry)
    monkeypatch.setattr(
        main_mod,
        "settings",
        replace(main_mod.settings, startup_reconcile_retry_seconds=0.01),
    )
    return saga_store, worker, telemetry


@pytest.mark.asyncio
async def test_long_saga_recovery_keeps_health_live_but_readiness_closed(monkeypatch):
    recovery_gate = asyncio.Event()
    remediation = ControlledRemediation(gate=recovery_gate)
    saga_store, worker, telemetry = install_runtime(monkeypatch, remediation)

    async with main_mod.lifespan(None):
        assert await main_mod.healthz() == {"status": "ok"}
        with pytest.raises(main_mod.HTTPException) as exc_info:
            await main_mod.readyz()
        assert exc_info.value.status_code == 503
        assert worker.run_calls == 0

        recovery_gate.set()
        await asyncio.wait_for(worker.started.wait(), timeout=1)

        assert await main_mod.readyz() == {"status": "ready"}
        assert remediation.calls == 1
        assert saga_store.prune_calls == 1

    assert telemetry.closed is True
    assert worker.running is False


@pytest.mark.asyncio
async def test_cleanup_rbac_failure_retries_without_restarting_process(
    monkeypatch, caplog
):
    remediation = ControlledRemediation(failures=1)
    saga_store, worker, _ = install_runtime(monkeypatch, remediation)

    async with main_mod.lifespan(None):
        await asyncio.wait_for(worker.started.wait(), timeout=1)

        assert remediation.calls == 2
        assert worker.run_calls == 1
        assert saga_store.prune_calls == 1
        assert await main_mod.readyz() == {"status": "ready"}

    assert "startup_saga_reconcile_retry" in caplog.text


def test_startup_reconcile_retry_must_be_positive():
    with pytest.raises(
        ValueError, match="startup reconcile retry seconds must be positive"
    ):
        replace(main_mod.settings, startup_reconcile_retry_seconds=0)
