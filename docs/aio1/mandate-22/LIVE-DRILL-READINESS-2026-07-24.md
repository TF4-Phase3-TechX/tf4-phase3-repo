# Mandate 22 live-drill readiness — 2026-07-24

Canonical Jira: [TF4AIO-83](https://aio1-xbrain.atlassian.net/browse/TF4AIO-83)

This packet prepares the controlled live proof required by Mandate 22. It does
not authorize a production mutation and is not itself evidence of a live
closed-loop pass.

## Purpose, owner and claim boundary

- Purpose: prove one bounded incident can flow through the team's own detector,
  deterministic safety policy, autonomous action, real-telemetry verification,
  and automatic rollback/escalation.
- Accountable AIO owner: Đinh Danh Nam.
- Required external owners: named CDO deployment owner and named on-call/SRE
  owner in ADR-022.
- Implemented and tested offline: controller, policy gates, Kubernetes server
  dry-run, target Lease, multi-poll verification, rollback, mutation blocking,
  escalation and reconstructable audit events.
- Not yet proven: autonomous mutation, successful recovery, forced-wrong
  rollback, MTTR improvement and audit persistence in the live cluster.

## Current runtime snapshot

Observed read-only at `2026-07-24T14:47:15Z` in namespace `techx-tf4`:

| Item | Observed state |
|---|---|
| AIOps Deployment | revision 9, desired 1, ready 1 |
| AIOps image | `c2560b9-aiops` / digest beginning `sha256:c9e3860` |
| Remediation mode | `dry-run` |
| Autonomous gate | `false` |
| Policy / runbook | `m22-v1` / `deployment-latency-rollback` |
| Product-reviews Deployment | revision 37, desired 1, ready 1 |
| Product-reviews image | `9954486-product-reviews` / digest beginning `sha256:28a0f28` |
| Product-reviews resources | request `75m/96Mi`, limit `300m/192Mi` |
| Previous ReplicaSet | revision 36, but it has the same image/digest as revision 37 |

Revision 36 is therefore retained but is not a demonstrated bad or good
alternative. A rollback between revisions 37 and 36 would not prove that
mitigation changed the failing condition.

The Argo CD `techx-corp` Application has automated self-heal enabled and ignores
only `/spec/replicas`. A direct pod-template fault or AIOps rollback may be
reconciled before the verification window. The drill must not start until CDO
approves a time-bounded reconciliation strategy.

### Read-only refresh — 2026-07-25

Observed at `2026-07-25T06:05:20Z`:

| Item | Refreshed state |
|---|---|
| AIOps Deployment | generation 9; desired/ready/available `1/1/1`; same `c2560b9-aiops` digest |
| Remediation gates | `REMEDIATION_MODE=dry-run`; autonomous `false`; allowed Deployment unset |
| Product-reviews Deployment | generation 38, revision 37; desired/ready/available `1/1/1` |
| Product-reviews template | same `9954486-product-reviews` digest; request `75m/96Mi`, limit `300m/192Mi` |
| Previous ReplicaSet | revision 36 remains retained with the same image and CPU resources as revision 37 |
| Telemetry status API | Prometheus available (17 series); OpenSearch available/yellow; Jaeger API available (17 services) |
| Active AIOps alerts | `0`; coverage-degraded alerts `0` at the observation time |

The current role cannot read the Argo CD `Application` CR, so runtime Argo
state is not claimed. The GitOps source still configures `techx-corp` with
automated self-heal and ignores only `/spec/replicas`; CDO must verify the live
Application before approving the drill.

One `product-reviews/service_latency_spike` incident was observed at
`2026-07-25T04:45:49Z` and auto-resolved after two healthy polls. It bound the
`deployment-latency-rollback` runbook but recorded `execution_attempts=0` and
`approval_status=cancelled_recovered`. This is useful detector/runbook routing
evidence only; it is not auto-mitigation evidence.

Although the aggregate telemetry status endpoint was available, one Jaeger pod
scrape returned `up=0` during the point-in-time query. Therefore the
30–60-minute telemetry-stability activation gate remains pending.

## Revalidated offline evidence

From `techx-corp-platform/src/aiops`:

```bash
python -m pytest tests/test_remediation.py tests/test_m22_mitigation_replay.py -q
python -m benchmark.mitigation_replay \
  ../../../docs/aio1/mandate-22/scenarios-v1.jsonl \
  --output ../../../docs/aio1/mandate-22/replay-report.json \
  --force
```

Result on 2026-07-24: `10 passed`; external replay `3/3` passed:

1. previous-template action verifies healthy -> `resolved`;
2. forced-wrong action verifies unhealthy, original restores healthy ->
   `rolled_back`;
3. action and rollback both verify unhealthy -> `escalated` with
   `mutation_blocked=true`.

This is evidence level 3 (offline test/replay), not live evidence.

## Proposed bounded live mechanism

Use `product-reviews` latency because it is already bound to the only
pre-authorized action. Create one temporary revision whose only fault is a
severely constrained CPU limit, then apply controlled load. The immediately
previous healthy pod template becomes the known-good rollback target.

Why this mechanism:

- it exercises the real detector and real Deployment rollback without adding a
  hidden application backdoor or changing flagd;
- the fault is explicit, reversible and limited to one replica of one service;
- the previous ReplicaSet differs in the exact property causing degradation.

Trade-off: this briefly degrades a customer-facing service and Argo self-heal
normally fights the mutation. The safer dedicated-canary alternative needs new
service routing, telemetry labels and detector configuration, which adds more
untested machinery before the deadline. CDO may reject the production-target
trade-off; if so, use a dedicated canary and keep the mandate open until that
path is live-tested.

## Hard activation gates

All rows must be complete before changing the current defaults.

| Gate | Required proof | Current state |
|---|---|---|
| ADR signatures | Full names and decisions from AIO, CDO and on-call/SRE | Pending |
| Telemetry health | Prometheus stable for 30–60 minutes; no active coverage-degraded alerts | Pending after shared-infra mitigation |
| Known-good target | Exact healthy product-reviews template/image/resources captured | Runtime observed; owner acceptance pending |
| Known-bad target | Reviewed CPU-constrained template and restore diff | Not created |
| Argo behavior | Time-boxed ignore for only product-reviews container resources, or an approved equivalent | Pending CDO |
| Slack/on-call | Drill window announced; firing/resolved/escalation channel watched | Pending |
| Mutation permission | `aiopsRemediation.liveEnabled=true` through reviewed GitOps | Off |
| Runtime mode | `REMEDIATION_MODE=live` | `dry-run` |
| Autonomous policy | `AIOPS_AUTONOMOUS_REMEDIATION_ENABLED=true` | `false` |
| Allowlist | `AIOPS_ALLOWED_DEPLOYMENTS=product-reviews` for the window | Pending explicit override |
| Stop/restore owner | Named person holding the healthy template and restore PR/command | Pending |

Do not enable only one or two gates as an experiment. The chart RBAC gate,
runtime mode and autonomous gate are deliberately independent.

## Drill A — successful autonomous mitigation

1. Capture the healthy Deployment template, current metrics and current audit
   cursor. Record the exact good image digest and resources.
2. Apply the approved temporary Argo reconciliation exception.
3. Introduce the reviewed CPU-constrained product-reviews revision and start
   bounded load.
4. Do not call the remediation API or press an approval button. Wait for the
   AIOps detector to create the latency incident.
5. Capture audit events showing policy evaluation, target Lease, Kubernetes
   server dry-run and `action_executed`.
6. Verify that the controller selects the immediately previous healthy
   ReplicaSet and that all configured real-telemetry polls are healthy.
7. Capture `remediation_verified`, Deployment/ReplicaSet state, latency/error
   recovery, Slack firing/resolved messages and detector-to-recovery MTTR.
8. Stop load and reconcile GitOps to the normal healthy state.

Pass boundary: the result is live evidence only if the trigger came from the
team detector and the action happened without a per-incident human approval.

## Drill B — forced-wrong action and automatic rollback

After Drill A, the failed CPU-constrained template should remain as the previous
ReplicaSet while the current template is healthy.

1. Capture the healthy current template as the controller's original snapshot.
2. Use bounded load to create a real latency incident on the healthy current
   revision.
3. Let the autonomous policy select the previous, deliberately constrained
   ReplicaSet. Keep the fault load active through the action verification
   window so verification fails.
4. Observe the controller restore its captured original template automatically.
   Remove the injected load only as part of the pre-agreed fault schedule, not
   by invoking rollback manually.
5. Capture `rollback_applied` and either:
   - `rollback_verified` with status `rolled_back`; or
   - `rollback_unverified_escalation` with `mutation_blocked=true`.
6. Restore normal GitOps reconciliation and confirm the healthy digest,
   readiness, latency and error-rate state.

The fault schedule and the exact point at which load stops must be recorded so
the team does not present a manually hidden failure as autonomous recovery.

## Stop conditions

Abort the drill and execute the pre-approved restore if any of these occurs:

- another production incident is active;
- Prometheus coverage becomes unavailable;
- the target is not the signed Deployment or the previous ReplicaSet differs
  from the captured template;
- customer-visible error rate crosses the CDO-approved ceiling;
- AIOps attempts more than one mutation, cannot acquire the Lease, or emits an
  unaudited action;
- Argo reconciles unexpectedly during action or rollback;
- the healthy template is not ready inside the agreed maximum window.

## Evidence to attach to TF4AIO-83

- signed ADR-022 with full names;
- GitOps activation and restoration PRs/commits;
- detector incident ID and evidence;
- before/action/verify/rollback audit events from OpenSearch;
- Prometheus latency, error-rate and readiness values for every verification
  poll;
- Deployment and ReplicaSet images/templates before and after;
- Slack firing/resolved/escalation screenshots;
- detector-to-recovery MTTR and a clearly defined manual baseline;
- final proof that runtime returned to `dry-run`, autonomous false and patch
  RBAC disabled.

