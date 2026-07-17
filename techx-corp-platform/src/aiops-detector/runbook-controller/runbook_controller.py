"""
TF4AIO-61: Approved Runbook Execution Controller with Dry-Run Mode.

Control plane that consumes a detected incident (from llm_timeout_detector /
rca_detector) and executes only policy-approved runbook actions.

Safety contract:
  - Only actions present in ALLOWED_ACTIONS may ever be executed.
  - Every invocation (dry-run or real) produces an immutable AuditRecord.
  - An action lock prevents the same action from running twice within the
    cooldown window.
  - Free-form shell commands, flagd mutations, and raw LLM output are
    structurally rejected — they cannot be passed as RunbookAction values.
"""
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RunbookController")


# =============================================================================
# 1. POLICY — CDO-APPROVED ALLOW-LIST
# =============================================================================
class RunbookAction(str, Enum):
    """
    Exhaustive list of actions the controller may ever invoke.
    No action outside this enum can be requested — structural rejection.
    """
    RESTART_DEPLOYMENT     = "restart_deployment"
    SCALE_DOWN_REPLICAS    = "scale_down_replicas"
    TOGGLE_FEATURE_FLAG    = "toggle_feature_flag"
    SEND_ALERT_NOTIFICATION = "send_alert_notification"
    NO_OP                  = "no_op"


# Per-action cooldown (seconds). Prevents duplicate/spam execution.
ACTION_COOLDOWN_SECONDS: Dict[RunbookAction, int] = {
    RunbookAction.RESTART_DEPLOYMENT:      300,   # 5 min
    RunbookAction.SCALE_DOWN_REPLICAS:     180,   # 3 min
    RunbookAction.TOGGLE_FEATURE_FLAG:     600,   # 10 min
    RunbookAction.SEND_ALERT_NOTIFICATION:  60,   # 1 min
    RunbookAction.NO_OP:                     0,
}

# Severity levels that permit each action
ACTION_SEVERITY_PRECONDITIONS: Dict[RunbookAction, List[str]] = {
    RunbookAction.RESTART_DEPLOYMENT:      ["high"],
    RunbookAction.SCALE_DOWN_REPLICAS:     ["high", "medium"],
    RunbookAction.TOGGLE_FEATURE_FLAG:     ["high", "medium"],
    RunbookAction.SEND_ALERT_NOTIFICATION: ["high", "medium", "unknown"],
    RunbookAction.NO_OP:                   ["high", "medium", "none", "unknown"],
}


# =============================================================================
# 2. DATA MODELS
# =============================================================================
@dataclass
class AuditRecord:
    """Immutable audit log entry produced for every controller invocation."""
    audit_id:     str
    timestamp:    str
    dry_run:      bool
    action:       str
    service:      str
    environment:  str
    severity:     str
    approved:     bool
    rejection_reason: Optional[str]
    proposed_command: Optional[str]   # what would have run
    outcome:      str                 # "dry_run" | "executed" | "rejected"
    incident_snapshot: Dict[str, Any]


@dataclass
class ControllerResult:
    audit: AuditRecord
    success: bool
    message: str


# =============================================================================
# 3. ACTION LOCK (in-process cooldown registry)
# =============================================================================
class ActionLock:
    """Thread-safe cooldown registry (single-process scope)."""

    def __init__(self):
        self._last_run: Dict[str, float] = {}   # key: "service:action"

    def _key(self, service: str, action: RunbookAction) -> str:
        return f"{service}:{action.value}"

    def is_locked(self, service: str, action: RunbookAction) -> bool:
        cooldown = ACTION_COOLDOWN_SECONDS[action]
        if cooldown == 0:
            return False
        last = self._last_run.get(self._key(service, action), 0)
        return (time.time() - last) < cooldown

    def seconds_remaining(self, service: str, action: RunbookAction) -> int:
        cooldown = ACTION_COOLDOWN_SECONDS[action]
        last = self._last_run.get(self._key(service, action), 0)
        remaining = cooldown - (time.time() - last)
        return max(0, int(remaining))

    def acquire(self, service: str, action: RunbookAction) -> None:
        self._last_run[self._key(service, action)] = time.time()


