# Mandate 22 implementation and repro

Canonical Jira: [TF4AIO-83](https://aio1-xbrain.atlassian.net/browse/TF4AIO-83)

The current production go/no-go contract is
[PRODUCTION-DRILL-GO-NO-GO.md](PRODUCTION-DRILL-GO-NO-GO.md). It reduces live
activation to five hard STOP gates and records the exact operation-scoped
signal, known-good revision pin, mutation lifecycle, traffic and restore
requirements.

## Offline external-scenario gate

```bash
cd techx-corp-platform/src/aiops
python -m benchmark.mitigation_replay \
  ../../../docs/aio1/mandate-22/scenarios-v1.jsonl \
  --output /tmp/m22-replay.json
```

The committed cases cover successful mitigation, a forced-wrong action with
verified rollback, and unhealthy rollback with mutation block plus escalation.
The harness imports the production `RemediationController`; only Kubernetes and
telemetry are bounded adapters. This does not claim a live pass.

## Durable saga restart gate (TF4AIO-89)

```bash
cd techx-corp-platform/src/aiops
python -m pytest tests/test_saga.py -q
python -m benchmark.saga_restart_replay \
  ../../../docs/aio1/mandate-22/saga-restart-cases-v1.jsonl \
  --output ../../../docs/aio1/mandate-22/saga-restart-report.json
```

Proves offline restart after preflight, action ack, verification and rollback,
plus lost Lease, conflicting desired state and incomplete records. Reviewer
verdict is machine-readable in the report JSON. Does not enable live autonomy.
The file backend must be mounted on persistent storage for cross-pod recovery;
`emptyDir` and the process-local `memory` backend do not satisfy live autonomy.
Live autonomous startup fails closed when configured with `memory`.

## Live activation

Default chart values remain `dry-run`, autonomous mode false and patch RBAC
disabled. A Kubernetes Lease provides a cross-replica target lock; the live
Role grants Deployment patch only when the separate Helm gate is enabled. CDO
must sign ADR-022, select the exact target/known-good revision and
review the drill window before enabling all three gates. Runtime closure then
requires real detector input, readiness/SLO verification, OpenSearch audit
records and the successful plus forced-wrong drill evidence on TF4AIO-83.

### Deterministic latency incident

The approved `deployment-latency-rollback` path needs a high-severity
`service_latency_spike`; resource starvation and broad load are not a reliable
way to create that signal. Product Reviews therefore supports an
off-by-default, Deployment-revision-coupled delay on `GetProductReviews`:

- `MANDATE22_REVIEW_DELAY_MS` (hard cap: 3000 ms);
- `MANDATE22_REVIEW_DELAY_TTL_SECONDS` (hard cap: 900 seconds);
- `MANDATE22_REVIEW_DELAY_MAX_REQUESTS` (hard cap: 200 requests per pod).

All three values are required to activate the fault. Health runs on the
separate health server and is never delayed. The TTL and request budget are
independent deadmen; invalid configuration fails safe to normal service
behavior. The TTL starts on the first eligible `GetProductReviews` request,
not pod startup, so an approval or reconciliation delay cannot silently consume
the drill window; the request budget is enforced from the same first request.
Because activation changes the Deployment pod template, the prior ReplicaSet
contains no fault variables and a real template rollback causally removes the
delay. The drill still requires CDO approval, a pinned retained known-good
revision, bounded mutation RBAC, real Prometheus detection and post-action
runtime verification. The mechanism exposes no runtime control API and does
not call Bedrock or mutate `flagd`. Unit/CI success alone is not a live pass.

The current runtime inventory, activation gates, proposed fault mechanism,
stop conditions and evidence checklist are recorded in
[`LIVE-DRILL-READINESS-2026-07-24.md`](LIVE-DRILL-READINESS-2026-07-24.md).

## Post-V7 local recovery gate

The V7 drill exposed a startup/liveness loop while a restarted process awaited
long saga verification, followed by cleanup failure when Deployment patch RBAC
was restored too early. The implementation, disposable-Kubernetes test matrix,
three consecutive local cycles and strict non-live claim are recorded in
[`LOCAL-RECOVERY-GATE-2026-07-29.md`](LOCAL-RECOVERY-GATE-2026-07-29.md).

This gate must pass before another production drill. It does not replace the
remaining live success-path evidence.

## Final evidence packet

The controlled 2026-07-25 drill, machine-readable audit summary, timing,
blockers and strict claim boundary are indexed in
[`FINAL-EVIDENCE-2026-07-25.md`](FINAL-EVIDENCE-2026-07-25.md).

The drill proves the live safety/failure path. It does not prove a successful
closed-loop pass because the deployed cross-service verifier rejected the
otherwise recovered target. No further EKS/load drill is authorized during the
CDO-04 freeze window.
