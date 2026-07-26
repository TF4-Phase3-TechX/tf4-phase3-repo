# ADR-022: Pre-authorized safe closed-loop mitigation

- Date: 2026-07-21
- Status: **Accepted by AIO1 Tech Lead for the documented policy and captured
  safety-path evidence; on-call/SRE signature and successful live verification
  remain pending**
- Canonical Jira: [TF4AIO-83](https://aio1-xbrain.atlassian.net/browse/TF4AIO-83)

## Signature record

| Name | Role | Decision | Date | Scope |
|---|---|---|---|---|
| Đinh Danh Nam (`c0mmie-b0msh3ll`) | AIO1 Tech Lead / policy owner | Accepted | 2026-07-25 | Deterministic policy, bounded action, target-scoped verification fix, rollback/escalation and stated claim boundary |
| Đinh Viết Quyết (CDO08) | CDO deployment owner | Approved for the bounded deployment/drill scope | 2026-07-25 | Target, RBAC, retained known-good revision, blast radius and reviewed drill window; named approval communicated to AIO1 |
| _Name required_ | On-call/SRE owner | Pending | — | Escalation, telemetry verification and live-drill acceptance |

The remaining on-call/SRE row is a hard activation gate. It is not inferred
from generic PR approval.

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
another EKS/load drill. AIO1 and the CDO deployment owner accept the documented
policy and bounded drill scope, but successful post-fix live verification and
the named on-call/SRE signature remain pending. Generic PR approvals are not a
substitute for that remaining role.

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

## Accepted trade-offs (post #669 hardening)

1. **Process-local quarantine.** Post-mutation safety quarantine survives incident
   auto-resolve but is lost on pod restart. This is acceptable only while
   autonomous live mode is disabled. A durable saga or CRD-backed quarantine is
   required before sustained live autonomous operation.
2. **Target-scoped verification.** Post-action SLO verification is scoped to the
   mutated service only. Cross-service or end-to-end dependency guards (e.g.
   checkout/storefront error rate) are not silently applied; they require an
   explicit approved dependency mapping in action policy configuration.
3. **Known-good pin is mandatory for live mutation.** Live mode refuses to patch
   unless `AIOPS_KNOWN_GOOD_REVISIONS` includes the target. Dry-run may still
   resolve `owned[1]` as a candidate for operator review; that candidate is not
   treated as proven known-good.
4. **Orphan mutation on pod crash.** If the AIOps pod crashes after
   `action_executed` but before verification completes, the in-memory incident,
   quarantine and lock state are lost. The Kubernetes Lease expires after its
   TTL, but no automatic rollback or escalation occurs for the orphaned
   mutation. Argo CD / GitOps eventual sync is the only recovery. This is
   acceptable only while autonomous live mode is disabled; a durable
   checkpoint/saga is required before sustained operation.
5. **No Argo CD self-heal coordination.** During the post-action verification
   window, Argo CD self-heal may detect the live-state drift and sync the
   Deployment back to its Git-declared spec, overwriting the AIOps mutation or
   rollback. The Kubernetes Lease prevents only AIOps-vs-AIOps conflicts, not
   Argo overwrites. CDO must either disable self-heal for target Deployments
   during autonomous windows or add an Argo sync-ignore annotation before
   enabling live autonomous mode.
6. **`mutation_blocked` is post-mutation only.** Pre-mutation policy denials
   (missing evidence, lease held, low confidence, missing pin) escalate without
   setting `mutation_blocked` so recovery can clear the incident and a later
   cycle can re-attempt. Permanent process-local quarantine is applied only
   after a live patch / rollback safety failure.
7. **Evidence freshness between authorize and patch.** Policy evaluates
   Prometheus evidence once before preflight; the controller does not re-query
   immediately before the live patch. The bounded single-service window is
   seconds-long; a mid-flight telemetry loss after authorize is accepted under
   dry-run / freeze constraints and remains a follow-up for durable saga work.
8. **Ambiguous live patch outcome.** A Kubernetes client timeout can occur after
   the API server committed the patch. The controller therefore performs one
   live patch attempt only. Any exception after the attempt is classified as
   `action_outcome_unknown`, blocks further mutation and quarantines the target
   for operator reconciliation; it is never treated as a safe pre-mutation
   failure. This fail-closed response cannot determine the actual cluster state
   by itself. Durable read-after-write reconciliation remains part of
   TF4AIO-89.

## Activation gates

1. Review and merge implementation.
2. CDO names one Deployment and confirms the retained known-good ReplicaSet.
3. Sign this ADR with full names.
4. Promote the exact image with autonomous mode first dry-run, then live RBAC.
5. Run one successful mitigation and one forced-wrong verified rollback.
6. Attach real telemetry, audit logs and measured MTTR to TF4AIO-83.
