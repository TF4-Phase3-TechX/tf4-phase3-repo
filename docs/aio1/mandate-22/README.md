# Mandate 22 implementation and repro

Canonical Jira: [TF4AIO-83](https://aio1-xbrain.atlassian.net/browse/TF4AIO-83)

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

## Live activation

Default chart values remain `dry-run`, autonomous mode false and patch RBAC
disabled. A Kubernetes Lease provides a cross-replica target lock; the live
Role grants Deployment patch only when the separate Helm gate is enabled. CDO
must sign ADR-022, select the exact target/known-good revision and
review the drill window before enabling all three gates. Runtime closure then
requires real detector input, readiness/SLO verification, OpenSearch audit
records and the successful plus forced-wrong drill evidence on TF4AIO-83.

The current runtime inventory, activation gates, proposed fault mechanism,
stop conditions and evidence checklist are recorded in
[`LIVE-DRILL-READINESS-2026-07-24.md`](LIVE-DRILL-READINESS-2026-07-24.md).

## Final evidence packet

The controlled 2026-07-25 drill, machine-readable audit summary, timing,
blockers and strict claim boundary are indexed in
[`FINAL-EVIDENCE-2026-07-25.md`](FINAL-EVIDENCE-2026-07-25.md).

The drill proves the live safety/failure path. It does not prove a successful
closed-loop pass because the deployed cross-service verifier rejected the
otherwise recovered target. No further EKS/load drill is authorized during the
CDO-04 freeze window.
