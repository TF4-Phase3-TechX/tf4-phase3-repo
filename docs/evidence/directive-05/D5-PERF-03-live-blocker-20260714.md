# D5-PERF-03 live rollout blocker — 2026-07-14

## Verdict

**BLOCKED — do not start a resource-remediation wave.** The production
namespace does not satisfy the mandatory preflight condition of zero Pending
pods, and the supplied role has no mutation permission.

## Runtime observations

- Cluster/account: `techx-tf4-cluster`, AWS account `511825856493`.
- Namespace: `techx-tf4`.
- Seven current application Deployments have no Ready/Available replica:
  `cart`, `checkout`, `frontend`, `payment`, `product-catalog`,
  `product-reviews`, and `recommendation`.
- Their current pods are Pending. Scheduler events report `0/2 nodes are
  available: 2 Insufficient cpu`.
- A second `load-generator` ReplicaSet pod is also Pending for insufficient CPU,
  while the older load-generator pod remains Ready.
- Frontend and checkout HPAs report `cpu: <unknown>/70%`; warning events say the
  resource metrics API returned no metrics.
- Earlier warnings in the same event history include missing `gp3` StorageClass
  for Kafka/Valkey PVCs and readiness failures, although the current Kafka and
  Valkey pods were Running at collection time.
- No new OOMKilled termination was visible in current container status.

These observations were collected read-only. They are a point-in-time
preflight result, not evidence of a successful rollout or stable SLO.

## Access observations

The supplied `TF4-CostPerfReadOnlyAlerting` role can read Deployments and Pods,
but Kubernetes authorization returned:

| Check | Result |
|---|---|
| Get Deployments in `techx-tf4` | yes |
| Patch Deployments in `techx-tf4` | no |
| Create Pods in `techx-tf4` | no |
| List Pod metrics (`metrics.k8s.io`) | forbidden |
| List Node metrics (`metrics.k8s.io`) | forbidden |
| List Nodes | forbidden |

Consequently this role cannot apply Helm remediation, run an admission reject
test, collect live CPU/memory usage, or validate node reservation/headroom.

## Required unblock actions

1. Reliability/Platform restores all application Deployments to Ready and
   resolves the two-node CPU capacity shortage. Pre-scaling is the documented
   safe option; do not lower requests blindly to force scheduling.
2. Metrics ownership restores HPA resource metrics and grants the performance
   team read access to Pod/Node Metrics API data (or provides equivalent
   Prometheus queries and exports).
3. D5-02 produces and reviews a measured resource matrix from a representative
   traffic window.
4. An operator with approved Helm mutation permission executes each wave in a
   controlled window. The performance role may remain read-only for independent
   observation.
5. Security supplies a test namespace and admission policy scope before the
   separate rejection test.

Once items 1–3 pass, populate the overlays described in
`deploy/resource-remediation/README.md`, run the dry-run, and then execute waves
with `scripts/resource-rollout.sh`.

