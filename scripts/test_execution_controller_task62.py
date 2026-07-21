"""Unit tests for Task 62 execution controller workflow.

Run:
  python scripts/test_execution_controller_task62.py
"""

from __future__ import annotations

import unittest

from execution_controller import (
    ActionExecutionResult,
    EscalationRecord,
    ExecutionController,
    IncidentExecutionContext,
    RemediationAction,
    RollbackResult,
    VerificationResult,
    WorkflowState,
)


class FakeEvidenceCollector:
    def capture_before(self, *, incident_id: str, action_name: str) -> dict[str, object]:
        return {
            "metrics": {"p95_ms": 1800, "error_rate": 0.14},
            "logs": ["timeout spikes before action"],
            "traces": ["trace-before-001"],
            "readiness": {"ready_replicas": 1, "desired_replicas": 2},
            "synthetic_sli": {"checkout_success": 0.88},
            "incident_id": incident_id,
            "action_name": action_name,
        }

    def capture_after(self, *, incident_id: str, action_name: str) -> dict[str, object]:
        return {
            "metrics": {"p95_ms": 640, "error_rate": 0.01},
            "logs": ["post-action observation"],
            "traces": ["trace-after-001"],
            "readiness": {"ready_replicas": 2, "desired_replicas": 2},
            "synthetic_sli": {"checkout_success": 0.995},
            "incident_id": incident_id,
            "action_name": action_name,
        }


class FakeVerifier:
    def __init__(self, result: VerificationResult) -> None:
        self._result = result

    def verify_recovery(
        self,
        *,
        incident_id: str,
        action_name: str,
        stabilization_window_seconds: int,
        before: dict[str, object],
        after: dict[str, object],
    ) -> VerificationResult:
        assert incident_id
        assert action_name
        assert stabilization_window_seconds > 0
        assert "metrics" in before and "metrics" in after
        return self._result


class FakeActionExecutor:
    def __init__(self, result: ActionExecutionResult) -> None:
        self._result = result
        self.calls = 0

    def execute(self, *, incident_id: str, action: RemediationAction) -> ActionExecutionResult:
        assert incident_id
        assert action.name
        self.calls += 1
        return self._result


class FakeRollbackExecutor:
    def __init__(self, *, safe_known_good: bool, rollback_result: RollbackResult) -> None:
        self.safe_known_good = safe_known_good
        self.rollback_result = rollback_result
        self.rollback_calls = 0

    def has_safe_known_good(self, *, action: RemediationAction) -> bool:
        assert action.name
        return self.safe_known_good

    def rollback(self, *, incident_id: str, action: RemediationAction) -> RollbackResult:
        assert incident_id
        assert action.name
        self.rollback_calls += 1
        return self.rollback_result


class FakeEscalationNotifier:
    def __init__(self) -> None:
        self.calls = 0

    def notify(
        self,
        *,
        owner: str,
        reason: str,
        evidence_package: dict[str, object],
    ) -> EscalationRecord:
        self.calls += 1
        return EscalationRecord(owner=owner, reason=reason, evidence_package=evidence_package)


