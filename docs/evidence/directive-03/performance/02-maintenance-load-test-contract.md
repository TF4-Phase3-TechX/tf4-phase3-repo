# D3-PERF-02 — Maintenance Load Profile and Test Contract

**Directive:** #3 — Maintenance Capacity & Cost-Efficient Resilience

**Owner:** D3-PERF-02 owner (single-owner execution)

**Cluster:** `techx-tf4-cluster`

**Application namespace:** `techx-tf4`

**Approved harness:** in-cluster `Deployment/load-generator`, Locust headless

**Contract status:** Contract complete — execution gated.

---

## 1. Purpose and pass contract

This contract creates continuous Browse, Cart, and Checkout traffic while one
approved maintenance action is performed. It is intended to distinguish a
zero-downtime maintenance result from a test that merely had too little traffic
to observe an outage.

A run passes only when all of the following are true:

1. The planned traffic shape completes and each flow passes its volume guard.
2. Browse and Cart success are each at least `99.5%`.
3. Checkout success is at least `99.0%`.
4. Storefront p95 is below `1000ms` for the full steady-state window and does
   not breach the stop condition during maintenance.
5. There is no new OOMKilled termination, CrashLoopBackOff, unexplained restart,
   prolonged Pending pod, or NodePressure condition.
6. The maintenance action and Kubernetes events are timestamped in UTC.
7. The complete raw Locust artifact set is retained.

Passing percentages without the volume guards is **not** a pass.

## 2. Approved maintenance window gate

The operator must fill this table before starting Locust. Relative or recurring
windows such as “tomorrow morning” are invalid.

| Field | Required value |
|---|---|
| Change ticket | `<CHG_ID>` |
| Approver | `<NAME_OR_ROLE>` |
| Absolute UTC window start | `<YYYY-MM-DDTHH:MM:SSZ>` |
| Absolute UTC window end | `<YYYY-MM-DDTHH:MM:SSZ>` |
| Local ICT display | `<YYYY-MM-DD HH:MM–HH:MM ICT>` |
| Maintenance action | Exactly one: `node drain` or `rolling restart` |
| Target | `<NODE_NAME>` or `<DEPLOYMENT_NAME>` |
| Rollback owner/command | `<OWNER>` / `<EXACT_COMMAND>` |

Gate rules:

- The UTC window must be at least 25 minutes and no more than 45 minutes.
- `TEST_T0` must fall inside the approved window with at least 20 minutes left.
- The owner announces `TEST_T0`, planned `MAINTENANCE_TS`, target, and rollback
  command before starting traffic.
- If any field is missing, the verdict is `NOT RUN — WINDOW NOT APPROVED`.

## 3. Load profile

| Phase | Relative time | Duration | Target users | Spawn/stop rate |
|---|---:|---:|---:|---:|
| Ramp-up | `T+00:00` | 60s | 0 → 200 | `3.34 users/s` |
| Pre-maintenance steady | `T+01:00` | 5m | 200 | hold |
| Maintenance action | `T+06:00` | timestamped event | 200 | hold |
| Post-action steady | `T+06:00` | 10m | 200 | hold |
| Ramp-down | `T+16:00` | 20s | 200 → 0 | `10 users/s` |
| End | `T+16:20` | — | 0 | stopped |

Concrete timestamp derivation:

```text
TEST_T0              = actual Locust start in UTC
RAMP_COMPLETE_TS     = TEST_T0 + 00:01:00
MAINTENANCE_TS       = TEST_T0 + 00:06:00
RAMP_DOWN_START_TS   = TEST_T0 + 00:16:00
TEST_END_TS          = TEST_T0 + 00:16:20
```

The maintenance command must not be issued early. Record both the planned and
actual action timestamps. Clock skew greater than five seconds between operator
host and UTC is a pre-test failure.

## 4. Traffic mix

The maintenance profile evaluates these scoped flow weights:

