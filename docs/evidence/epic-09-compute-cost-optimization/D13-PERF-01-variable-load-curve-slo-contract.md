# D13-PERF-01 — Variable Load Curve and SLO Contract

## 1. Purpose and status

This document is the execution contract for the Directive #13 baseline and
optimized EKS runs. Both runs MUST use the same load shape, traffic mix,
duration, request-denominator rules, SLO gates, and evidence checkpoints.

This artifact defines the test. It does not claim that either run or the Spot
interruption drill has already been executed. Runtime values and evidence links
must be filled in during an approved test window.

## 2. Immutable comparison contract

| Parameter | Contract value |
|---|---|
| Load generator | Repository Locust `WebsiteUser` implementation |
| Target | `http://frontend-proxy:8080` from the in-cluster load generator |
| Initial/return load | 25 concurrent users |
| Peak load | 200 concurrent users |
| Low baseline | 5 minutes |
| Ramp-up | Linear, 25 to 200 users over 5 minutes |
| Peak | 200 users for 15 minutes |
| Ramp-down | Linear, 200 to 25 users over 5 minutes |
| Low observation | 25 users for at least 30 minutes and until the exit gate passes |
| Minimum total duration | 60 minutes |
| Traffic mix | Same checked-out `locustfile.py`, test data, feature flags, task weights, wait time, host, and randomization behavior for both runs |
| Request-volume tolerance | Absolute difference between run totals MUST be no more than 5% |
| Interruption traffic | Optimized run only; load generator remains active at 200 users throughout the interruption checkpoint |

No run may change the user curve, endpoint/task weights, test data, timeout,
retry behavior, feature flags, request-generation settings, or denominator
definition. Record the reviewed Git SHA and load-generator image digest before
each run.

## 3. Exact phase timeline

`RUN_START_UTC` is an approved RFC 3339 UTC timestamp such as
`2026-07-20T02:00:00Z`. It MUST be populated before starting a run. The operator
calculates and records every boundary below in UTC; local timestamps are not
accepted as the source of truth.

| Phase | Relative window | Users | Exit condition |
|---|---:|---:|---|
| Low baseline | `T+00:00` to `T+05:00` | 25 | Five complete minutes captured |
| Ramp-up | `T+05:00` to `T+10:00` | Linear 25 → 200 | 200 active users reached |
| Peak | `T+10:00` to `T+25:00` | 200 | Fifteen complete minutes captured |
| Ramp-down | `T+25:00` to `T+30:00` | Linear 200 → 25 | 25 active users reached |
| Low observation | `T+30:00` to at least `T+60:00` | 25 | Observation exit gate passes |

The Spot interruption is scheduled within the optimized peak window. The
approved `INTERRUPTION_TIMESTAMP_UTC` SHOULD be between `T+15:00` and
`T+20:00`, leaving at least five minutes of peak traffic before and after it.
The actual termination timestamp must also be recorded; a scheduled timestamp
alone is not evidence.

### Run window record

```text
BASELINE_RUN_START_UTC=
BASELINE_RUN_END_UTC=
OPTIMIZED_RUN_START_UTC=
OPTIMIZED_RUN_END_UTC=
OBSERVATION_PERIOD_MINUTES=30
SCHEDULED_INTERRUPTION_TIMESTAMP_UTC=
ACTUAL_INTERRUPTION_TIMESTAMP_UTC=
REVIEWED_GIT_SHA=
LOAD_GENERATOR_IMAGE_DIGEST=
CHANGE_TICKET=
OPERATOR=
```

If low-load observation must continue beyond 30 minutes, update the run end
timestamp and record the reason. Both runs must use the same final duration for
the node-hour comparison; extend or rerun the shorter run when necessary.

## 4. Observation exit gate

The low-observation phase ends only after all of the following are true:

- at least 30 minutes of low-load traffic have elapsed;
- HPA replicas have scaled down and stabilized;
- Karpenter has evaluated consolidation;
- all peak-only NodeClaims have terminated, or a named blocker is recorded;
- worker count has stabilized at the approved low-load baseline;
- the load generator is still producing requests; and
- all customer-facing SLOs remain within contract.