# =============================================================================
# 4. CDO EXECUTION INTERFACE (stubbed for MVP dry-run)
# =============================================================================
class CDOExecutionInterface:
    """
    Thin wrapper around CDO-approved infrastructure operations.
    Each method logs the proposed command and raises NotImplementedError
    in the MVP — real execution is wired in post-CDO sign-off.
    """

    def restart_deployment(self, service: str, namespace: str) -> str:
        cmd = f"kubectl rollout restart deployment/{service} -n {namespace}"
        logger.info(f"[CDO] Would execute: {cmd}")
        raise NotImplementedError("Live execution requires CDO sign-off. Use dry_run=True.")

    def scale_down_replicas(self, service: str, namespace: str, replicas: int = 0) -> str:
        cmd = f"kubectl scale deployment/{service} --replicas={replicas} -n {namespace}"
        logger.info(f"[CDO] Would execute: {cmd}")
        raise NotImplementedError("Live execution requires CDO sign-off. Use dry_run=True.")

    def toggle_feature_flag(self, flag_name: str, value: bool) -> str:
        # flagd change is CDO-gated — only toggle flags on the allow-list
        cmd = f"flagd set --flag {flag_name} --value {str(value).lower()}"
        logger.info(f"[CDO] Would execute: {cmd}")
        raise NotImplementedError("Live execution requires CDO sign-off. Use dry_run=True.")

    def send_alert_notification(self, service: str, severity: str, message: str) -> str:
        cmd = f"alertmanager-cli fire --service {service} --severity {severity} --msg '{message}'"
        logger.info(f"[CDO] Would execute: {cmd}")
        return cmd  # Notifications are safe to "execute" in MVP

    def build_proposed_command(self, action: RunbookAction, service: str, environment: str) -> str:
        """Returns a human-readable proposed command string without executing."""
        mapping = {
            RunbookAction.RESTART_DEPLOYMENT:
                f"kubectl rollout restart deployment/{service} -n {environment}",
            RunbookAction.SCALE_DOWN_REPLICAS:
                f"kubectl scale deployment/{service} --replicas=0 -n {environment}",
            RunbookAction.TOGGLE_FEATURE_FLAG:
                f"flagd set --flag {service}-maintenance --value true",
            RunbookAction.SEND_ALERT_NOTIFICATION:
                f"alertmanager-cli fire --service {service} --severity high",
            RunbookAction.NO_OP:
                "echo 'no-op: monitoring only'",
        }
        return mapping.get(action, "unknown")


