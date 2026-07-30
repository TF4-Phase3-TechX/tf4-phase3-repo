from __future__ import annotations

import json
from datetime import timedelta

import pytest

from app.models import utcnow
from app.saga import (
    FileSagaStore,
    GitTransaction,
    MemorySagaStore,
    RemediationSaga,
    SagaOutcome,
    SagaPersistenceError,
    SagaPhase,
    decide_restart_action,
)


def transaction(kind="remediation"):
    return GitTransaction(
        kind=kind,
        branch=f"aiops/{kind}/inc-restart",
        base_sha="a" * 40,
        known_good_sha="b" * 40,
        target_file="environments/production/app-values.yaml",
        before_hash="c" * 64,
        after_hash="d" * 64,
        before_file_sha="e" * 40,
        before_document={"sensitive_internal_body": True},
        after_document={"sensitive_internal_body": False},
    )


def test_v2_phase_and_restart_decision_table():
    saga = RemediationSaga(incident_id="inc-restart", target="product-reviews")
    assert decide_restart_action(saga) == "abandon_pre_merge"
    saga.remediation = transaction()
    saga.advance(SagaPhase.PR_OPEN)
    assert decide_restart_action(saga) == "rediscover_and_continue"
    saga.terminate(SagaOutcome.RESOLVED)
    assert decide_restart_action(saga) == "noop_terminal"


@pytest.mark.asyncio
async def test_v1_non_terminal_file_record_is_fail_closed(tmp_path):
    record = {
        "saga_id": "saga-v1",
        "incident_id": "inc-v1",
        "target": "product-reviews",
        "phase": "verifying",
        "outcome": "resolved",
        "mutation_attempted": True,
        "lease_held": True,
    }
    (tmp_path / "saga-v1.json").write_text(json.dumps(record), encoding="utf-8")
    saga = await FileSagaStore(tmp_path).get("saga-v1")
    assert saga.schema_version == 1
    assert saga.legacy_phase == "verifying"
    assert saga.is_open is True
    assert decide_restart_action(saga) == "block_legacy_v1"


@pytest.mark.asyncio
async def test_v1_terminal_record_is_retained_but_not_open(tmp_path):
    record = {
        "saga_id": "saga-v1-terminal",
        "incident_id": "inc-v1-terminal",
        "target": "product-reviews",
        "phase": "terminal",
        "outcome": "resolved",
    }
    (tmp_path / "saga-v1-terminal.json").write_text(
        json.dumps(record), encoding="utf-8"
    )
    saga = await FileSagaStore(tmp_path).get("saga-v1-terminal")
    assert saga.schema_version == 1
    assert saga.is_open is False


@pytest.mark.asyncio
async def test_file_store_round_trip_preserves_git_transactions(tmp_path):
    store = FileSagaStore(tmp_path)
    saga = RemediationSaga(
        incident_id="inc-restart",
        target="product-reviews",
        phase=SagaPhase.CHECKS_PENDING,
        remediation=transaction(),
        lock_held=True,
    )
    await store.save(saga)
    loaded = await store.get(saga.saga_id)
    assert loaded.schema_version == 2
    assert loaded.remediation.branch == "aiops/remediation/inc-restart"
    assert loaded.remediation.before_document == {"sensitive_internal_body": True}
    assert loaded.lock_held is True


@pytest.mark.asyncio
async def test_file_store_rejects_unreadable_record(tmp_path):
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    with pytest.raises(SagaPersistenceError, match="unreadable saga"):
        await FileSagaStore(tmp_path).list_all()


@pytest.mark.asyncio
async def test_exactly_one_saga_is_returned_by_incident():
    store = MemorySagaStore()
    saga = RemediationSaga(incident_id="inc-one", target="product-reviews")
    await store.save(saga)
    assert (await store.get_by_incident("inc-one")).saga_id == saga.saga_id
    assert await store.get_by_incident("missing") is None


@pytest.mark.asyncio
async def test_quarantine_survives_restart_until_operator_clear(tmp_path):
    store = FileSagaStore(tmp_path)
    saga = RemediationSaga(
        incident_id="inc-blocked",
        target="product-reviews",
        mutation_blocked=True,
    )
    saga.terminate(SagaOutcome.COMPENSATION_FAILED, "runtime restore unverified")
    await store.save(saga)

    reopened = FileSagaStore(tmp_path)
    assert (await reopened.list_open_for_target("product-reviews"))[0].is_open
    cleared = await reopened.clear_mutation_block_for_target("product-reviews")
    assert cleared == [saga.saga_id]
    assert await reopened.list_open_for_target("product-reviews") == []


@pytest.mark.asyncio
async def test_operator_cannot_clear_before_lease_cleanup():
    store = MemorySagaStore()
    saga = RemediationSaga(
        incident_id="inc-locked",
        target="product-reviews",
        mutation_blocked=True,
        lock_held=True,
    )
    saga.terminate(SagaOutcome.COMPENSATION_FAILED)
    await store.save(saga)
    with pytest.raises(SagaPersistenceError, match="cleanup is incomplete"):
        await store.clear_mutation_block_for_target("product-reviews")


@pytest.mark.asyncio
async def test_retention_prunes_only_clean_terminal_v2(tmp_path):
    store = FileSagaStore(tmp_path)
    old = RemediationSaga(incident_id="inc-old", target="product-reviews")
    old.terminate(SagaOutcome.RESOLVED)
    old.updated_at = (utcnow() - timedelta(hours=73)).isoformat()
    blocked = RemediationSaga(
        incident_id="inc-blocked",
        target="product-reviews",
        mutation_blocked=True,
    )
    blocked.terminate(SagaOutcome.COMPENSATION_FAILED)
    blocked.updated_at = (utcnow() - timedelta(hours=73)).isoformat()
    await store.save(old)
    await store.save(blocked)
    removed = await store.prune_terminal_before(utcnow() - timedelta(hours=72))
    assert removed == [old.saga_id]
    assert await store.get(blocked.saga_id) is not None


def test_public_evidence_sanitizes_document_bodies():
    saga = RemediationSaga(
        incident_id="inc-restart",
        target="product-reviews",
        remediation=transaction(),
    )
    payload = saga.public_evidence()
    encoded = json.dumps(payload)
    assert "before_document" not in encoded
    assert "after_document" not in encoded
    assert "sensitive_internal_body" not in encoded
    assert payload["remediation"]["branch"] == "aiops/remediation/inc-restart"