## 5. Request denominator and error accounting

All success rates use raw Locust request counts for the complete run. Do not
use a dashboard sampling interval or successful-checkout count as the common
denominator.

```text
flow_total = flow_success + flow_failure
flow_success_rate_percent = 100 * flow_success / flow_total
request_volume_difference_percent =
  100 * abs(optimized_total - baseline_total) / baseline_total
```

Rules:

- `flow_total` must be greater than zero for Browse, Cart, and Checkout;
- classify each Locust request name into exactly one documented flow;
- preserve `*_stats.csv`, `*_stats_history.csv`, `*_failures.csv`, and
  `*_exceptions.csv` without manual editing;
- record HTTP 5xx, timeouts, connection resets, and Locust exceptions as raw
  integer counts, even if their rate rounds to zero;
- use Locust failed requests (`# failures`) as the authoritative
  `customer_error_count`. Locust already records a request once when it ends in
  HTTP 5xx, timeout, connection reset, or another client exception, so those
  diagnostic categories MUST NOT be added to the total again;
- retain HTTP 5xx, timeout, connection-reset, and exception counts as diagnostic
  breakdowns. Their sum is not the authoritative customer error count;
- calculate interruption failures from cumulative counters without resetting
  Locust: `post_interruption_failures - pre_interruption_failures`;
- the optimized run's interruption requests and failures remain in the complete
  run denominator. Do not subtract, isolate, or restart statistics for the drill;
- request-volume difference above 5% invalidates direct comparison. Rerun is
  preferred; any normalization requires reviewer approval and documentation.

### Locust request-name mapping

Use HTTP method plus normalized Locust request name. Dynamic product IDs are
normalized to `{product_id}` before aggregation.

| Flow | Locust method and normalized request name |
|---|---|
| Browse | `GET /`, `GET /api/products/{product_id}`, `GET /api/recommendations`, `GET /api/product-reviews/{product_id}`, `POST /api/product-ask-ai-assistant/{product_id}`, `GET /api/data/` |
| Cart | `GET /api/cart`, `POST /api/cart` |
| Checkout | `POST /api/checkout` |

The `add_to_cart` calls made as checkout setup still contribute to the Cart
denominator; the final `POST /api/checkout` contributes to Checkout. Any new or
unmapped request name invalidates automatic flow aggregation until this table is
reviewed and updated. Feature-flagged `flood_home` traffic maps to Browse, but
the flag value must be identical for baseline and optimized runs.

### Result record

| Metric | Baseline | Optimized | Pass rule |
|---|---:|---:|---|
| Total requests | | | Difference ≤ 5% |
| Browse total / failures / success % | | | Total > 0; success ≥ 99.5% |
| Cart total / failures / success % | | | Total > 0; success ≥ 99.5% |
| Checkout total / failures / success % | | | Total > 0; success ≥ 99.0% |
| Storefront p95 (ms) | | | < 1000 ms |
| HTTP 5xx | | | Record raw count |
| Timeouts | | | Record raw count |
| Connection resets | | | Record raw count |
| Locust exceptions | | | Record raw count |
| Interruption customer errors | N/A | | Exactly 0 |

## 6. Capacity and compute result contract

Calculate each worker's hours from its overlap with the test window, not from a
node-count snapshot:

```text
node_seconds_i = max(
  0,
  min(instance_termination_utc_i, run_end_utc)
    - max(instance_launch_utc_i, run_start_utc)
)

total_worker_node_hours = sum(node_seconds_i) / 3600

node_hour_reduction_percent =
  100 * (baseline_worker_node_hours - optimized_worker_node_hours)
      / baseline_worker_node_hours

spot_node_hour_ratio_percent =
  100 * optimized_spot_worker_node_hours
      / optimized_total_worker_node_hours
```

