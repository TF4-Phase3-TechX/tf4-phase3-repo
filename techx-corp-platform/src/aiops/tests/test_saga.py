"""Offline durable saga + restart reconcile tests (TF4AIO-89)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.config import Settings
from app.models import Incident, IncidentStatus
from app.remediation import PolicyDenied, RemediationController
from app.saga import (
    FileSagaStore,
    MemorySagaStore,
    RemediationSaga,
    SagaOutcome,
    SagaPhase,
    decide_restart_action,
    templates_equivalent,
)


def incident(service="product-reviews"):
    return Incident(
        incident_type="service_latency_spike",
        severity="high",
        affected_service=service,
        confidence=0.9,
        suspected_root_cause="recent deploy",
        runbook_id="deployment-latency-rollback",
        recommended_action="rollback",
    )


class TrackingAdapter:
    def __init__(self, *, current=None, previous=None):
        self.current = current or {
            "metadata": {"labels": {"version": "current"}},
            "spec": {"containers": [{"name": "app", "image": "bad:1"}]},
        }
        self.previous = previous or {
            "metadata": {"labels": {"version": "previous"}},
            "spec": {"containers": [{"name": "app", "image": "good:1"}]},
        }
        self.patches: list[dict] = []
        self.locks: list[str] = []
        self.argo_open: list[str] = []
        self.argo_closed: list[str] = []
        self.hold_lease = False
        self.fail_patch_once = False

    def acquire_lock(self, deployment, incident_id, ttl):
        if self.hold_lease:
            return False
        self.locks.append(incident_id)
        return True

    def release_lock(self, deployment, incident_id):
        return None

    def previous_template(self, deployment):
        return self.current, self.previous

    def patch_template(self, deployment, template):
        if self.fail_patch_once:
            self.fail_patch_once = False
            raise TimeoutError("ambiguous transport error")
        self.patches.append(template)
        self.current = template

    def dry_run_patch_template(self, deployment, template):
        return None

    def rollout_ready(self, deployment):
        return True

    def read_template(self, deployment):
        return self.current

    def begin_argo_window(self, deployment, incident_id, ttl):
        self.argo_open.append(incident_id)
        return {"aiops.techx/mutation-window": incident_id}

    def end_argo_window(self, deployment, incident_id):
        self.argo_closed.append(incident_id)


def make_controller(adapter, saga_store=None, healthy=True, **settings_kwargs):
    async def verifier(_):
        return {"healthy": healthy, "p95_latency_ms": 10 if healthy else 5000}

    settings = replace(
        Settings(),
        remediation_mode="live",
        verification_polls=1,
        rollback_verification_polls=1,
        verification_settle_seconds=0,
        verification_interval_seconds=0,
        argo_window_enabled=True,
        **settings_kwargs,
    )
    return RemediationController(
        settings,
        adapter=adapter,
        verifier=verifier,
        saga_store=saga_store or MemorySagaStore(),
    )


def test_decide_restart_action_table():
    pre = RemediationSaga(incident_id="i1", target="svc", phase=SagaPhase.PREFLIGHT)
    assert decide_restart_action(pre) == "abandon_pre_mutation"

    verifying = RemediationSaga(
        incident_id="i1",
        target="svc",
        phase=SagaPhase.VERIFYING,
        mutation_attempted=True,
        original_template={"a": 1},
        selected_template={"b": 2},
    )
    assert decide_restart_action(verifying) == "continue_verification"

    rolling = RemediationSaga(
        incident_id="i1",
        target="svc",
        phase=SagaPhase.ROLLING_BACK,
        mutation_attempted=True,
        original_template={"a": 1},
    )
    assert decide_restart_action(rolling) == "restore_original"

    incomplete = RemediationSaga(
        incident_id="i1",
        target="svc",
        phase=SagaPhase.ACTION_ACKNOWLEDGED,
        mutation_attempted=True,
    )
    assert decide_restart_action(incomplete) == "fail_closed_escalate"


def test_templates_equivalent():
    assert templates_equivalent({"x": 1}, {"x": 1})
    assert not templates_equivalent({"x": 1}, {"x": 2})


@pytest.mark.asyncio
async def test_execute_persists_terminal_resolved_saga():
    adapter = TrackingAdapter()
    store = MemorySagaStore()
    controller = make_controller(adapter, store, healthy=True)
    item = incident()
    controller.request_approval(item)
    controller.approve(item)
    await controller.execute(item)

    assert item.status == IncidentStatus.RESOLVED
    sagas = await store.list_all()
    assert len(sagas) == 1
    saga = sagas[0]
    assert saga.phase == SagaPhase.TERMINAL
    assert saga.outcome == SagaOutcome.RESOLVED
    assert saga.original_template is not None
    assert saga.selected_template is not None
    assert adapter.argo_open and adapter.argo_closed


@pytest.mark.asyncio
async def test_second_mutation_blocked_while_open_saga_exists():
    adapter = TrackingAdapter()
    store = MemorySagaStore()
    open_saga = RemediationSaga(
        incident_id="inc-open",
        target="product-reviews",
        phase=SagaPhase.VERIFYING,
        mutation_attempted=True,
        original_template={"a": 1},
        selected_template={"b": 2},
    )
    await store.save(open_saga)
    controller = make_controller(adapter, store, healthy=True)
    item = incident()
    controller.request_approval(item)
    controller.approve(item)
    with pytest.raises(PolicyDenied, match="Open remediation saga"):
        await controller.execute(item)
    assert adapter.patches == []


@pytest.mark.asyncio
async def test_restart_after_preflight_abandons_without_mutation(tmp_path: Path):
    store = FileSagaStore(tmp_path)
    saga = RemediationSaga(
        incident_id="inc-pre",
        target="product-reviews",
        phase=SagaPhase.PREFLIGHT,
    )
    await store.save(saga)

    adapter = TrackingAdapter()
    controller = make_controller(adapter, store)
    results = await controller.reconcile_open_sagas()
    assert results[0]["action"] == "abandon_pre_mutation"
    reloaded = await store.get(saga.saga_id)
    assert reloaded.outcome == SagaOutcome.ABANDONED_PRE_MUTATION
    assert adapter.patches == []


@pytest.mark.asyncio
async def test_restart_after_action_ack_continues_verification(tmp_path: Path):
    store = FileSagaStore(tmp_path)
    adapter = TrackingAdapter()
    # Cluster already at known-good (mutation applied before crash).
    adapter.current = adapter.previous
    saga = RemediationSaga(
        incident_id="inc-ack",
        target="product-reviews",
        phase=SagaPhase.ACTION_ACKNOWLEDGED,
        mutation_attempted=True,
        original_template=adapter.current
        and {
            "metadata": {"labels": {"version": "current"}},
            "spec": {"containers": [{"name": "app", "image": "bad:1"}]},
        },
        selected_template=adapter.previous,
        expected_template_after_action=adapter.previous,
        argo_window_active=True,
    )
    # Fix original to true bad template independent of current.
    saga.original_template = {
        "metadata": {"labels": {"version": "current"}},
        "spec": {"containers": [{"name": "app", "image": "bad:1"}]},
    }
    await store.save(saga)

    controller = make_controller(adapter, store, healthy=True)
    results = await controller.reconcile_open_sagas()
    assert results[0]["action"] == "continue_verification"
    reloaded = await store.get(saga.saga_id)
    assert reloaded.outcome == SagaOutcome.RESOLVED


@pytest.mark.asyncio
async def test_restart_during_verification_restores_when_unhealthy(tmp_path: Path):
    store = FileSagaStore(tmp_path)
    adapter = TrackingAdapter()
    adapter.current = adapter.previous
    original = {
        "metadata": {"labels": {"version": "current"}},
        "spec": {"containers": [{"name": "app", "image": "bad:1"}]},
    }
    saga = RemediationSaga(
        incident_id="inc-ver",
        target="product-reviews",
        phase=SagaPhase.VERIFYING,
        mutation_attempted=True,
        original_template=original,
        selected_template=adapter.previous,
        expected_template_after_action=adapter.previous,
    )
    await store.save(saga)

    async def verifier(_):
        # Post-mutation template is unhealthy; original is healthy after restore.
        on_mutation = templates_equivalent(adapter.current, adapter.previous)
        return {
            "healthy": not on_mutation,
            "p95_latency_ms": 9000 if on_mutation else 10,
        }

    settings = replace(
        Settings(),
        remediation_mode="live",
        verification_polls=1,
        rollback_verification_polls=1,
        verification_settle_seconds=0,
        verification_interval_seconds=0,
        argo_window_enabled=True,
    )
    controller = RemediationController(
        settings, adapter=adapter, verifier=verifier, saga_store=store
    )
    results = await controller.reconcile_open_sagas()
    assert results[0]["action"] == "continue_verification"
    reloaded = await store.get(saga.saga_id)
    assert reloaded.outcome == SagaOutcome.ROLLED_BACK
    assert adapter.patches[-1] == original


@pytest.mark.asyncio
async def test_restart_during_rollback_restores_original(tmp_path: Path):
    store = FileSagaStore(tmp_path)
    adapter = TrackingAdapter()
    original = {
        "metadata": {"labels": {"version": "current"}},
        "spec": {"containers": [{"name": "app", "image": "bad:1"}]},
    }
    saga = RemediationSaga(
        incident_id="inc-rb",
        target="product-reviews",
        phase=SagaPhase.ROLLING_BACK,
        mutation_attempted=True,
        original_template=original,
        selected_template=adapter.previous,
        rollback_phase="started",
    )
    await store.save(saga)
    controller = make_controller(adapter, store, healthy=True)
    results = await controller.reconcile_open_sagas()
    assert results[0]["action"] == "restore_original"
    reloaded = await store.get(saga.saga_id)
    assert reloaded.outcome == SagaOutcome.ROLLED_BACK
    assert adapter.patches[-1] == original


@pytest.mark.asyncio
async def test_lost_lease_on_restart_fails_closed():
    store = MemorySagaStore()
    saga = RemediationSaga(
        incident_id="inc-lease",
        target="product-reviews",
        phase=SagaPhase.VERIFYING,
        mutation_attempted=True,
        original_template={"a": 1},
        selected_template={"b": 2},
        expected_template_after_action={"b": 2},
    )
    await store.save(saga)
    adapter = TrackingAdapter()
    adapter.hold_lease = True
    controller = make_controller(adapter, store, healthy=True)
    results = await controller.reconcile_open_sagas()
    assert results[0]["lease"] == "lost"
    reloaded = await store.get(saga.saga_id)
    assert reloaded.outcome == SagaOutcome.ESCALATED
    assert reloaded.mutation_blocked is True
    assert adapter.patches == []


@pytest.mark.asyncio
async def test_conflicting_desired_state_detected_on_resume():
    store = MemorySagaStore()
    adapter = TrackingAdapter()
    # Cluster drifted to a third template (Argo self-heal).
    adapter.current = {
        "metadata": {"labels": {"version": "gitops"}},
        "spec": {"containers": [{"name": "app", "image": "git:1"}]},
    }
    original = {
        "metadata": {"labels": {"version": "current"}},
        "spec": {"containers": [{"name": "app", "image": "bad:1"}]},
    }
    expected = {
        "metadata": {"labels": {"version": "previous"}},
        "spec": {"containers": [{"name": "app", "image": "good:1"}]},
    }
    saga = RemediationSaga(
        incident_id="inc-conflict",
        target="product-reviews",
        phase=SagaPhase.VERIFYING,
        mutation_attempted=True,
        original_template=original,
        selected_template=expected,
        expected_template_after_action=expected,
    )
    await store.save(saga)
    controller = make_controller(adapter, store, healthy=True)
    results = await controller.reconcile_open_sagas()
    reloaded = await store.get(saga.saga_id)
    assert reloaded.outcome == SagaOutcome.CONFLICTING_DESIRED_STATE
    assert adapter.patches[-1] == original
    assert results[0]["outcome"] == SagaOutcome.CONFLICTING_DESIRED_STATE.value


@pytest.mark.asyncio
async def test_failed_persistence_fails_closed():
    adapter = TrackingAdapter()
    store = MemorySagaStore()
    store.fail_next_save = True
    controller = make_controller(adapter, store, healthy=True)
    item = incident()
    controller.request_approval(item)
    controller.approve(item)
    await controller.execute(item)
    assert item.status == IncidentStatus.ESCALATED
    assert item.mutation_blocked is True
    assert "Saga persistence failed" in (item.escalation_reason or "")
    assert adapter.patches == []


@pytest.mark.asyncio
async def test_argo_overwrite_during_live_execute():
    class OverwriteAdapter(TrackingAdapter):
        def patch_template(self, deployment, template):
            # Simulate Argo immediately restoring Git desired state.
            self.patches.append(template)
            self.current = {
                "metadata": {"labels": {"version": "gitops"}},
                "spec": {"containers": [{"name": "app", "image": "git:1"}]},
            }

    adapter = OverwriteAdapter()
    store = MemorySagaStore()
    controller = make_controller(adapter, store, healthy=True)
    item = incident()
    controller.request_approval(item)
    controller.approve(item)
    await controller.execute(item)
    assert item.status == IncidentStatus.ESCALATED
    assert item.mutation_blocked is True
    assert "overwrote" in (item.escalation_reason or "").lower()
    sagas = await store.list_all()
    assert sagas[0].outcome == SagaOutcome.ARGO_OVERWRITE


@pytest.mark.asyncio
async def test_stale_open_saga_and_new_controller_never_double_mutate(tmp_path: Path):
    """Simulate process crash mid-verify then a new process resume."""

    store = FileSagaStore(tmp_path)
    adapter1 = TrackingAdapter()
    controller1 = make_controller(adapter1, store, healthy=True)
    item = incident()
    controller1.request_approval(item)
    controller1.approve(item)

    # Manually craft a mid-flight saga as if crash happened after action.
    adapter1.current = adapter1.previous
    saga = RemediationSaga(
        incident_id=item.incident_id,
        target=item.affected_service,
        phase=SagaPhase.VERIFYING,
        mutation_attempted=True,
        original_template={
            "metadata": {"labels": {"version": "current"}},
            "spec": {"containers": [{"name": "app", "image": "bad:1"}]},
        },
        selected_template=adapter1.previous,
        expected_template_after_action=adapter1.previous,
        argo_window_active=True,
    )
    await store.save(saga)

    # New process / new controller, same durable store.
    adapter2 = TrackingAdapter()
    adapter2.current = adapter1.previous
    controller2 = make_controller(adapter2, store, healthy=True)
    with pytest.raises(PolicyDenied, match="Open remediation saga"):
        # Must not start a second mutation while open saga exists.
        item2 = incident()
        item2.incident_id = "inc-second"
        controller2.request_approval(item2)
        controller2.approve(item2)
        await controller2.execute(item2)

    results = await controller2.reconcile_open_sagas()
    assert results[0]["action"] == "continue_verification"
    assert (await store.get(saga.saga_id)).phase == SagaPhase.TERMINAL
