"""Durable GitOps remediation saga.

Schema V2 records Git and runtime identities instead of Kubernetes templates.
Legacy V1 JSON remains readable so live activation can fail closed when an old
non-terminal direct-mutation transaction still exists.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import utcnow

log = logging.getLogger("aiops.saga")


class SagaPhase(str, Enum):
    PREFLIGHT = "PREFLIGHT"
    PR_OPEN = "PR_OPEN"
    CHECKS_PENDING = "CHECKS_PENDING"
    AWAITING_HUMAN_MERGE = "AWAITING_HUMAN_MERGE"
    MERGE_QUEUED = "MERGE_QUEUED"
    MERGED = "MERGED"
    RUNTIME_PENDING = "RUNTIME_PENDING"
    VERIFYING = "VERIFYING"
    COMPENSATING = "COMPENSATING"
    TERMINAL = "TERMINAL"


class SagaOutcome(str, Enum):
    NONE = "none"
    RESOLVED = "resolved"
    COMPENSATED_ESCALATED = "compensated_escalated"
    ESCALATED = "escalated"
    ABANDONED_PRE_MERGE = "abandoned_pre_merge"
    CHECKS_FAILED = "checks_failed"
    RUNTIME_TIMEOUT = "runtime_timeout"
    COMPENSATION_FAILED = "compensation_failed"
    STALE_BASE = "stale_base"
    PERSISTENCE_FAILED = "persistence_failed"
    LEGACY_V1_BLOCKED = "legacy_v1_blocked"


OPEN_PHASES = frozenset(phase for phase in SagaPhase if phase != SagaPhase.TERMINAL)


class GitTransaction(BaseModel):
    kind: str
    merge_strategy: str = "auto"
    branch: str
    base_sha: str
    policy_sha: str | None = None
    known_good_sha: str | None = None
    target_file: str
    before_hash: str
    after_hash: str
    before_file_sha: str | None = None
    after_file_sha: str | None = None
    head_sha: str | None = None
    pr_number: int | None = None
    pr_node_id: str | None = None
    pr_url: str | None = None
    checks: dict[str, str] = Field(default_factory=dict)
    merge_queued: bool = False
    merge_sha: str | None = None
    state: str = "prepared"
    # Required for exact compensation, but never returned by the evidence API.
    before_document: dict[str, Any] | None = None
    after_document: dict[str, Any] | None = None


_V1_TERMINAL = "terminal"


class RemediationSaga(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: int = 2
    saga_id: str = Field(default_factory=lambda: f"saga-{uuid4().hex[:12]}")
    incident_id: str
    incident_type: str = "service_latency_spike"
    target: str
    policy_version: str | None = None
    policy_sha: str | None = None
    base_sha: str | None = None
    known_good_sha: str | None = None
    phase: SagaPhase = SagaPhase.PREFLIGHT
    outcome: SagaOutcome = SagaOutcome.NONE
    remediation: GitTransaction | None = None
    compensation: GitTransaction | None = None
    expected_runtime_identity: dict[str, Any] = Field(default_factory=dict)
    runtime_observation: dict[str, Any] | None = None
    verification_samples: list[dict[str, Any]] = Field(default_factory=list)
    compensation_verification_samples: list[dict[str, Any]] = Field(
        default_factory=list
    )
    mutation_blocked: bool = False
    lock_held: bool = False
    escalation_reason: str | None = None
    generation: int = 0
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: utcnow().isoformat())
    terminal_reason: str | None = None
    audit: list[dict[str, Any]] = Field(default_factory=list)
    legacy_phase: str | None = None

    @model_validator(mode="before")
    @classmethod
    def read_v1_records(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "schema_version" in data:
            return data
        legacy_keys = {
            "original_template",
            "selected_template",
            "known_good_revision",
            "expected_template_after_action",
            "rollback_verification_samples",
            "rollback_phase",
            "mutation_attempted",
            "lease_held",
            "argo_window_active",
        }
        phase = data.get("phase")
        legacy_phases = {
            "created",
            "preflight",
            "lease_acquired",
            "argo_window_open",
            "action_acknowledged",
            "verifying",
            "rolling_back",
            "terminal",
        }
        if not (legacy_keys & set(data)) and phase not in legacy_phases:
            raw = dict(data)
            raw["schema_version"] = 2
            return raw
        raw = dict(data)
        legacy_phase = str(raw.get("phase", "created"))
        raw["schema_version"] = 1
        raw["legacy_phase"] = legacy_phase
        raw["phase"] = (
            SagaPhase.TERMINAL.value
            if legacy_phase == _V1_TERMINAL
            else SagaPhase.PREFLIGHT.value
        )
        legacy_outcome = str(raw.get("outcome", "none"))
        valid_outcomes = {item.value for item in SagaOutcome}
        raw["outcome"] = (
            legacy_outcome if legacy_outcome in valid_outcomes else "escalated"
        )
        raw["lock_held"] = bool(raw.get("lease_held", False))
        raw["mutation_blocked"] = bool(raw.get("mutation_blocked", False))
        raw.setdefault("incident_type", "service_latency_spike")
        return raw

    def note(self, event: str, **detail: Any) -> None:
        self.audit.append(
            {"at": utcnow().isoformat(), "event": event, "detail": detail}
        )
        self.updated_at = utcnow().isoformat()

    def advance(self, phase: SagaPhase, **detail: Any) -> None:
        self.phase = phase
        self.generation += 1
        self.note("phase_advanced", phase=phase.value, **detail)

    def terminate(self, outcome: SagaOutcome, reason: str | None = None) -> None:
        self.phase = SagaPhase.TERMINAL
        self.outcome = outcome
        self.terminal_reason = reason
        self.escalation_reason = reason if outcome != SagaOutcome.RESOLVED else None
        self.generation += 1
        self.note("saga_terminal", outcome=outcome.value, reason=reason)

    @property
    def is_open(self) -> bool:
        if self.schema_version == 1:
            return self.legacy_phase != _V1_TERMINAL or self.mutation_blocked
        return self.phase in OPEN_PHASES or self.lock_held or self.mutation_blocked

    def public_evidence(self) -> dict[str, Any]:
        """Return a sanitized API view with no file bodies or credentials."""

        def transaction(value: GitTransaction | None) -> dict[str, Any] | None:
            if value is None:
                return None
            return value.model_dump(
                mode="json",
                exclude={"before_document", "after_document"},
            )

        return {
            "schema_version": self.schema_version,
            "incident_id": self.incident_id,
            "incident_type": self.incident_type,
            "target": self.target,
            "phase": self.phase.value,
            "outcome": self.outcome.value,
            "policy_version": self.policy_version,
            "policy_sha": self.policy_sha,
            "base_sha": self.base_sha,
            "known_good_sha": self.known_good_sha,
            "remediation": transaction(self.remediation),
            "compensation": transaction(self.compensation),
            "expected_runtime_identity": self.expected_runtime_identity,
            "runtime_observation": self.runtime_observation,
            "verification_samples": self.verification_samples,
            "compensation_verification_samples": (
                self.compensation_verification_samples
            ),
            "mutation_blocked": self.mutation_blocked,
            "escalation_reason": self.escalation_reason,
            "updated_at": self.updated_at,
        }


class SagaStore(Protocol):
    async def save(self, saga: RemediationSaga) -> RemediationSaga: ...

    async def get(self, saga_id: str) -> RemediationSaga | None: ...

    async def get_by_incident(self, incident_id: str) -> RemediationSaga | None: ...

    async def list_open(self) -> list[RemediationSaga]: ...

    async def list_open_for_target(self, target: str) -> list[RemediationSaga]: ...

    async def list_all(self) -> list[RemediationSaga]: ...

    async def clear_mutation_block_for_target(self, target: str) -> list[str]: ...

    async def prune_terminal_before(self, cutoff: datetime) -> list[str]: ...


class SagaPersistenceError(RuntimeError):
    pass


class MemorySagaStore:
    def __init__(self) -> None:
        self._items: dict[str, RemediationSaga] = {}
        self._lock = asyncio.Lock()
        self.fail_next_save = False

    async def save(self, saga: RemediationSaga) -> RemediationSaga:
        async with self._lock:
            if self.fail_next_save:
                self.fail_next_save = False
                raise SagaPersistenceError("injected save failure")
            copy = RemediationSaga.model_validate(saga.model_dump(mode="json"))
            self._items[copy.saga_id] = copy
            return copy

    async def get(self, saga_id: str) -> RemediationSaga | None:
        async with self._lock:
            item = self._items.get(saga_id)
            return self._copy(item)

    async def get_by_incident(self, incident_id: str) -> RemediationSaga | None:
        async with self._lock:
            for item in self._items.values():
                if item.incident_id == incident_id:
                    return self._copy(item)
        return None

    async def list_open(self) -> list[RemediationSaga]:
        return [item for item in await self.list_all() if item.is_open]

    async def list_open_for_target(self, target: str) -> list[RemediationSaga]:
        return [item for item in await self.list_open() if item.target == target]

    async def list_all(self) -> list[RemediationSaga]:
        async with self._lock:
            return [self._copy(item) for item in self._items.values() if item]

    async def clear_mutation_block_for_target(self, target: str) -> list[str]:
        async with self._lock:
            blocked = [
                item
                for item in self._items.values()
                if item.target == target and item.mutation_blocked
            ]
            if any(
                item.phase != SagaPhase.TERMINAL or item.lock_held for item in blocked
            ):
                raise SagaPersistenceError(
                    f"cannot clear {target}: saga cleanup is incomplete"
                )
            for item in blocked:
                item.mutation_blocked = False
                item.note("mutation_block_cleared_by_operator", target=target)
            return [item.saga_id for item in blocked]

    async def prune_terminal_before(self, cutoff: datetime) -> list[str]:
        async with self._lock:
            removed = [
                key
                for key, item in self._items.items()
                if not item.is_open and datetime.fromisoformat(item.updated_at) < cutoff
            ]
            for key in removed:
                del self._items[key]
            return removed

    @staticmethod
    def _copy(item: RemediationSaga | None) -> RemediationSaga | None:
        return (
            RemediationSaga.model_validate(item.model_dump(mode="json"))
            if item is not None
            else None
        )


class FileSagaStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self.fail_next_save = False

    def _path(self, saga_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in saga_id)
        return self.root / f"{safe}.json"

    def _write_unlocked(self, saga: RemediationSaga) -> RemediationSaga:
        path = self._path(saga.saga_id)
        temporary = path.with_suffix(".tmp")
        payload = saga.model_dump(mode="json")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        os.replace(temporary, path)
        return RemediationSaga.model_validate(payload)

    async def save(self, saga: RemediationSaga) -> RemediationSaga:
        async with self._lock:
            if self.fail_next_save:
                self.fail_next_save = False
                raise SagaPersistenceError("injected file save failure")
            return self._write_unlocked(saga)

    async def get(self, saga_id: str) -> RemediationSaga | None:
        path = self._path(saga_id)
        if not path.exists():
            return None
        return self._read(path)

    async def get_by_incident(self, incident_id: str) -> RemediationSaga | None:
        for saga in await self.list_all():
            if saga.incident_id == incident_id:
                return saga
        return None

    async def list_open(self) -> list[RemediationSaga]:
        return [item for item in await self.list_all() if item.is_open]

    async def list_open_for_target(self, target: str) -> list[RemediationSaga]:
        return [item for item in await self.list_open() if item.target == target]

    async def list_all(self) -> list[RemediationSaga]:
        async with self._lock:
            return [self._read(path) for path in sorted(self.root.glob("*.json"))]

    async def clear_mutation_block_for_target(self, target: str) -> list[str]:
        async with self._lock:
            blocked = [
                self._read(path)
                for path in sorted(self.root.glob("*.json"))
                if self._read(path).target == target
            ]
            blocked = [item for item in blocked if item.mutation_blocked]
            if any(
                item.phase != SagaPhase.TERMINAL or item.lock_held for item in blocked
            ):
                raise SagaPersistenceError(
                    f"cannot clear {target}: saga cleanup is incomplete"
                )
            for item in blocked:
                item.mutation_blocked = False
                item.note("mutation_block_cleared_by_operator", target=target)
                self._write_unlocked(item)
            return [item.saga_id for item in blocked]

    async def prune_terminal_before(self, cutoff: datetime) -> list[str]:
        async with self._lock:
            removed: list[str] = []
            for path in sorted(self.root.glob("*.json")):
                saga = self._read(path)
                if saga.is_open or datetime.fromisoformat(saga.updated_at) >= cutoff:
                    continue
                path.unlink()
                removed.append(saga.saga_id)
            return removed

    @staticmethod
    def _read(path: Path) -> RemediationSaga:
        try:
            return RemediationSaga.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.error(
                json.dumps(
                    {
                        "event": "saga_record_unreadable",
                        "path": str(path),
                        "error": str(exc),
                    }
                )
            )
            raise SagaPersistenceError(f"unreadable saga record {path}: {exc}") from exc


def build_saga_store(
    backend: str = "memory", path: str | None = None
) -> MemorySagaStore | FileSagaStore:
    kind = (backend or "memory").strip().lower()
    if kind in {"", "memory", "mem", "none", "off"}:
        return MemorySagaStore()
    if kind in {"file", "fs", "json"}:
        if not path:
            raise ValueError("AIOPS_SAGA_PATH is required when saga backend is file")
        return FileSagaStore(path)
    raise ValueError(f"unsupported AIOPS_SAGA_BACKEND: {backend!r}")


def has_open_v1(sagas: list[RemediationSaga]) -> bool:
    return any(saga.schema_version == 1 and saga.is_open for saga in sagas)


def decide_restart_action(saga: RemediationSaga) -> str:
    if saga.schema_version == 1:
        return "block_legacy_v1" if saga.is_open else "noop_terminal"
    if saga.phase == SagaPhase.TERMINAL:
        return "noop_terminal"
    if saga.phase == SagaPhase.PREFLIGHT and saga.remediation is None:
        return "abandon_pre_merge"
    return "rediscover_and_continue"
