"""Task 62 execution controller with verification, rollback, and escalation guards.

This module models a safe remediation workflow:
- action execution is separate from recovery verification,
- recovery requires a stabilization window,
- failed verification triggers rollback when safe,
- unsafe/unavailable/failed rollback escalates and blocks further mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class WorkflowState(str, Enum):
    ACTION_SKIPPED = "action-skipped"
    ACTION_EXECUTED = "action-executed"
    RECOVERED = "recovered"
    ROLLBACK_COMPLETED = "rollback-completed"
    ESCALATED = "escalated"


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    details: str
    observed_entire_window: bool


@dataclass(frozen=True)
class ActionExecutionResult:
    success: bool
    details: str


@dataclass(frozen=True)
class RollbackResult:
    success: bool
    details: str


@dataclass(frozen=True)
class EscalationRecord:
    owner: str
    reason: str
    evidence_package: dict[str, Any]


@dataclass(frozen=True)
class RemediationAction:
    name: str
    action_type: str
    stabilization_window_seconds: int
    rollback_to: str | None = None


@dataclass
class IncidentExecutionContext:
    incident_id: str
    cdo_owner: str
    mutation_blocked: bool = False
    restart_attempts: int = 0
    action_history: list["ActionRecord"] = field(default_factory=list)


@dataclass
class ActionRecord:
    action: RemediationAction
    action_executed: bool
    state: WorkflowState
    execution_details: str
    verification_result: VerificationResult | None
    rollback_result: RollbackResult | None
    escalation: EscalationRecord | None
    evidence_package: dict[str, Any]


class EvidenceCollector(Protocol):
    def capture_before(self, *, incident_id: str, action_name: str) -> dict[str, Any]:
        """Capture metrics/logs/traces/readiness/synthetic evidence before mutation."""

    def capture_after(self, *, incident_id: str, action_name: str) -> dict[str, Any]:
        """Capture metrics/logs/traces/readiness/synthetic evidence after mutation."""


class Verifier(Protocol):
    def verify_recovery(
        self,
        *,
        incident_id: str,
        action_name: str,
        stabilization_window_seconds: int,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> VerificationResult:
        """Return whether recovery criteria held for the entire stabilization window."""


class ActionExecutor(Protocol):
    def execute(self, *, incident_id: str, action: RemediationAction) -> ActionExecutionResult:
        """Execute one approved remediation action."""


class RollbackExecutor(Protocol):
    def has_safe_known_good(self, *, action: RemediationAction) -> bool:
        """Return whether a safe rollback target exists for this action."""

    def rollback(self, *, incident_id: str, action: RemediationAction) -> RollbackResult:
        """Rollback to the pre-defined known-good target for this action."""


class EscalationNotifier(Protocol):
    def notify(
        self,
        *,
        owner: str,
        reason: str,
        evidence_package: dict[str, Any],
    ) -> EscalationRecord:
        """Escalate to the named CDO owner with the evidence package."""


class ExecutionController:
    """Orchestrates action -> verification -> rollback/escalation safely."""

    def __init__(self, *, max_restart_attempts: int = 1) -> None:
        if max_restart_attempts < 1:
            raise ValueError("max_restart_attempts must be >= 1")
        self._max_restart_attempts = max_restart_attempts

    def run(
        self,
        *,
        context: IncidentExecutionContext,
        action: RemediationAction,
        evidence_collector: EvidenceCollector,
        verifier: Verifier,
        action_executor: ActionExecutor,
        rollback_executor: RollbackExecutor,
        escalation_notifier: EscalationNotifier,
    ) -> ActionRecord:
        if context.mutation_blocked:
            record = ActionRecord(
                action=action,
                action_executed=False,
                state=WorkflowState.ACTION_SKIPPED,
                execution_details="Mutation is blocked after prior escalation/failure",
                verification_result=None,
                rollback_result=None,
                escalation=None,
                evidence_package={},
            )
            context.action_history.append(record)
            return record

        if action.action_type == "restart" and context.restart_attempts >= self._max_restart_attempts:
            reason = (
                "Restart loop prevented: max restart attempts reached; "
                "no further restart mutation is allowed"
            )
            escalation = escalation_notifier.notify(
                owner=context.cdo_owner,
                reason=reason,
                evidence_package={"incident_id": context.incident_id, "action": action.name},
            )
            context.mutation_blocked = True
            record = ActionRecord(
                action=action,
                action_executed=False,
                state=WorkflowState.ESCALATED,
                execution_details=reason,
                verification_result=None,
                rollback_result=None,
                escalation=escalation,
                evidence_package=escalation.evidence_package,
            )
            context.action_history.append(record)
            return record

        before = evidence_collector.capture_before(
            incident_id=context.incident_id,
            action_name=action.name,
        )

        execution = action_executor.execute(incident_id=context.incident_id, action=action)
        if not execution.success:
            after = evidence_collector.capture_after(
                incident_id=context.incident_id,
                action_name=action.name,
            )
            package = self._build_evidence_package(
                context=context,
                action=action,
                before=before,
                after=after,
                verification=None,
            )
            escalation = escalation_notifier.notify(
                owner=context.cdo_owner,
                reason=f"Action execution failed: {execution.details}",
                evidence_package=package,
            )
            context.mutation_blocked = True
            record = ActionRecord(
                action=action,
                action_executed=True,
                state=WorkflowState.ESCALATED,
                execution_details=execution.details,
                verification_result=None,
                rollback_result=None,
                escalation=escalation,
                evidence_package=package,
            )
            context.action_history.append(record)
            return record

        if action.action_type == "restart":
            context.restart_attempts += 1

        after = evidence_collector.capture_after(
            incident_id=context.incident_id,
            action_name=action.name,
        )
        verification = verifier.verify_recovery(
            incident_id=context.incident_id,
            action_name=action.name,
            stabilization_window_seconds=action.stabilization_window_seconds,
            before=before,
            after=after,
        )
        package = self._build_evidence_package(
            context=context,
            action=action,
            before=before,
            after=after,
            verification=verification,
        )

        if verification.passed and verification.observed_entire_window:
            record = ActionRecord(
                action=action,
                action_executed=True,
                state=WorkflowState.RECOVERED,
                execution_details=execution.details,
                verification_result=verification,
                rollback_result=None,
                escalation=None,
                evidence_package=package,
            )
            context.action_history.append(record)
            return record

        if rollback_executor.has_safe_known_good(action=action):
            rollback = rollback_executor.rollback(incident_id=context.incident_id, action=action)
            if rollback.success:
                record = ActionRecord(
                    action=action,
                    action_executed=True,
                    state=WorkflowState.ROLLBACK_COMPLETED,
                    execution_details=execution.details,
                    verification_result=verification,
                    rollback_result=rollback,
                    escalation=None,
                    evidence_package=package,
                )
                context.action_history.append(record)
                return record

            escalation = escalation_notifier.notify(
                owner=context.cdo_owner,
                reason=f"Rollback failed after failed verification: {rollback.details}",
                evidence_package=package,
            )
            context.mutation_blocked = True
            record = ActionRecord(
                action=action,
                action_executed=True,
                state=WorkflowState.ESCALATED,
                execution_details=execution.details,
                verification_result=verification,
                rollback_result=rollback,
                escalation=escalation,
                evidence_package=package,
            )
            context.action_history.append(record)
            return record

        escalation = escalation_notifier.notify(
            owner=context.cdo_owner,
            reason="Verification failed and safe rollback is unavailable/unsafe",
            evidence_package=package,
        )
        context.mutation_blocked = True
        record = ActionRecord(
            action=action,
            action_executed=True,
            state=WorkflowState.ESCALATED,
            execution_details=execution.details,
            verification_result=verification,
            rollback_result=None,
            escalation=escalation,
            evidence_package=package,
        )
        context.action_history.append(record)
        return record

    @staticmethod
    def _build_evidence_package(
        *,
        context: IncidentExecutionContext,
        action: RemediationAction,
        before: dict[str, Any],
        after: dict[str, Any],
        verification: VerificationResult | None,
    ) -> dict[str, Any]:
        return {
            "incident_id": context.incident_id,
            "action": {
                "name": action.name,
                "type": action.action_type,
                "stabilization_window_seconds": action.stabilization_window_seconds,
                "rollback_to": action.rollback_to,
            },
            "before": before,
            "after": after,
            "verification": None
            if verification is None
            else {
                "passed": verification.passed,
                "details": verification.details,
                "observed_entire_window": verification.observed_entire_window,
            },
        }