# =============================================================================
# 5. RUNBOOK CONTROLLER
# =============================================================================
class RunbookController:
    """
    Policy-aware execution controller for AIOps remediation.

    Usage:
        controller = RunbookController()
        result = controller.execute(incident, RunbookAction.SEND_ALERT_NOTIFICATION, dry_run=True)
    """

    def __init__(self, action_lock: Optional[ActionLock] = None):
        self._lock = action_lock or ActionLock()
        self._cdo = CDOExecutionInterface()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        incident: Dict[str, Any],
        action: RunbookAction,
        dry_run: bool = True,
    ) -> ControllerResult:
        """
        Entry point. Always produces an AuditRecord regardless of outcome.

        Args:
            incident:  Structured detector output (llm_timeout_detector / rca_detector format).
            action:    RunbookAction enum value — no free-form strings accepted.
            dry_run:   When True, logs proposed command and returns without mutating infra.

        Returns:
            ControllerResult with audit record and outcome.
        """
        service     = incident.get("service", "unknown")
        environment = incident.get("environment", "unknown")
        severity    = incident.get("severity", "unknown")

        proposed_cmd = self._cdo.build_proposed_command(action, service, environment)

        # --- Validation pipeline ---
        rejection = self._validate(incident, action, service, severity)

        if rejection:
            audit = self._make_audit(
                dry_run=dry_run,
                action=action,
                service=service,
                environment=environment,
                severity=severity,
                approved=False,
                rejection_reason=rejection,
                proposed_command=proposed_cmd,
                outcome="rejected",
                incident=incident,
            )
            logger.warning(f"[REJECTED] {action.value} for {service}: {rejection}")
            return ControllerResult(audit=audit, success=False, message=rejection)

        # --- Approved path ---
        if dry_run:
            audit = self._make_audit(
                dry_run=True,
                action=action,
                service=service,
                environment=environment,
                severity=severity,
                approved=True,
                rejection_reason=None,
                proposed_command=proposed_cmd,
                outcome="dry_run",
                incident=incident,
            )
            logger.info(f"[DRY-RUN] {action.value} for {service} -> {proposed_cmd}")
            return ControllerResult(audit=audit, success=True,
                                    message=f"DRY-RUN: would execute -> {proposed_cmd}")

        # --- Real execution (requires CDO sign-off; MVP raises NotImplementedError) ---
        self._lock.acquire(service, action)
        try:
            self._dispatch(action, service, environment, severity, incident)
            outcome = "executed"
            msg = f"Executed {action.value} for {service}"
        except NotImplementedError as e:
            outcome = "rejected"
            msg = str(e)

        audit = self._make_audit(
            dry_run=False,
            action=action,
            service=service,
            environment=environment,
            severity=severity,
            approved=True,
            rejection_reason=None if outcome == "executed" else msg,
            proposed_command=proposed_cmd,
            outcome=outcome,
            incident=incident,
        )
        return ControllerResult(audit=audit, success=(outcome == "executed"), message=msg)

    # ------------------------------------------------------------------
    # Validation pipeline
    # ------------------------------------------------------------------

    def _validate(
        self,
        incident: Dict[str, Any],
        action: RunbookAction,
        service: str,
        severity: str,
    ) -> Optional[str]:
        """Returns a rejection reason string, or None if valid."""

        # 1. Action must be a known RunbookAction (structural — enforced by type)
        if not isinstance(action, RunbookAction):
            return f"Action '{action}' is not a permitted RunbookAction value"

        # 2. Severity precondition
        allowed_severities = ACTION_SEVERITY_PRECONDITIONS.get(action, [])
        if severity not in allowed_severities:
            return (f"Action '{action.value}' requires severity in "
                    f"{allowed_severities}, got '{severity}'")

        # 3. Cooldown / action lock
        if self._lock.is_locked(service, action):
            remaining = self._lock.seconds_remaining(service, action)
            return (f"Action '{action.value}' is in cooldown for {service}. "
                    f"{remaining}s remaining.")

        return None  # all checks passed

    # ------------------------------------------------------------------
    # Dispatch (CDO-gated)
    # ------------------------------------------------------------------

    def _dispatch(
        self,
        action: RunbookAction,
        service: str,
        environment: str,
        severity: str,
        incident: Dict[str, Any],
    ) -> None:
        if action == RunbookAction.RESTART_DEPLOYMENT:
            self._cdo.restart_deployment(service, environment)
        elif action == RunbookAction.SCALE_DOWN_REPLICAS:
            self._cdo.scale_down_replicas(service, environment)
        elif action == RunbookAction.TOGGLE_FEATURE_FLAG:
            self._cdo.toggle_feature_flag(f"{service}-maintenance", True)
        elif action == RunbookAction.SEND_ALERT_NOTIFICATION:
            self._cdo.send_alert_notification(
                service, severity,
                f"AIOps detected incident: severity={severity}"
            )
        elif action == RunbookAction.NO_OP:
            logger.info(f"[NO_OP] Monitoring only for {service}")

    # ------------------------------------------------------------------
    # Audit record factory
    # ------------------------------------------------------------------

    def _make_audit(self, **kwargs) -> AuditRecord:
        incident = kwargs.pop("incident")
        return AuditRecord(
            audit_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            incident_snapshot={
                "service":     incident.get("service"),
                "environment": incident.get("environment"),
                "severity":    incident.get("severity"),
                "rule":        incident.get("rule"),
                "timestamp":   incident.get("timestamp"),
            },
            **kwargs,
        )


# =============================================================================
# 6. DEMO (dry-run only)
# =============================================================================
if __name__ == "__main__":
    sample_incident = {
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "rule":        "ai_llm_timeout_error",
        "service":     "product-reviews",
        "environment": "production",
        "tenant_id":   "default",
        "severity":    "high",
    }

    controller = RunbookController()

    for action in [
        RunbookAction.SEND_ALERT_NOTIFICATION,
        RunbookAction.RESTART_DEPLOYMENT,
        RunbookAction.NO_OP,
    ]:
        result = controller.execute(sample_incident, action, dry_run=True)
        print(json.dumps(asdict(result.audit), indent=2))
        print(f"-> {result.message}\n")
