"""
Unit tests for TF4AIO-61: RunbookController.

Run: python -m pytest tests/test_runbook_controller.py -v
"""
import os
import sys
import importlib.util
import unittest
from datetime import datetime, timezone

base_dir = os.path.dirname(os.path.dirname(__file__))

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

rc = load_module(
    "runbook_controller",
    os.path.join(base_dir, "runbook-controller", "runbook_controller.py"),
)

RunbookController = rc.RunbookController
RunbookAction     = rc.RunbookAction
ActionLock        = rc.ActionLock


def _make_incident(severity="high"):
    return {
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "rule":        "ai_llm_timeout_error",
        "service":     "product-reviews",
        "environment": "production",
        "tenant_id":   "default",
        "severity":    severity,
    }


class TestDryRunProducesAuditRecord(unittest.TestCase):

    def test_dry_run_returns_success(self):
        ctrl = RunbookController()
        result = ctrl.execute(_make_incident("high"),
                              RunbookAction.SEND_ALERT_NOTIFICATION, dry_run=True)
        self.assertTrue(result.success)
        self.assertEqual(result.audit.outcome, "dry_run")
        self.assertTrue(result.audit.dry_run)

    def test_dry_run_audit_contains_proposed_command(self):
        ctrl = RunbookController()
        result = ctrl.execute(_make_incident("high"),
                              RunbookAction.RESTART_DEPLOYMENT, dry_run=True)
        self.assertIsNotNone(result.audit.proposed_command)
        self.assertIn("kubectl", result.audit.proposed_command)

    def test_audit_record_captures_incident_snapshot(self):
        ctrl = RunbookController()
        result = ctrl.execute(_make_incident("high"),
                              RunbookAction.NO_OP, dry_run=True)
        snap = result.audit.incident_snapshot
        self.assertEqual(snap["service"], "product-reviews")
        self.assertEqual(snap["severity"], "high")

    def test_audit_id_is_unique(self):
        ctrl = RunbookController()
        r1 = ctrl.execute(_make_incident(), RunbookAction.NO_OP, dry_run=True)
        r2 = ctrl.execute(_make_incident(), RunbookAction.NO_OP, dry_run=True)
        self.assertNotEqual(r1.audit.audit_id, r2.audit.audit_id)


class TestRejectionRules(unittest.TestCase):

    def test_reject_when_severity_too_low(self):
        """RESTART_DEPLOYMENT requires 'high' — should reject on 'none'."""
        ctrl = RunbookController()
        result = ctrl.execute(_make_incident("none"),
                              RunbookAction.RESTART_DEPLOYMENT, dry_run=True)
        self.assertFalse(result.success)
        self.assertEqual(result.audit.outcome, "rejected")
        self.assertIsNotNone(result.audit.rejection_reason)

    def test_reject_when_cooldown_active(self):
        """Second identical action within cooldown window must be rejected."""
        lock = ActionLock()
        lock.acquire("product-reviews", RunbookAction.RESTART_DEPLOYMENT)
        ctrl = RunbookController(action_lock=lock)
        result = ctrl.execute(_make_incident("high"),
                              RunbookAction.RESTART_DEPLOYMENT, dry_run=True)
        self.assertFalse(result.success)
        self.assertIn("cooldown", result.audit.rejection_reason.lower())

    def test_no_op_always_allowed(self):
        """NO_OP must pass for any severity including 'unknown'."""
        ctrl = RunbookController()
        for sev in ["high", "medium", "none", "unknown"]:
            result = ctrl.execute(_make_incident(sev), RunbookAction.NO_OP, dry_run=True)
            self.assertTrue(result.success, f"NO_OP failed for severity={sev}")


class TestSeparationOfConcerns(unittest.TestCase):

    def test_execution_is_separate_from_detector_code(self):
        """Controller must not import or call detector modules directly."""
        src_path = os.path.join(base_dir, "runbook-controller", "runbook_controller.py")
        module_source = open(src_path).read()
        self.assertNotIn("LLMTimeoutDetector", module_source)
        self.assertNotIn("RCARuleEngine", module_source)

    def test_approved_flag_in_audit(self):
        ctrl = RunbookController()
        result = ctrl.execute(_make_incident("high"),
                              RunbookAction.SEND_ALERT_NOTIFICATION, dry_run=True)
        self.assertTrue(result.audit.approved)

    def test_rejected_audit_has_no_approved_flag(self):
        ctrl = RunbookController()
        result = ctrl.execute(_make_incident("none"),
                              RunbookAction.RESTART_DEPLOYMENT, dry_run=True)
        self.assertFalse(result.audit.approved)


if __name__ == "__main__":
    unittest.main()