Use EC2 instance launch and termination timestamps as the authoritative
lifecycle source. Correlate each instance ID to Kubernetes node and NodeClaim.
NodeClaim creation/deletion timestamps provide Karpenter evidence and may be
used as a documented fallback only when an EC2 termination timestamp is not yet
available. For a node alive at `run_end_utc`, clamp termination to
`run_end_utc`; for a node launched before the run, clamp launch to
`run_start_utc`. Exclude control-plane services and non-worker capacity.

| Capacity metric | Baseline | Optimized | Pass rule |
|---|---:|---:|---|
| Total worker node-hours | | | Source timestamps retained |
| On-Demand worker node-hours | | | Report separately |
| Spot worker node-hours | | | Report separately |
| Graviton/ARM64 worker node-hours | | | Greater than 0 in optimized run |
| Node-hour reduction | N/A | | At least 30% |
| Spot node-hour ratio | N/A | | At least 50% |
| Peak worker count | | | Record |
| Final resting worker count | | | Returns to approved baseline |

### Graviton workload serving evidence

Having an idle ARM64 node does not satisfy the contract. Record a real workload
scheduled on ARM64 and prove that it served traffic during the test window:

```text
GRAVITON_INSTANCE_ID=
GRAVITON_NODE_NAME=
GRAVITON_NODECLAIM_NAME=
GRAVITON_INSTANCE_TYPE=
GRAVITON_ARCHITECTURE=arm64
GRAVITON_WORKLOAD_NAMESPACE=
GRAVITON_WORKLOAD_NAME=
GRAVITON_POD_NAMES=
GRAVITON_TRAFFIC_WINDOW_START_UTC=
GRAVITON_TRAFFIC_WINDOW_END_UTC=
GRAVITON_REQUEST_COUNT=
GRAVITON_SUCCESSFUL_REQUEST_COUNT=
GRAVITON_NODE_HOURS=
```

Required evidence includes EC2 architecture, Kubernetes `kubernetes.io/arch`,
pod placement, workload readiness, and a request/trace/metric attributable to
the ARM64 workload with a denominator greater than zero.

## 7. SLO contract

| Customer indicator | Target | Evaluation window | Verdict |
|---|---:|---|---|
| Checkout success | ≥ 99.0% | Complete run and interruption interval | Hard gate |
| Browse success | ≥ 99.5% | Complete run and interruption interval | Hard gate |
| Cart success | ≥ 99.5% | Complete run and interruption interval | Hard gate |
| Storefront p95 | < 1000 ms | Rolling 5-minute window, evaluated every minute with at least 20 Storefront requests; complete-run p95 is also reported | Hard gate after two consecutive failing evaluations |
| Spot interruption customer error count | 0 | Interruption until recovery | Hard gate |

SLOs apply to both runs. A cost or node-hour improvement cannot receive a PASS
when any customer-facing SLO fails.

One scrape or incomplete low-volume bucket does not trigger the p95 hard stop.
The first valid rolling-window breach is a warning and capture checkpoint; two
consecutive valid breaches trigger stop/rollback. During the interruption, raw
customer errors still trigger an immediate hard stop without waiting for two
p95 evaluations.

## 8. Spot interruption checkpoint

The drill is valid only when the selected EC2 instance is Spot, Ready, serving
in-scope replicated workload, and receiving traffic. The load generator MUST
continue uninterrupted at peak load. Do not stop/restart Locust or reset its
statistics around the drill.

```text
SPOT_INSTANCE_ID=
KUBERNETES_NODE_NAME=
NODECLAIM_NAME=
INSTANCE_TYPE=
ARCHITECTURE=
WORKLOADS_ON_NODE=
PRE_DRILL_CUMULATIVE_REQUESTS=
PRE_DRILL_CUMULATIVE_FAILURES=
ACTUAL_INTERRUPTION_TIMESTAMP_UTC=
REPLACEMENT_READY_TIMESTAMP_UTC=
RESCHEDULE_COMPLETE_TIMESTAMP_UTC=
POST_DRILL_CUMULATIVE_REQUESTS=
POST_DRILL_CUMULATIVE_FAILURES=
INTERRUPTION_REQUEST_COUNT=POST_REQUESTS-PRE_REQUESTS
CUSTOMER_ERROR_COUNT=POST_FAILURES-PRE_FAILURES
DIAGNOSTIC_BROWSE_FAILURES=
DIAGNOSTIC_CART_FAILURES=
DIAGNOSTIC_CHECKOUT_FAILURES=
DIAGNOSTIC_HTTP_5XX=
DIAGNOSTIC_TIMEOUTS=
DIAGNOSTIC_CONNECTION_RESETS=
DIAGNOSTIC_LOCUST_EXCEPTIONS=
```

