"""Durable remediation saga persistence and restart reconciliation (TF4AIO-89).

A Kubernetes Lease alone prevents concurrent AIOps ownership; it does not record
what phase the controller reached before a crash. This module persists
intent/state outside process memory so startup can continue verification,
restore the captured original template, or fail closed — never silently start a
second mutation on the same target.
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

from pydantic import BaseModel, Field

from .models import utcnow

log = logging.getLogger("aiops.saga")

ARGO_WINDOW_ANNOTATION = "aiops.techx/mutation-window"
ARGO_WINDOW_UNTIL_ANNOTATION = "aiops.techx/mutation-window-until"
ARGO_OWNER_ANNOTATION = "aiops.techx/owned-by-incident"
# Documented contract: Application-level ignoreDifferences must also cover
# /spec/template during the window. Deployment annotations alone do not pause
# Argo; they give AIOps an ownership marker and enable overwrite detection.


class SagaPhase(str, Enum):
    CREATED = "created"
    PREFLIGHT = "preflight"
    LEASE_ACQUIRED = "lease_acquired"
    ARGO_WINDOW_OPEN = "argo_window_open"
    ACTION_ACKNOWLEDGED = "action_acknowledged"
    VERIFYING = "verifying"
    ROLLING_BACK = "rolling_back"
    TERMINAL = "terminal"


class SagaOutcome(str, Enum):
    NONE = "none"
    RESOLVED = "resolved"
    ROLLED_BACK = "rolled_back"
    ESCALATED = "escalated"
    MUTATION_UNKNOWN = "mutation_unknown"
    ABANDONED_PRE_MUTATION = "abandoned_pre_mutation"
    ARGO_OVERWRITE = "argo_overwrite"
    STALE = "stale"
    PERSISTENCE_FAILED = "persistence_failed"
    CONFLICTING_DESIRED_STATE = "conflicting_desired_state"


# Phases that imply a live mutation may already have been applied.
POST_MUTATION_PHASES = frozenset(
    {
        SagaPhase.ACTION_ACKNOWLEDGED,
        SagaPhase.VERIFYING,
        SagaPhase.ROLLING_BACK,
    }
)

# Phases still open after a crash and requiring deterministic reconcile.
OPEN_PHASES = frozenset(
    {
        SagaPhase.CREATED,
        SagaPhase.PREFLIGHT,
        SagaPhase.LEASE_ACQUIRED,
        SagaPhase.ARGO_WINDOW_OPEN,
        SagaPhase.ACTION_ACKNOWLEDGED,
        SagaPhase.VERIFYING,
        SagaPhase.ROLLING_BACK,
    }
)


class RemediationSaga(BaseModel):
    """Cross-restart record for one bounded remediation attempt."""

    saga_id: str = Field(default_factory=lambda: f"saga-{uuid4().hex[:12]}")
    incident_id: str
    target: str
    phase: SagaPhase = SagaPhase.CREATED
    outcome: SagaOutcome = SagaOutcome.NONE
    original_template: dict[str, Any] | None = None
    selected_template: dict[str, Any] | None = None
    known_good_revision: str | None = None
    expected_template_after_action: dict[str, Any] | None = None
    verification_samples: list[dict[str, Any]] = Field(default_factory=list)
    rollback_verification_samples: list[dict[str, Any]] = Field(default_factory=list)
    rollback_phase: str | None = None
    mutation_attempted: bool = False
    mutation_blocked: bool = False
    lease_held: bool = False
    argo_window_active: bool = False
    generation: int = 0
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: utcnow().isoformat())
    terminal_reason: str | None = None
    audit: list[dict[str, Any]] = Field(default_factory=list)

    def note(self, event: str, **detail: Any) -> None:
        self.audit.append(
            {
                "at": utcnow().isoformat(),
                "event": event,
                "detail": detail,
            }
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
        self.generation += 1
        self.note("saga_terminal", outcome=outcome.value, reason=reason)

    @property
    def is_open(self) -> bool:
        # Terminal business state is not fully reconciled while external
        # ownership markers or a fail-closed mutation quarantine remain.
        # Quarantined records stay durable until an authenticated operator clears
        # them, so a process restart cannot silently re-enable mutation.
        return (
            self.phase in OPEN_PHASES
            or self.argo_window_active
            or self.lease_held
            or self.mutation_blocked
        )

    @property
    def may_have_mutated(self) -> bool:
        return self.mutation_attempted or self.phase in POST_MUTATION_PHASES


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
    """Raised when durable state cannot be written; callers must fail closed."""


class MemorySagaStore:
    """Process-local store used by unit tests and when durability is disabled."""

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
            return (
                RemediationSaga.model_validate(item.model_dump(mode="json"))
                if item
                else None
            )

    async def get_by_incident(self, incident_id: str) -> RemediationSaga | None:
        async with self._lock:
            for item in self._items.values():
                if item.incident_id == incident_id:
                    return RemediationSaga.model_validate(item.model_dump(mode="json"))
            return None

    async def list_open(self) -> list[RemediationSaga]:
        async with self._lock:
            return [
                RemediationSaga.model_validate(item.model_dump(mode="json"))
                for item in self._items.values()
                if item.is_open
            ]

    async def list_open_for_target(self, target: str) -> list[RemediationSaga]:
        return [s for s in await self.list_open() if s.target == target]

    async def list_all(self) -> list[RemediationSaga]:
        async with self._lock:
            return [
                RemediationSaga.model_validate(item.model_dump(mode="json"))
                for item in self._items.values()
            ]

    async def clear_mutation_block_for_target(self, target: str) -> list[str]:
        async with self._lock:
            blocked = [
                item
                for item in self._items.values()
                if item.target == target and item.mutation_blocked
            ]
            if any(
                item.phase != SagaPhase.TERMINAL
                or item.lease_held
                or item.argo_window_active
                for item in blocked
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
                saga_id
                for saga_id, item in self._items.items()
                if not item.is_open
                and datetime.fromisoformat(item.updated_at) < cutoff
            ]
            for saga_id in removed:
                del self._items[saga_id]
            return removed


class FileSagaStore:
    """JSON-file store; live use requires an operator-provided persistent volume."""

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
        tmp = path.with_suffix(".tmp")
        payload = saga.model_dump(mode="json")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)
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
        return RemediationSaga.model_validate_json(path.read_text(encoding="utf-8"))

    async def get_by_incident(self, incident_id: str) -> RemediationSaga | None:
        for saga in await self.list_all():
            if saga.incident_id == incident_id:
                return saga
        return None

    async def list_open(self) -> list[RemediationSaga]:
        return [s for s in await self.list_all() if s.is_open]

    async def list_open_for_target(self, target: str) -> list[RemediationSaga]:
        return [s for s in await self.list_open() if s.target == target]

    async def list_all(self) -> list[RemediationSaga]:
        async with self._lock:
            items: list[RemediationSaga] = []
            for path in sorted(self.root.glob("*.json")):
                try:
                    items.append(
                        RemediationSaga.model_validate_json(
                            path.read_text(encoding="utf-8")
                        )
                    )
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
                    raise SagaPersistenceError(
                        f"unreadable saga record {path}: {exc}"
                    ) from exc
            return items

    async def clear_mutation_block_for_target(self, target: str) -> list[str]:
        async with self._lock:
            blocked: list[RemediationSaga] = []
            for path in sorted(self.root.glob("*.json")):
                try:
                    saga = RemediationSaga.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                except Exception as exc:
                    raise SagaPersistenceError(
                        f"unreadable saga record {path}: {exc}"
                    ) from exc
                if saga.target == target and saga.mutation_blocked:
                    blocked.append(saga)
            if any(
                saga.phase != SagaPhase.TERMINAL
                or saga.lease_held
                or saga.argo_window_active
                for saga in blocked
            ):
                raise SagaPersistenceError(
                    f"cannot clear {target}: saga cleanup is incomplete"
                )
            for saga in blocked:
                saga.mutation_blocked = False
                saga.note("mutation_block_cleared_by_operator", target=target)
                self._write_unlocked(saga)
            return [saga.saga_id for saga in blocked]

    async def prune_terminal_before(self, cutoff: datetime) -> list[str]:
        """Delete only fully-cleaned terminal records older than the cutoff."""

        async with self._lock:
            removed: list[str] = []
            for path in sorted(self.root.glob("*.json")):
                try:
                    saga = RemediationSaga.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                except Exception as exc:
                    raise SagaPersistenceError(
                        f"unreadable saga record {path}: {exc}"
                    ) from exc
                if saga.is_open or datetime.fromisoformat(saga.updated_at) >= cutoff:
                    continue
                try:
                    path.unlink()
                except OSError as exc:
                    raise SagaPersistenceError(
                        f"failed to prune saga record {path}: {exc}"
                    ) from exc
                removed.append(saga.saga_id)
            return removed


def build_saga_store(
    backend: str = "memory",
    path: str | None = None,
) -> MemorySagaStore | FileSagaStore:
    """Factory used by Settings / main wiring."""

    kind = (backend or "memory").strip().lower()
    if kind in {"", "memory", "mem", "none", "off"}:
        return MemorySagaStore()
    if kind in {"file", "fs", "json"}:
        if not path:
            raise ValueError("AIOPS_SAGA_PATH is required when saga backend is file")
        return FileSagaStore(path)
    if kind == "configmap":
        raise ValueError(
            "configmap saga backend is not implemented; use file with a durable "
            "mounted volume or memory for tests"
        )
    raise ValueError(f"unsupported AIOPS_SAGA_BACKEND: {backend!r}")


def templates_equivalent(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    """Structural equality used for Argo overwrite detection."""

    if left is None or right is None:
        return left is right
    return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


def argo_window_annotations(incident_id: str, until_iso: str) -> dict[str, str]:
    """Annotations applied for the bounded mutation/verification window."""

    return {
        ARGO_WINDOW_ANNOTATION: incident_id,
        ARGO_WINDOW_UNTIL_ANNOTATION: until_iso,
        ARGO_OWNER_ANNOTATION: incident_id,
    }


def decide_restart_action(saga: RemediationSaga) -> str:
    """Pure decision table for startup reconcile (offline-testable).

    Returns one of:
    - abandon_pre_mutation
    - continue_verification
    - restore_original
    - fail_closed_escalate
    - noop_terminal
    """

    if saga.phase == SagaPhase.TERMINAL:
        return "noop_terminal"
    if saga.phase in {
        SagaPhase.CREATED,
        SagaPhase.PREFLIGHT,
        SagaPhase.LEASE_ACQUIRED,
        SagaPhase.ARGO_WINDOW_OPEN,
    } and not saga.mutation_attempted:
        return "abandon_pre_mutation"
    if saga.phase == SagaPhase.VERIFYING or saga.phase == SagaPhase.ACTION_ACKNOWLEDGED:
        if saga.original_template is None:
            return "fail_closed_escalate"
        if saga.selected_template is None and saga.expected_template_after_action is None:
            return "fail_closed_escalate"
        return "continue_verification"
    if saga.phase == SagaPhase.ROLLING_BACK:
        if saga.original_template is None:
            return "fail_closed_escalate"
        return "restore_original"
    if saga.may_have_mutated and saga.original_template is not None:
        return "restore_original"
    return "fail_closed_escalate"