| Flow | Weight | Share of scoped tasks | Representative operations |
|---|---:|---:|---|
| Browse | 10 | 58.8% | home/product list and product-detail reads |
| Cart | 5 | 29.4% | view cart and add item |
| Checkout | 2 | 11.8% | single-item and multi-item checkout |
| **Total** | **17** | **100%** | — |

The Locust implementation may also call supporting endpoints such as
recommendations, reviews, ads, payment, shipping, currency, email and Kafka as
part of these customer journeys. Those calls do not replace the three scoped
flow counters.

The operator must verify the rendered Locust task weights before the official
run. Any change to weights, wait time, host, user count or duration creates a
new contract revision and requires review.

## 5. Volume guards

Volume is evaluated over the 15-minute steady-state interval, excluding the
first ramp minute and final ramp-down.

| Flow | Minimum completed requests | Reason |
|---|---:|---|
| Browse | `1,000` | More than enough to evaluate a 0.5% error budget |
| Cart | `500` | At least 2.5× the 200-request minimum for 0.5% resolution |
| Checkout | `200` | At least 2× the 100-request minimum for 1% resolution |
| All scoped flows | `1,700` | Prevents a nominal pass with negligible traffic |

Additional guards:

- Every scoped flow must record traffic before, during, and after the actual
  maintenance timestamp.
- Each flow must have at least 20 completed requests in the two-minute window
  centered on `MAINTENANCE_TS`.
- Missing Locust rows, zero requests, or fallback to the aggregate `Total` row
  is a test-contract failure, not a successful SLO result.
- If the volume guard fails without a safety stop, the run is `INVALID` and may
  be rerun; user count must not be increased ad hoc inside the same window.

## 6. Pre-declared SLO and stop conditions

### 6.1 SLO evaluation thresholds

| Flow | Success SLO | Latency SLO |
|---|---:|---:|
| Browse | `>= 99.5%` | Storefront p95 `< 1000ms` |
| Cart | `>= 99.5%` | Storefront p95 `< 1000ms` |
| Checkout | `>= 99.0%` | Storefront p95 `< 1000ms`; retain checkout-specific p95/p99 |

### 6.2 Automatic or operator stop triggers

Stop immediately, abort the maintenance action when still safe, and execute the
documented recovery command if any condition is true:

| Category | Stop condition |
|---|---|
| Error rate | Browse or Cart error rate `> 0.5%`, or Checkout `> 1.0%`, in two consecutive 1-minute windows; immediate stop if any flow reaches `>= 5%` in one minute |
| p95 latency | Storefront p95 `>= 1000ms` for two consecutive 1-minute windows; immediate stop at `>= 2000ms` in one minute |
| OOM/restart | Any new `OOMKilled`; any new CrashLoopBackOff; any application container restart delta `> 0` unless explicitly expected and recorded for the target rolling restart |
| Pending pod | Any revenue-path pod Pending for `> 60s`; immediate stop if a revenue service has zero Ready endpoints |
| Node pressure | `MemoryPressure`, `DiskPressure`, or `PIDPressure=True`; node CPU `>= 90%` or memory `>= 85%` for 5 minutes |
| HPA | Frontend or Checkout HPA target becomes `<unknown>` for more than 2 minutes |
| Harness | Load-generator pod restart/OOM, loss of its only Ready replica, duplicate Locust process, or missing stats updates for 60s |
| Maintenance | Drain/rollout exceeds its approved timeout or rollback precondition becomes true |

The test does not “wait out” an SLO breach to obtain a better final average.
The raw partial artifacts are retained with verdict `STOPPED`.

## 7. Single approved harness guard

Only the existing in-cluster `Deployment/load-generator` may generate traffic.
Before the run:

```bash
kubectl -n techx-tf4 get deploy load-generator
kubectl -n techx-tf4 get pods -l app.kubernetes.io/name=load-generator
kubectl -n techx-tf4 exec deploy/load-generator -- pgrep -af locust
```

Required state:

- Exactly one Ready load-generator pod.
- `LOCUST_AUTOSTART=false` at deployment baseline.
- No active Locust swarm/process except the idle service process documented by
  the image entrypoint.
