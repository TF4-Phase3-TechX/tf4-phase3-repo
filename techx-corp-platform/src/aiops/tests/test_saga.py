"""Offline durable saga + restart reconcile tests (TF4AIO-89)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from app.config import Settings
from app.models import Incident, IncidentStatus, utcnow
from app.remediation import PolicyDenied, RemediationController
from app.saga import (
    FileSagaStore,
    MemorySagaStore,
    RemediationSaga,
    SagaOutcome,
    SagaPersistenceError,
    SagaPhase,
    argo_window_annotations,
    build_saga_store,
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
        verification_consecutive_healthy_polls=1,
        argo_window_enabled=True,
        # Required by #669 live pin (AIOPS_KNOWN_GOOD_REVISIONS).
        known_good_revisions={"product-reviews": "1"},
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


def test_argo_window_does_not_overwrite_reserved_argo_annotations():
    annotations = argo_window_annotations("inc-1", utcnow().isoformat())

    assert "argocd.argoproj.io/compare-options" not in annotations
    assert annotations["aiops.techx/mutation-window"] == "inc-1"


def test_configmap_backend_is_rejected_until_implemented(tmp_path: Path):
    with pytest.raises(ValueError, match="not implemented"):
        build_saga_store("configmap", str(tmp_path))


@pytest.mark.asyncio
async def test_unreadable_record_fails_closed(tmp_path: Path):
    (tmp_path / "corrupt.json").write_text("{not-json", encoding="utf-8")
    store = FileSagaStore(tmp_path)

    with pytest.raises(SagaPersistenceError, match="unreadable saga record"):
        await store.list_open()


@pytest.mark.asyncio
async def test_terminal_saga_retries_external_ownership_cleanup():
    store = MemorySagaStore()
    saga = RemediationSaga(
        incident_id="inc-cleanup",
        target="product-reviews",
        argo_window_active=True,
        lease_held=True,
    )
    saga.terminate(SagaOutcome.RESOLVED, "business outcome complete")
    assert saga.is_open is True
    await store.save(saga)

    adapter = TrackingAdapter()
    controller = make_controller(adapter, store)
    results = await controller.reconcile_open_sagas()

    reloaded = await store.get(saga.saga_id)
    assert results[0]["action"] == "noop_terminal"
    assert results[0]["cleanup"] == "complete"
    assert adapter.argo_closed == ["inc-cleanup"]
    assert reloaded.argo_window_active is False
    assert reloaded.lease_held is False
    assert reloaded.is_open is False


@pytest.mark.asyncio
async def test_retention_prunes_only_old_fully_cleaned_terminal_sagas(tmp_path: Path):
    store = FileSagaStore(tmp_path)
    old = RemediationSaga(incident_id="old", target="product-reviews")
    old.terminate(SagaOutcome.RESOLVED)
    old.updated_at = (utcnow() - timedelta(hours=73)).isoformat()
    fresh = RemediationSaga(incident_id="fresh", target="product-reviews")
    fresh.terminate(SagaOutcome.RESOLVED)
    old_with_cleanup = RemediationSaga(
        incident_id="old-open",
        target="product-reviews",
        argo_window_active=True,
    )
    old_with_cleanup.terminate(SagaOutcome.RESOLVED)
    old_with_cleanup.updated_at = (utcnow() - timedelta(hours=73)).isoformat()
    for saga in (old, fresh, old_with_cleanup):
        await store.save(saga)

    removed = await store.prune_terminal_before(
        utcnow() - timedelta(hours=72)
    )

    assert removed == [old.saga_id]
    assert await store.get(old.saga_id) is None
    assert await store.get(fresh.saga_id) is not None
    assert await store.get(old_with_cleanup.saga_id) is not None


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
    assert reloaded.is_open is False


@pytest.mark.asyncio
async def test_restart_after_lease_or_argo_window_clears_ownership(tmp_path: Path):
    """P1 (HuyVu12): abandon_pre_mutation must release Lease/Argo markers.

    Otherwise is_open stays true and list_open_for_target permanently blocks
    the target after a crash between LEASE_ACQUIRED / ARGO_WINDOW_OPEN and
    the live patch.
    """

    store = FileSagaStore(tmp_path)
    saga = RemediationSaga(
        incident_id="inc-lease-argo",
        target="product-reviews",
        phase=SagaPhase.ARGO_WINDOW_OPEN,
        lease_held=True,
        argo_window_active=True,
        mutation_attempted=False,
    )
    await store.save(saga)

    adapter = TrackingAdapter()
    controller = make_controller(adapter, store)
    results = await controller.reconcile_open_sagas()
    assert results[0]["action"] == "abandon_pre_mutation"
    assert results[0]["still_open"] is False
    reloaded = await store.get(saga.saga_id)
    assert reloaded.outcome == SagaOutcome.ABANDONED_PRE_MUTATION
    assert reloaded.lease_held is False
    assert reloaded.argo_window_active is False
    assert reloaded.is_open is False
    assert adapter.argo_closed == ["inc-lease-argo"]
    # Target must be free for a later remediation cycle.
    assert await store.list_open_for_target("product-reviews") == []


@pytest.mark.asyncio
async def test_resume_uses_controller_adapter_not_none():
    """P1 (HuyVu12): resume_saga must not take adapter-is-None when wired."""

    store = MemorySagaStore()
    adapter = TrackingAdapter()
    adapter.current = adapter.previous
    saga = RemediationSaga(
        incident_id="inc-resume-adapter",
        target="product-reviews",
        phase=SagaPhase.VERIFYING,
        mutation_attempted=True,
        original_template={
            "metadata": {"labels": {"version": "current"}},
            "spec": {"containers": [{"name": "app", "image": "bad:1"}]},
        },
        selected_template=adapter.previous,
        expected_template_after_action=adapter.previous,
        argo_window_active=True,
    )
    await store.save(saga)
    controller = make_controller(adapter, store, healthy=True)
    assert controller.adapter is adapter
    results = await controller.reconcile_open_sagas()
    assert results[0]["action"] == "continue_verification"
    assert results[0]["outcome"] == SagaOutcome.RESOLVED.value
    reloaded = await store.get(saga.saga_id)
    assert reloaded.outcome == SagaOutcome.RESOLVED
    assert reloaded.is_open is False


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
        verification_consecutive_healthy_polls=1,
        argo_window_enabled=True,
        known_good_revisions={"product-reviews": "1"},
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
async def test_restart_checkpoints_rollback_intent_before_restore():
    store = MemorySagaStore()
    adapter = TrackingAdapter()
    adapter.current = adapter.previous
    saga = RemediationSaga(
        incident_id="inc-checkpoint",
        target="product-reviews",
        phase=SagaPhase.VERIFYING,
        mutation_attempted=True,
        original_template={
            "metadata": {"labels": {"version": "current"}},
            "spec": {"containers": [{"name": "app", "image": "bad:1"}]},
        },
        selected_template=adapter.previous,
        expected_template_after_action=adapter.previous,
    )
    await store.save(saga)
    store.fail_next_save = True
    controller = make_controller(adapter, store, healthy=False)

    with pytest.raises(SagaPersistenceError, match="injected save failure"):
        await controller.reconcile_open_sagas()

    # The durable rollback checkpoint failed, so recovery must not mutate.
    assert adapter.patches == []


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
async def test_restart_quarantine_blocks_new_mutation_until_operator_clear(
    tmp_path: Path,
):
    """A terminal fail-closed saga remains authoritative across processes."""

    store = FileSagaStore(tmp_path)
    quarantined = RemediationSaga(
        incident_id="inc-quarantined",
        target="product-reviews",
        phase=SagaPhase.TERMINAL,
        outcome=SagaOutcome.ESCALATED,
        mutation_attempted=True,
        mutation_blocked=True,
        terminal_reason="mutation outcome unknown",
    )
    await store.save(quarantined)

    adapter = TrackingAdapter()
    controller = make_controller(adapter, store, healthy=True)
    fresh = incident()
    fresh.incident_id = "inc-after-restart"
    controller.request_approval(fresh)
    controller.approve(fresh)

    with pytest.raises(PolicyDenied, match="Open remediation saga"):
        await controller.execute(fresh)
    assert adapter.patches == []
    assert (await store.get(quarantined.saga_id)).is_open is True

    cleared = await store.clear_mutation_block_for_target("product-reviews")
    assert cleared == [quarantined.saga_id]
    assert await store.list_open_for_target("product-reviews") == []

    await controller.execute(fresh)
    assert len(adapter.patches) == 1


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
