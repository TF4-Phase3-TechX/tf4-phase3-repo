# ADR-022: Pre-authorized safe closed-loop mitigation

- Date: 2026-07-21
- Status: **Proposed — controlled runtime evidence captured; formal signatures
  and successful live verification pending**
- Canonical Jira: [TF4AIO-83](https://aio1-xbrain.atlassian.net/browse/TF4AIO-83)

## Signature record

| Name | Role | Decision | Date | Scope |
|---|---|---|---|---|
| Đinh Danh Nam (`c0mmie-b0msh3ll`) | AIO1 Tech Lead / policy owner | Proposed | 2026-07-21 | Architecture and implementation submitted for review |
| _Name required_ | CDO deployment owner | Pending | — | Target, RBAC, known-good revision, blast radius and drill window |
| _Name required_ | On-call/SRE owner | Pending | — | Escalation, telemetry verification and live-drill acceptance |

Pending rows are hard activation gates. They are not inferred from generic PR approval.

## Runtime decision record — 2026-07-25

A reviewed, time-bounded production drill exercised the detector, policy,
Lease, server dry-run, one autonomous Deployment action, real-telemetry
verification, automatic rollback, escalation, mutation block and GitOps
restore. See
[`FINAL-EVIDENCE-2026-07-25.md`](FINAL-EVIDENCE-2026-07-25.md).

The target product-reviews p95 recovered from `15000ms` to `1.9ms`, but the
deployed verifier also applied an undeclared aggregate frontend/checkout
error-rate guard. The action was therefore rejected and the safety branch ran.
The follow-up implementation scopes the mandatory error-rate guard to the
mutated service and fails closed when that target telemetry is absent.

This follow-up is implemented/tested offline only. The CDO-04 freeze prohibits
another EKS/load drill, so this ADR remains Proposed. PR approvals or chat
acknowledgements are evidence of reviewed activity, not substitutes for the two
pending named signatures above.

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
