# D5-PERF-03 — Staged Resource Remediation Rollout

## Safety contract

Rollout order: low-risk stateless, revenue-critical stateless,
stateful/messaging, observability, then registered exceptions. Run one wave per
approved change window. A human performance review is required before the next
wave; successful deployment alone is not approval.

The reviewed D5-02 matrix is the sole source of resource values. Put its
cumulative overlays in `deploy/resource-remediation/`. A server-side dry-run
allows Security admission policies to reject a non-compliant manifest before
mutation.

## Commands

```bash
# Preflight and evidence capture; no mutation
PROM_URL=http://prometheus.techx-observability.svc:9090 \
  ./scripts/resource-rollout.sh low-risk-stateless

# Execute only inside the controlled window
PROM_URL=http://prometheus.techx-observability.svc:9090 VERIFY_SECONDS=900 \
  ./scripts/resource-rollout.sh low-risk-stateless --execute \
  --approve-window CHG-1234
```

Repeat with `revenue-critical-stateless`, `stateful-messaging`, `observability`,
and `remaining-exceptions` only after sign-off of the preceding verdict.

## Stop and rollback

The script automatically rolls back to the captured Helm revision if a Pending
pod, CrashLoop state, or new OOMKilled termination appears. Each wave records an
exact manual command in `rollback-command.txt`. CPU throttling and SLO results
require Huy's review because labels and traffic windows cannot be inferred
safely by automation.

## Evidence and roles

Evidence is stored below
`docs/evidence/directive-05/official-<RUN_ID>/resource-rollout/<wave>/` with
before/after pods, deployments, HPA, events, usage, Helm values, Prometheus
results, apply/rollback commands, and verdict.

- Tín: window, reviewed overlays, Helm apply, wave decision.
- Huy: throttling and Browse/Cart/Checkout p95/error-rate comparison.
- Tuấn: pod state and independent rollback rehearsal.

Exceptions must record workload, missing evidence, owner, expiry, risk, and
Security audit/enforce disposition. They are never silently carried forward.

