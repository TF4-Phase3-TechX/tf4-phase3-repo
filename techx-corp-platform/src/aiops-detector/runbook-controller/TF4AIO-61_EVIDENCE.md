# TF4AIO-61 Validation Evidence

**Task**: [W3][AIOPS] Build approved runbook execution controller with dry-run mode
**Assignee**: huynh xuan hau

## Validation Context
This document proves that the approved runbook execution controller can successfully consume detected incidents and safely determine whether a proposed remediation action should be executed under CDO policy guidelines.

## Test Implementation
A comprehensive unit test suite (`tests/test_runbook_controller.py`) with 10 test cases is established under pytest to cover:
1. Dry-run producing an auditable proposed-action record with a unique UUID.
2. Unapproved/disallowed actions (due to low severity) being rejected with a detailed reason.
3. Duplicate actions within the action lock cooldown window being rejected with time remaining.
4. Complete isolation of approved action execution from LLM/detector code (no references).

## Validation Output (Demo Script Execution)
When running the controller demo script (`runbook_controller.py`), the controller processes a high-severity incident across multiple CDO-approved runbook actions in `dry_run` mode:

**Command:**
```bash
python techx-corp-platform/src/aiops-detector/runbook-controller/runbook_controller.py
```

**Output:**
```
INFO:RunbookController:[DRY-RUN] send_alert_notification for product-reviews -> alertmanager-cli fire --service product-reviews --severity high
INFO:RunbookController:[DRY-RUN] restart_deployment for product-reviews -> kubectl rollout restart deployment/product-reviews -n production
INFO:RunbookController:[DRY-RUN] no_op for product-reviews -> echo 'no-op: monitoring only'
{
  "audit_id": "03c296d6-f53d-4c65-b053-ecc90cfff4cb",
  "timestamp": "2026-07-17T08:21:45.493601+00:00",
  "dry_run": true,
  "action": "send_alert_notification",
  "service": "product-reviews",
  "environment": "production",
  "severity": "high",
  "approved": true,
  "rejection_reason": null,
  "proposed_command": "alertmanager-cli fire --service product-reviews --severity high",
  "outcome": "dry_run",
  "incident_snapshot": {
    "service": "product-reviews",
    "environment": "production",
    "severity": "high",
    "rule": "ai_llm_timeout_error",
    "timestamp": "2026-07-17T08:21:45.493601+00:00"
  }
}
-> DRY-RUN: would execute -> alertmanager-cli fire --service product-reviews --severity high

{
  "audit_id": "defd520a-7d4a-491e-ad6e-a77d84d47ad7",
  "timestamp": "2026-07-17T08:21:45.494608+00:00",
  "dry_run": true,
  "action": "restart_deployment",
  "service": "product-reviews",
  "environment": "production",
  "severity": "high",
  "approved": true,
  "rejection_reason": null,
  "proposed_command": "kubectl rollout restart deployment/product-reviews -n production",
  "outcome": "dry_run",
  "incident_snapshot": {
    "service": "product-reviews",
    "environment": "production",
    "severity": "high",
    "rule": "ai_llm_timeout_error",
    "timestamp": "2026-07-17T08:21:45.493601+00:00"
  }
}
-> DRY-RUN: would execute -> kubectl rollout restart deployment/product-reviews -n production

{
  "audit_id": "2eac4515-6914-4c4f-8c59-9efe0edcc94d",
  "timestamp": "2026-07-17T08:21:45.494608+00:00",
  "dry_run": true,
  "action": "no_op",
  "service": "product-reviews",
  "environment": "production",
  "severity": "high",
  "approved": true,
  "rejection_reason": null,
  "proposed_command": "echo 'no-op: monitoring only'",
  "outcome": "dry_run",
  "incident_snapshot": {
    "service": "product-reviews",
    "environment": "production",
    "severity": "high",
    "rule": "ai_llm_timeout_error",
    "timestamp": "2026-07-17T08:21:45.493601+00:00"
  }
}
-> DRY-RUN: would execute -> echo 'no-op: monitoring only'
```

## Pytest Execution Results
Running `pytest` executes the full policy and isolation validation:

**Command:**
```bash
python -m pytest techx-corp-platform/src/aiops-detector/tests/test_runbook_controller.py -v
```

**Output:**
```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.1.1, pluggy-1.6.0
rootdir: D:\AWS\Xbrain\Phase3
plugins: anyio-4.9.0
collected 10 items

techx-corp-platform\src\aiops-detector\tests\test_runbook_controller.py ::TestDryRunProducesAuditRecord::test_audit_id_is_unique PASSED
techx-corp-platform\src\aiops-detector\tests\test_runbook_controller.py ::TestDryRunProducesAuditRecord::test_audit_record_captures_incident_snapshot PASSED
techx-corp-platform\src\aiops-detector\tests\test_runbook_controller.py ::TestDryRunProducesAuditRecord::test_dry_run_audit_contains_proposed_command PASSED
techx-corp-platform\src\aiops-detector\tests\test_runbook_controller.py ::TestDryRunProducesAuditRecord::test_dry_run_returns_success PASSED
techx-corp-platform\src\aiops-detector\tests\test_RejectionRules::test_no_op_always_allowed PASSED
techx-corp-platform\src\aiops-detector\tests\test_RejectionRules::test_reject_when_cooldown_active PASSED
techx-corp-platform\src\aiops-detector\tests\test_RejectionRules::test_reject_when_severity_too_low PASSED
techx-corp-platform\src\aiops-detector\tests\test_SeparationOfConcerns::test_approved_flag_in_audit PASSED
techx-corp-platform\src\aiops-detector\tests\test_SeparationOfConcerns::test_execution_is_separate_from_detector_code PASSED
techx-corp-platform\src\aiops-detector\tests\test_SeparationOfConcerns::test_rejected_audit_has_no_approved_flag PASSED

============================= 10 passed in 0.04s ==============================
```

## Security & Safety Guardrails Enforced
- **Allow-list Restriction**: Only enum values defined in `RunbookAction` are permitted.
- **Preconditions**: Actions like `RESTART_DEPLOYMENT` cannot execute unless severity is `high`.
- **Cooldown Window**: Prevents spammed execution of identical mitigation steps within predefined cooldown thresholds.
- **Structural Rejection**: Rejects arbitrary string injection, shell expansions, and flagd mutations.