- No local Locust, CI load job, browser automation traffic, or second Kubernetes
  Job/Pod targeting the storefront.

If process inspection is not permitted, the operator must use deployment logs,
Locust state and request-rate baseline to prove zero active users before start.

## 8. Pre-test checklist

- [ ] Approved window table is complete and expressed in absolute UTC.
- [ ] Maintenance target, safety timeout and rollback command are reviewed.
- [ ] All application and observability pods are Running/Ready; completed Jobs are excluded.
- [ ] Pending pods = 0 and CrashLoopBackOff pods = 0.
- [ ] Baseline restart and OOM counters are captured.
- [ ] All worker nodes are Ready with no pressure condition.
- [ ] Frontend and Checkout HPA return valid CPU metrics.
- [ ] Revenue-path Services have Ready endpoints.
- [ ] Prometheus/Grafana and Metrics API are queryable.
- [ ] Exactly one approved load harness exists and it has zero active users.
- [ ] Artifact directory exists and is writable.
- [ ] Operator clock is synchronized; `TEST_T0` is announced.

Failure of any checklist item prevents test start.

## 9. Execution command

The maintenance wrapper is the approved entry point. It creates the complete
artifact tree, captures preflight state, rejects missing execution-gate fields
or missing `pods/exec`, and delegates to the Task-4 harness, which enforces the same
`200 users / 60s ramp / 15m steady / 20s ramp-down` profile:

```bash
export RUN_ID="maint-$(date -u +%Y%m%dT%H%M%SZ)"
export NAMESPACE=techx-tf4
export USERS=200
export SPAWN=3.34
export RAMP_UP=1m
export STEADY_STATE=15m
export RAMP_DOWN=20s
export TOTAL_RUNTIME=16m20s
export CHANGE_TICKET="CHG-REPLACE-ME"
export APPROVER="REPLACE-ME"
export WINDOW_START_UTC="2026-07-16T00:00:00Z"
export WINDOW_END_UTC="2026-07-16T00:30:00Z"
export MAINTENANCE_ACTION="rolling restart"
export MAINTENANCE_TARGET="deployment/frontend"
export MAINTENANCE_COMMAND="kubectl -n techx-tf4 rollout restart deployment/frontend"
export ROLLBACK_OWNER="REPLACE-ME"
export ROLLBACK_COMMAND="kubectl -n techx-tf4 rollout undo deployment/frontend"

bash scripts/run-maintenance-load-test.sh full
```

Replace every placeholder and UTC value with approved values. The wrapper does
not execute the maintenance command automatically. In a second operator
terminal, wait until the planned `TEST_T0 + 00:06:00`, record UTC immediately
before and after the command, then run only the approved command:

```bash
date -u +%Y-%m-%dT%H:%M:%SZ
kubectl -n techx-tf4 rollout restart deployment/frontend
kubectl -n techx-tf4 rollout status deployment/frontend --timeout=5m
date -u +%Y-%m-%dT%H:%M:%SZ
```

For an approved node drain, replace the example with the exact reviewed
cordon/drain and recovery commands. Never copy the deployment example onto a
node-drain ticket.

Read-only gate check (never starts Locust or maintenance):

```bash
bash scripts/run-maintenance-load-test.sh preflight
```

The reviewed script honors these environment values. `SPAWN=3.34` reaches 200
users in approximately 60 seconds. Do not manually start a second Locust
process as a workaround.

At `TEST_T0 + 00:06:00`, execute exactly the approved maintenance command and
record the command, start timestamp, completion timestamp and exit code.

## 10. Raw artifact contract

Official output root:

```text
docs/evidence/directive-03/performance/runs/<RUN_ID>/
```

Required files:

```text
metadata.env
timeline.csv
maintenance-command.txt
rollback-command.txt
preflight/
  pods.txt
  deployments.txt
  nodes.txt
  node-conditions.txt
  hpa.txt
  endpoints.txt
  resource-usage.txt
raw-locust/
  task4-full-stats.csv
  task4-full-stats-history.csv
  task4-full-failures.csv
  task4-full-exceptions.csv
  task4-full-report.html
runtime/
  pod-state-during.txt
  events-during.txt
  node-state-during.txt
  pod-state-after.txt
  events-after.txt
  restart-oom-delta.txt
dashboard/
  before.png
  during-maintenance.png
  after.png
verdict.md
```

