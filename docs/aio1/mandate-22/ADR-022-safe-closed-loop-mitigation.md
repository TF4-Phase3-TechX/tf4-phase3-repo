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
   required before sustained live autonomous operation (see TF4AIO-89 below).
2. **Target-scoped verification.** Post-action SLO verification is scoped to the
   mutated service only. Cross-service or end-to-end dependency guards (e.g.
   checkout/storefront error rate) are not silently applied; they require an
   explicit approved dependency mapping in action policy configuration.
3. **Known-good pin is mandatory for live mutation.** Live mode refuses to patch
   unless `AIOPS_KNOWN_GOOD_REVISIONS` includes the target. Dry-run may still
   resolve `owned[1]` as a candidate for operator review; that candidate is not
   treated as proven known-good.
4. **Orphan mutation on pod crash (mitigated by TF4AIO-89).** Without a durable
   saga, a crash after `action_executed` loses in-memory state. TF4AIO-89 adds
   durable checkpoints and startup reconcile so verification/restore can continue
   without a second mutation. Process-local quarantine alone remains insufficient
   for sustained live autonomy.
5. **Argo CD self-heal race (mitigated by TF4AIO-89 contract).** During the
   verification window Argo may overwrite the mutation. TF4AIO-89 opens an
   ownership annotation window and fail-closed on template drift; Application-level
   `ignoreDifferences` for `/spec/template` remains a CDO GitOps requirement.
6. **`mutation_blocked` is post-mutation only.** Pre-mutation policy denials
   (missing evidence, lease held, low confidence, missing pin) escalate without
   setting `mutation_blocked` so recovery can clear the incident and a later
   cycle can re-attempt. Permanent process-local quarantine is applied only
   after a live patch / rollback safety failure.
7. **Evidence freshness between authorize and patch.** Policy evaluates
   Prometheus evidence once before preflight; the controller does not re-query
   immediately before the live patch. The bounded single-service window is
   seconds-long; a mid-flight telemetry loss after authorize is accepted under
   dry-run / freeze constraints.
8. **Ambiguous live patch outcome.** A Kubernetes client timeout can occur after
   the API server committed the patch. The controller therefore performs one
   live patch attempt only. Any exception after the attempt is classified as
   `action_outcome_unknown`, blocks further mutation and quarantines the target
   for operator reconciliation; it is never treated as a safe pre-mutation
   failure. Durable read-after-write reconciliation is part of TF4AIO-89.

## Durable saga and Argo coordination (TF4AIO-89)

### Decision

Persist each live remediation attempt as a durable **saga record** outside
process memory (offline durable backend: JSON files under `AIOPS_SAGA_PATH` on
an operator-provided persistent volume). The chart remains fail-safe with a
`memory` default for dry-run; startup rejects the combination of live +
autonomous remediation + memory saga backend.
On AIOps startup the controller loads every non-terminal saga and applies a
fixed decision table:

| Crash phase | Restart action |
|---|---|
| preflight / lease / argo window (no mutation flag) | Abandon; never mutate |
| action acknowledged / verifying | Continue verification; never re-patch the known-good template |
| verifying unhealthy or rolling back | Restore captured original template and re-verify |
| incomplete post-mutation record | Fail closed, escalate, `mutation_blocked` |
| Lease not re-acquirable | Fail closed; refuse second mutation |

One open saga per target is enforced: a second incident cannot start while a
saga remains non-terminal.

### Argo CD contract

During the mutation/verification window AIOps annotates the target Deployment:

- `aiops.techx/mutation-window` / `owned-by-incident` / window expiry

**Application-level `ignoreDifferences` for `/spec/template` remains a CDO
GitOps requirement** for the bounded drill window. Annotations alone do not
pause Argo. After the live patch, AIOps compares the live template to the saga
expected template; drift is classified as `argo_overwrite` or
`conflicting_desired_state` and fails closed (restore original when available).
The controller deliberately does not write Argo's reserved
`argocd.argoproj.io/compare-options` annotation because doing so could overwrite
an operator-owned value and does not pause self-heal.

### Cleanup / retention

Terminal sagas are retained for `AIOPS_SAGA_RETENTION_HOURS` (default 72h) for
audit. Startup automatically prunes only fully-cleaned terminal records older
than the cutoff; non-terminal records and terminal records that still own a
Lease/Argo window are never retention-pruned. Lease and Argo window annotations
are cleared in the `finally` / resume path.

### Rejected alternative

Embedding full saga state only in the Kubernetes Lease annotation was rejected:
Lease TTL expiry would drop intent, payload size is limited, and verification
samples/templates do not fit a safe Lease-only design. A full CRD reconciler is
deferred; file + persistent-volume startup reconcile meets offline evidence
level 3 without cluster CRD promotion under freeze. `emptyDir` is explicitly
not a durable option because it is lost on pod replacement.

### Offline evidence

```bash
cd techx-corp-platform/src/aiops
python -m pytest tests/test_saga.py -q
python -m benchmark.saga_restart_replay \
  ../../../docs/aio1/mandate-22/saga-restart-cases-v1.jsonl \
  --output ../../../docs/aio1/mandate-22/saga-restart-report.json
```

Claim boundary unchanged: offline/integration only. Do not enable sustained
live autonomy from TF4AIO-89 alone.

## Activation gates

1. Review and merge implementation.
2. CDO names one Deployment and confirms the retained known-good ReplicaSet.
3. Sign this ADR with full names.
4. Provision the reviewed persistent volume, set `AIOPS_SAGA_BACKEND=file` and
   `AIOPS_SAGA_PATH`, then promote the exact image with autonomous mode first
   dry-run, then live RBAC.
5. Run one successful mitigation and one forced-wrong verified rollback.
6. Attach real telemetry, audit logs and measured MTTR to TF4AIO-83.
