# Architecture Decision Record: ADR-022
## Safe Closed-Loop Mitigation (MANDATE-22)

**Status:** Approved
**Date:** 2026-07-22
**Context:** AI MANDATE #22 (TF4AIO-83) requires the AIOps platform to autonomously execute mitigating actions without per-incident human approval, provided the system is safe (dry-run/cooldown/blast-radius), verifies the result, and rolls back on failure.

### Context and Problem Statement
The current AIOps remediation system (`worker.py` -> `remediation.py`) requires a manual human button press for every incident (`IncidentStatus.AWAITING_APPROVAL`). If an incident occurs at midnight, customers endure degraded service until an engineer wakes up to approve the action. We need to transition from per-incident manual approval to a pre-authorized autonomous policy that can mitigate known issues safely.

### Decision
We will implement a **Pre-authorized Autonomous Policy Gate** for closed-loop mitigation.

Instead of human approval occurring at *runtime* per incident, approval is shifted left to *deployment time*. The Chief Data Officer (CDO) and Platform Owners authorize a policy envelope defined by:
1. `REMEDIATION_MODE=live` set at the cluster level.
2. `AUTONOMOUS_INCIDENT_TYPES` allowlist (currently only `service_latency_spike`).
3. CDO-approved allowed deployments (`AIOPS_ALLOWED_DEPLOYMENTS`).
4. Minimum detector confidence threshold (`AIOPS_REMEDIATION_CONFIDENCE_THRESHOLD`).

When an incident is detected, the `RemediationController.should_auto_execute()` gate evaluates the incident against this envelope. If all checks pass—including runtime safety checks (cooldown windows and blast-radius/execution limits)—the controller autonomously executes the mitigation.

The autonomous path uses the same rollback, verify, and restore-on-fail logic as the manual path but records `auto_approved=True` in the audit chain.

### Algorithm
1. **Detect:** Worker polls telemetry and creates an Incident.
2. **Policy Gate:** `should_auto_execute` evaluates allowlists, confidence, cooldown, and lock state.
   - If fail: fallback to manual `request_approval`.
   - If pass: proceed to autonomous execution.
3. **Execute:** Acquire lock, set cooldown, and patch Kubernetes ReplicaSet. Set status to `AUTO_EXECUTING`.
4. **Verify:** Wait for rollout ready, then verify SLO (latency/error rates).
5. **Rollback/Resolve:** 
   - If healthy: mark `RESOLVED`.
   - If unhealthy (or verify fails): restore original template (rollback) and mark `ROLLED_BACK`.
6. **Audit:** Every step (trigger, policy decision, mutate, verify, rollback) writes an `AuditEvent` to the incident for reconstruction.

### Consequences
* **Positive:** Reduced MTTR for known incident types. Safe mitigation with cooldowns and automated rollback. Fully auditable decisions.
* **Negative:** Requires rigorous testing and tuning of the detector confidence to avoid false positives triggering unnecessary autonomous actions.

### Sign-off
Signed by: AIOps Team (AI Task Force)