All pre/post values are cumulative counters from the same uninterrupted Locust
process. `CUSTOMER_ERROR_COUNT` must equal zero, while
`INTERRUPTION_REQUEST_COUNT` must be greater than zero. The same requests and
failures remain part of the optimized complete-run totals.

Capture node termination, NotReady transition, pod eviction, PDB behavior,
rescheduling, replacement NodeClaim creation, replacement readiness, HPA state,
and Storefront p95 on one UTC-aligned timeline.

## 9. Stop and rollback conditions

Stop load safely and invoke the approved rollback runbook immediately when any
of these conditions occurs:

- Checkout success is below 99.0%;
- Browse or Cart success is below 99.5%;
- Storefront p95 reaches or exceeds 1000 ms for two consecutive valid rolling
  5-minute evaluations (each with at least 20 Storefront requests);
- any customer error occurs during the interruption interval;
- Pending/FailedScheduling is sustained beyond the approved provisioning
  allowance or affects an SLO;
- Karpenter does not create required replacement capacity;
- a new OOMKilled event, material restart/throttling regression, or node pressure
  affects serving capacity;
- a PDB or eviction removes required serving capacity;
- ResourceQuota prevents HPA or replacement scheduling;
- an ARM64 workload reports an exec-format/startup/readiness failure;
- observability loses required Locust, Kubernetes, Karpenter, or SLO signals;
- a critical workload does not recover; or
- the approved On-Demand reliability floor is no longer healthy.

Record `STOP_TIMESTAMP_UTC`, the triggering metric/event, operator, rollback
action, and post-rollback smoke-test result. A run stopped by a hard gate is a
FAIL and must not be used for the optimization comparison.

Rollback means restoring the reviewed previous-known-good Git/Terraform
revision and approved On-Demand workload placement, then verifying workers,
critical replicas, observability, and Browse/Cart/Checkout smoke tests. This
contract does not require a separate rollback drill; it requires the revision,
owner, and recovery steps to be recorded before execution.

## 10. Screenshot and video checkpoints

Use UTC on every dashboard and keep a visible clock or terminal timestamp in
each capture.

| Checkpoint | Relative time | Required evidence |
|---|---:|---|
| Pre-flight | Before `T+00:00` | Run fields, Git SHA/image digest, nodes, NodeClaims, HPA, pods, ResourceQuota |
| Low baseline | `T+04:00`–`T+05:00` | Active users/RPS, node count, replicas, SLO panels |
| Ramp-up | About `T+07:30` | Rising users, HPA response, Pending pods, NodeClaim launch |
| Peak settled | `T+12:00`–`T+15:00` | 200 users, RPS, peak node count, workload placement, SLO panels |
| Pre-interruption | Immediately before drill | Spot identity, workloads on node, cumulative request/failure counters; do not reset Locust |
| During interruption | Continuous video or captures at event time | Termination/NotReady, eviction, PDB, reschedule, replacement, live traffic and SLO |
| Post-interruption | After recovery, still at peak | Replacement Ready, request deltas, raw error counts, Storefront p95 |
| Ramp-down | About `T+27:30` | Falling users, HPA replicas, node count |
| Consolidation | On each peak-only termination | NodeClaim deletion/EC2 termination and continuous SLO |
| Final rest | At exit gate | 25 users, final node count, HPA, zero material regression, final SLO |
| EC2 Instances | Pre-flight, peak, interruption, final rest | Lifecycle, instance ID, instance type, architecture, launch time, termination/state, and Purchase Option |
| Cost Explorer — Purchase Option | After billing data is available | EC2 Compute `Usage quantity`, exact run date/window noted, grouped by Purchase Option; separate On-Demand and Spot |
| Cost Explorer — Instance Type | After billing data is available | EC2 Compute `Usage quantity`, same filters/window, grouped by Instance Type; identify Graviton usage |