`metadata.env` must contain cluster, namespace, Git SHA, Helm revisions, Locust
image digest, exact UTC window, actual timestamps, users, spawn rate, traffic
weights, target and change ticket. CSV and HTML files must be copied unchanged
from the load-generator pod; summaries never replace raw artifacts.

## 11. Rerun runbook

### 11.1 Safety-stop rerun

1. Stop Locust and confirm active users reach zero.
2. Stop/rollback the maintenance action according to the approved runbook.
3. Wait until every application and observability workload is Ready.
4. Confirm no new restart/OOM/Pending/NodePressure condition is still active.
5. Preserve the failed run directory; never overwrite it.
6. Identify and remediate the cause, then obtain a new change approval/window.
7. Create a new `RUN_ID`; rerun the full profile from ramp-up. Do not resume at
   the failed phase.

### 11.2 Invalid-volume rerun

If all safety conditions stayed healthy but a volume guard failed:

1. Mark the original run `INVALID — INSUFFICIENT VOLUME`.
2. Verify task weights, Locust failures, wait time and stats row names.
3. Do not silently raise users. Any change to user count, weights or duration
   requires a new contract revision and capacity review.
4. Obtain a new absolute window and rerun with a new `RUN_ID`.

### 11.3 Cleanup verification

After every pass, fail or invalid run:

```bash
kubectl -n techx-tf4 get pods
kubectl -n techx-tf4 get hpa
kubectl get nodes
kubectl -n techx-tf4 get events --sort-by=.lastTimestamp
```

Confirm the load generator has zero active users and no second harness remains.

## 12. Final verdict template

```text
RUN_ID:
CHANGE_TICKET:
APPROVED_UTC_WINDOW:
ACTUAL_TEST_T0:
ACTUAL_MAINTENANCE_TS:
MAINTENANCE_COMPLETED_TS:
ACTUAL_TEST_END:
ACTION/TARGET:

BROWSE_REQUESTS / SUCCESS / P95:
CART_REQUESTS / SUCCESS / P95:
CHECKOUT_REQUESTS / SUCCESS / P95:
REQUESTS AROUND MAINTENANCE PER FLOW:

PENDING DELTA:
RESTART DELTA:
OOM DELTA:
NODE PRESSURE:
HPA METRICS:
ROLLBACK USED/TESTED:
RAW ARTIFACT PATH:

VERDICT: PASS | FAIL | STOPPED | INVALID | NOT RUN
OWNER SIGN-OFF:
```

The owner may self-verify rollout, performance and runtime evidence, but must
label it `single-owner execution` rather than attributing checks to named
supporters who did not participate.

## 13. Latest live execution-gate evidence

Read-only preflight `maint-20260715T172819Z` was collected on
`2026-07-15T17:28:49Z` against context `d5-perf05`. Revenue-path remediation is
live: Cart, Checkout, Frontend, Frontend Proxy, Payment, Product Catalog, Quote,
Shipping and Currency each reported `2/2` deployment replicas and two Ready
EndpointSlice addresses. Frontend, Checkout and Currency HPA metrics were
valid; all nine PDBs reported one allowed disruption; all observed pods were
Running/Ready with zero restarts; node utilization was below the declared stop
thresholds.

The official load and maintenance action were **not run**. The execution gate
failed because the change ticket, approver, absolute UTC window, action/target,
rollback owner and exact rollback command were not provided. The active IAM
identity also returned `no` for `create pods/exec`, so it cannot verify the
Locust process list, start the approved headless harness, or copy raw artifacts.
No second load process was started.

Raw preflight and gate result:
`docs/evidence/directive-03/performance/runs/maint-20260715T172819Z/`.

**Current verdict: Contract complete — execution gated.**