class Task62ExecutionControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = IncidentExecutionContext(
            incident_id="inc-2026-07-21-001",
            cdo_owner="cdo08-oncall-owner",
        )
        self.action = RemediationAction(
            name="restart-checkout-deployment",
            action_type="restart",
            stabilization_window_seconds=300,
            rollback_to="checkout-revision-142",
        )
        self.evidence = FakeEvidenceCollector()

    def test_recovered_when_verification_holds_for_window(self) -> None:
        controller = ExecutionController(max_restart_attempts=1)
        verifier = FakeVerifier(
            VerificationResult(
                passed=True,
                details="SLIs stayed healthy for full 300s",
                observed_entire_window=True,
            )
        )
        action_executor = FakeActionExecutor(ActionExecutionResult(success=True, details="restart executed"))
        rollback_executor = FakeRollbackExecutor(
            safe_known_good=True,
            rollback_result=RollbackResult(success=True, details="rollback not needed"),
        )
        escalation = FakeEscalationNotifier()

        record = controller.run(
            context=self.context,
            action=self.action,
            evidence_collector=self.evidence,
            verifier=verifier,
            action_executor=action_executor,
            rollback_executor=rollback_executor,
            escalation_notifier=escalation,
        )

        self.assertEqual(record.state, WorkflowState.RECOVERED)
        self.assertTrue(record.action_executed)
        self.assertIsNotNone(record.verification_result)
        self.assertEqual(escalation.calls, 0)

    def test_failed_verification_triggers_rollback_when_safe(self) -> None:
        controller = ExecutionController(max_restart_attempts=1)
        verifier = FakeVerifier(
            VerificationResult(
                passed=False,
                details="error rate regressed within stabilization window",
                observed_entire_window=True,
            )
        )
        action_executor = FakeActionExecutor(ActionExecutionResult(success=True, details="restart executed"))
        rollback_executor = FakeRollbackExecutor(
            safe_known_good=True,
            rollback_result=RollbackResult(success=True, details="rolled back to checkout-revision-142"),
        )
        escalation = FakeEscalationNotifier()

        record = controller.run(
            context=self.context,
            action=self.action,
            evidence_collector=self.evidence,
            verifier=verifier,
            action_executor=action_executor,
            rollback_executor=rollback_executor,
            escalation_notifier=escalation,
        )

        self.assertEqual(record.state, WorkflowState.ROLLBACK_COMPLETED)
        self.assertTrue(record.action_executed)
        self.assertFalse(record.verification_result.passed)  # type: ignore[union-attr]
        self.assertEqual(rollback_executor.rollback_calls, 1)
        self.assertEqual(escalation.calls, 0)

    def test_escalates_when_rollback_is_unavailable(self) -> None:
        controller = ExecutionController(max_restart_attempts=1)
        verifier = FakeVerifier(
            VerificationResult(
                passed=False,
                details="readiness never stabilized",
                observed_entire_window=True,
            )
        )
        action_executor = FakeActionExecutor(ActionExecutionResult(success=True, details="restart executed"))
        rollback_executor = FakeRollbackExecutor(
            safe_known_good=False,
            rollback_result=RollbackResult(success=False, details="n/a"),
        )
        escalation = FakeEscalationNotifier()

        record = controller.run(
            context=self.context,
            action=self.action,
            evidence_collector=self.evidence,
            verifier=verifier,
            action_executor=action_executor,
            rollback_executor=rollback_executor,
            escalation_notifier=escalation,
        )

        self.assertEqual(record.state, WorkflowState.ESCALATED)
        self.assertTrue(self.context.mutation_blocked)
        self.assertTrue(record.action_executed)
        self.assertIsNotNone(record.verification_result)
        self.assertEqual(escalation.calls, 1)

    def test_escalates_when_rollback_attempt_fails(self) -> None:
        controller = ExecutionController(max_restart_attempts=1)
        verifier = FakeVerifier(
            VerificationResult(
                passed=False,
                details="customer-facing SLI dropped below threshold",
                observed_entire_window=True,
            )
        )
        action_executor = FakeActionExecutor(ActionExecutionResult(success=True, details="restart executed"))
        rollback_executor = FakeRollbackExecutor(
            safe_known_good=True,
            rollback_result=RollbackResult(success=False, details="helm rollback failed"),
        )
        escalation = FakeEscalationNotifier()

        record = controller.run(
            context=self.context,
            action=self.action,
            evidence_collector=self.evidence,
            verifier=verifier,
            action_executor=action_executor,
            rollback_executor=rollback_executor,
            escalation_notifier=escalation,
        )

        self.assertEqual(record.state, WorkflowState.ESCALATED)
        self.assertTrue(self.context.mutation_blocked)
        self.assertEqual(rollback_executor.rollback_calls, 1)
        self.assertEqual(escalation.calls, 1)

    def test_restart_loop_is_prevented(self) -> None:
        controller = ExecutionController(max_restart_attempts=1)
        verifier = FakeVerifier(
            VerificationResult(
                passed=True,
                details="healthy",
                observed_entire_window=True,
            )
        )
        action_executor = FakeActionExecutor(ActionExecutionResult(success=True, details="restart executed"))
        rollback_executor = FakeRollbackExecutor(
            safe_known_good=True,
            rollback_result=RollbackResult(success=True, details="rollback ok"),
        )
        escalation = FakeEscalationNotifier()

        first = controller.run(
            context=self.context,
            action=self.action,
            evidence_collector=self.evidence,
            verifier=verifier,
            action_executor=action_executor,
            rollback_executor=rollback_executor,
            escalation_notifier=escalation,
        )
        self.assertEqual(first.state, WorkflowState.RECOVERED)

        second = controller.run(
            context=self.context,
            action=self.action,
            evidence_collector=self.evidence,
            verifier=verifier,
            action_executor=action_executor,
            rollback_executor=rollback_executor,
            escalation_notifier=escalation,
        )
        self.assertEqual(second.state, WorkflowState.ESCALATED)
        self.assertFalse(second.action_executed)
        self.assertIn("Restart loop prevented", second.execution_details)


if __name__ == "__main__":
    unittest.main(verbosity=2)
