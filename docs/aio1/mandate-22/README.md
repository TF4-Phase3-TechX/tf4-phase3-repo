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
