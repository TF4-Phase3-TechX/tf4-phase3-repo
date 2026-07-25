# ADR-022: Pre-authorized safe closed-loop mitigation

- Date: 2026-07-21
- Status: **Proposed — runtime signatures and live drills pending**
- Canonical Jira: [TF4AIO-83](https://aio1-xbrain.atlassian.net/browse/TF4AIO-83)

## Signature record

| Name | Role | Decision | Date | Scope |
|---|---|---|---|---|
| Đinh Danh Nam (`c0mmie-b0msh3ll`) | AIO1 Tech Lead / policy owner | Proposed | 2026-07-21 | Architecture and implementation submitted for review |
| _Name required_ | CDO deployment owner | Pending | — | Target, RBAC, known-good revision, blast radius and drill window |
| _Name required_ | On-call/SRE owner | Pending | — | Escalation, telemetry verification and live-drill acceptance |

Pending rows are hard activation gates. They are not inferred from generic PR approval.

## Decision

Use a deployment-time, signed policy envelope rather than a human approval for
every incident. The detector may autonomously execute only the exact
`deployment-latency-rollback` action when all deterministic checks pass:

- autonomous mode and exact policy version are enabled by reviewed deployment config;
- incident is high severity, sufficiently confident and carries telemetry evidence;
- runbook and target Deployment are allowlisted;
- one mutation attempt per incident and one action per target are enforced;
- a namespace-scoped Kubernetes Lease prevents duplicate action across pod restarts/replicas;
- preflight resolves both current and previous ReplicaSet templates;
- live mutation permission is separately gated by Helm/RBAC;
- recovery must hold throughout a multi-poll readiness and SLO window.

If action verification fails, the controller restores the captured original
template and verifies that rollback over another telemetry window. An
unverified or failed rollback blocks further mutation and escalates. LLM output,
free-form shell, native HPA/restart and flagd mutation never authorize closure.

## Why

Per-incident approval is safe but does not satisfy Mandate 22's autonomous
property. Unbounded autonomy is unsafe. Pre-authorizing a narrow deterministic
policy once gives the system permission to act without a midnight button while
retaining an auditable blast-radius boundary.

## Audit contract

Every run records policy version and checks, incident evidence, preflight,
action, every verification sample, rollback application, rollback verification,
mutation-blocked state and escalation reason. The external replay entry accepts
JSONL without code changes and exercises the canonical runtime controller.

## Activation gates

1. Review and merge implementation.
2. CDO names one Deployment and confirms the retained known-good ReplicaSet.
3. Sign this ADR with full names.
4. Promote the exact image with autonomous mode first dry-run, then live RBAC.
5. Run one successful mitigation and one forced-wrong verified rollback.
6. Attach real telemetry, audit logs and measured MTTR to TF4AIO-83.