Cost Explorer is delayed evidence and does not replace timestamp-derived
node-hours. Use Usage Quantity, not USD Cost, as the primary console evidence.
If Cost Explorer cannot isolate the exact sub-day run, retain the hourly/daily
view as corroboration and use the EC2/NodeClaim lifecycle calculation for the
run verdict.

Store raw outputs and images under a run-specific directory:

```text
docs/evidence/epic-09-compute-cost-optimization/runtime/<baseline|optimized>-<YYYYMMDDTHHMMSSZ>/
```

## 11. Pre-flight and terminal evidence commands

Run these read-only commands from a terminal configured for the target cluster.
They produce a compact screen suitable for the pre-flight screenshot:

```bash
export NAMESPACE=techx-tf4
date -u +"CAPTURE_TIMESTAMP_UTC=%Y-%m-%dT%H:%M:%SZ"
printf 'GIT_SHA=' && git rev-parse HEAD
kubectl config current-context
kubectl get nodes -L karpenter.sh/capacity-type,kubernetes.io/arch,node.kubernetes.io/instance-type
kubectl get nodeclaims -o wide
kubectl get hpa -n "$NAMESPACE"
kubectl get resourcequota -n "$NAMESPACE"
kubectl get pods -n "$NAMESPACE" -o wide
```

Immediately before the interruption, capture the selected node and its workload:

```bash
export SPOT_NODE='<spot-kubernetes-node-name>'
date -u +"PRE_INTERRUPTION_TIMESTAMP_UTC=%Y-%m-%dT%H:%M:%SZ"
kubectl get node "$SPOT_NODE" -o wide
kubectl get node "$SPOT_NODE" -o jsonpath='{.metadata.labels.karpenter\.sh/capacity-type}{"\n"}{.metadata.labels.kubernetes\.io/arch}{"\n"}{.metadata.labels.node\.kubernetes\.io/instance-type}{"\n"}'
kubectl get pods -A --field-selector spec.nodeName="$SPOT_NODE" -o wide
kubectl get nodeclaims -o wide
```

During the drill, keep this read-only watch visible while Locust and Grafana are
recorded separately:

```bash
kubectl get nodes,nodeclaims,pods -A -o wide --watch
```

After recovery, capture the UTC-aligned replacement state:

```bash
date -u +"POST_INTERRUPTION_TIMESTAMP_UTC=%Y-%m-%dT%H:%M:%SZ"
kubectl get nodes -L karpenter.sh/capacity-type,kubernetes.io/arch,node.kubernetes.io/instance-type
kubectl get nodeclaims -o wide
kubectl get pods -n techx-tf4 -o wide
kubectl get events -n techx-tf4 --sort-by='.metadata.creationTimestamp' | tail -n 80
```

These commands prove cluster state only. Locust CSV/HTML and Grafana captures
remain mandatory evidence for request denominators, raw errors, and SLOs.

## 12. Acceptance checklist

- [x] Contract includes low, ramp-up, peak, ramp-down, and low observation.
- [x] Baseline and optimized runs use one immutable profile.
- [x] Traffic remains continuous during the interruption drill.
- [x] Request denominator and raw error-count rules are defined.
- [x] Hard stop and rollback conditions are defined.
- [x] Exact UTC run fields, phase offsets, interruption time, and observation
  period are defined.
- [x] Worker node-hour, reduction, Spot ratio, and Graviton serving rules are
  defined.
- [x] EC2 lifecycle and Cost Explorer Usage Quantity checkpoints are defined.
- [x] Interruption uses cumulative pre/post counters and remains in the optimized
  denominator.
- [ ] Baseline runtime fields and artifacts populated after execution.
- [ ] Optimized runtime fields and artifacts populated after execution.
- [ ] Reviewer confirms comparable request volume and final PASS/FAIL verdict.
