# Mandate 22 GitOps-native implementation and repro

Canonical Jira: [TF4AIO-83](https://aio1-xbrain.atlassian.net/browse/TF4AIO-83)

Current contracts:

- [ADR-022](ADR-022-safe-closed-loop-mitigation.md)
- [production drill gate](PRODUCTION-DRILL-GO-NO-GO.md)

Documents and evidence dated before 2026-07-30 describe the superseded direct
Deployment/ReplicaSet design. They remain historical evidence only and are not
activation instructions.

## Offline scenario gate

```bash
cd techx-corp-platform/src/aiops
python -m pytest tests -q
python -m benchmark.mitigation_replay \
  ../../../docs/aio1/mandate-22/scenarios-v2.jsonl \
  --output /tmp/m22-gitops-replay.json
```

The production controller runs against bounded GitHub, Argo/runtime, telemetry
and Lease adapters. Cases cover success, forced-wrong compensation and
compensation failure/quarantine.

## Restart decision gate

```bash
python -m benchmark.saga_restart_replay \
  ../../../docs/aio1/mandate-22/saga-restart-cases-v2.jsonl \
  --output /tmp/m22-saga-restart-v2.json
```

The cases cover pre-PR abandonment, ambiguous PR write rediscovery, pending
checks, merge race, runtime convergence, compensation and an open schema V1
activation block.

## Exact V1 scope

The only autonomous envelope is:

- incident `service_latency_spike`;
- component `product-reviews`;
- runbook `product-reviews-config-rollback`;
- three `MANDATE22_REVIEW_DELAY_*` entries;
- correlation annotation `aiops.techx.io/remediation-id`.

The bounded fault remains TTL/request-capped and does not call Bedrock or
modify flagd. Remediation is a protected PR, required checks, merge and Argo
rollout. Kubernetes access is read-only except for the coordination Lease.

Offline success is evidence level 3 only. It neither activates production nor
supplies CDO/on-call signatures.

The time-boxed 2026-07-31 demo exception uses separate creator and reviewer
fine-grained tokens. It demonstrates the GitOps PR/check/merge/Argo/runtime
chain, but remains assisted two-account automation and does not prove the
CDO-owned GitHub App production path.

## Kind/Argo three-round gate

The disposable runtime harness is:

```powershell
cd techx-corp-platform/src/aiops
python tests/kind/m22_gitops_sandbox.py `
  --scenario success `
  --context kind-m22-gitops-sandbox `
  --evidence-dir ../../../docs/aio1/mandate-22/evidence/sandbox-gitops-20260730-success-v1

python tests/kind/m22_gitops_sandbox.py `
  --scenario forced-wrong `
  --context kind-m22-gitops-sandbox `
  --evidence-dir ../../../docs/aio1/mandate-22/evidence/sandbox-gitops-20260730-forced-wrong-v2

python tests/kind/m22_gitops_sandbox.py `
  --scenario restart-recovery `
  --context kind-m22-gitops-sandbox `
  --evidence-dir ../../../docs/aio1/mandate-22/evidence/sandbox-gitops-20260730-restart-recovery-v1
```

The 2026-07-30 runs used a real Kind Deployment, Kubernetes Lease, local Git
branches/commits, Argo CD `v3.4.2` with `selfHeal=true`, the production detector,
worker, controller and exact `/api/product-reviews/<id>` traffic. The bounded
fault measured about 805 ms; all three post-remediation p95 samples were below
8 ms. The managed fault env disappeared, the rollout correlation matched and
the durable saga terminated `resolved`.

The forced-wrong profile retained the fault through the candidate rollout.
All three verification samples stayed above 807 ms, triggering one compensation
PR. Git/runtime returned to the exact pre-action structured hash, the original
fault remained visible, and the saga terminated `compensated_escalated` with
further mutation blocked.

The restart round discarded responses after the real branch/PR write and after
the real merge write, then recreated the controller twice. Recovery rediscovered
exactly one remediation branch and one synthetic PR, matched the merge SHA to
`origin/main`, rolled out through Argo, and terminated `resolved` without a
compensation PR.

Evidence:

- [success.json](evidence/sandbox-gitops-20260730-success-v1/success.json)
- [forced-wrong.json](evidence/sandbox-gitops-20260730-forced-wrong-v2/forced-wrong.json)
- [restart-recovery.json](evidence/sandbox-gitops-20260730-restart-recovery-v1/restart-recovery.json)

The drill found and fixed a rollout race: runtime convergence now waits until
total, ready, updated and available replicas all equal desired, preventing a
terminating fault pod from contaminating verification.

This is sandbox runtime evidence. The local adapter writes real Git commits and
enforces the three required checks, but it simulates the Git-provider PR/webhook
boundary. GitHub App/rulesets and production behavior remain unproven.
