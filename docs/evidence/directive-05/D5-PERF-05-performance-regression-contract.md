# D5-PERF-05 — Post-Enforcement Performance Regression Contract

## Purpose and entry gate

This test proves that resource remediation plus admission enforcement does not
regress Browse, Cart, Checkout, Kubernetes scheduling, or autoscaling. It is not
an enforcement test and must not be used to compensate for an incomplete
D5-PERF-03 rollout.

An official run may start only when all gates below have evidence links:

1. D5-PERF-03 has a `PASS` final verdict for every applicable rollout wave.
2. Security confirms the resource requests/limits policy is in `enforce` for
   `techx-tf4`; a compliant manifest passes and a missing-resource manifest is
   rejected.
3. All current application pods are Ready with no Pending/CrashLoop pod and no
   unresolved OOM incident.
4. Every HPA target has CPU requests and reports valid current/target metrics.
5. A pre-remediation baseline exists for the same load profile, duration,
   traffic mix and dashboard queries.
6. The UTC change window and operator are approved before traffic starts.

If any gate fails, create `precheck-verdict.md` and do not start Locust.

## Immutable load profile

Use the repository-approved Locust UI harness only. Do not run
`run-load-test-task4.sh`, a second Locust process, or an ad-hoc traffic tool in
parallel.

| Parameter | Contract |
|---|---|
| Concurrent users | 200 |
| Spawn rate | 3.34 users/s |
| Ramp-up | 60 seconds |
| Steady state | 15 minutes after reaching 200 users |
| Ramp-down | Operator Stop; maximum 20 seconds |
| Target | Internal `frontend-proxy:8080` through the approved load-generator |
| Flow mix | Same Browse/Cart/Checkout weights as the approved baseline |
| Window | Absolute UTC T0/T1 recorded in `metadata.md` |

The official run is invalid if the Locust shape, flow weights, target, feature
flags, replicas, or dashboard queries differ from the baseline without a
documented exception.

## Acceptance and comparison rules

| Signal | Pass rule |
|---|---|
| Storefront/Browse p95 | `< 1000 ms` and no material regression versus baseline |
| Browse success | Meets the approved baseline SLO and volume guard |
| Cart success | Meets the approved baseline SLO and volume guard |
| Checkout success | Meets the approved baseline SLO and volume guard |
| CPU throttling | No sustained material increase versus baseline; report per container and aggregate |
| OOM/restarts | No new OOMKilled event and no restart burst during T0–T1 |
| Pending | Zero Pending pods during T0–T1 and the surge exercise |
| HPA | Metrics are valid; observed replica/metric behavior is recorded |
| Scheduler | Node requested resources retain documented headroom |
| Surge pod | One approved rolling restart schedules and becomes Ready within rollout timeout |

“Material regression” must be fixed before T0. Recommended default when no ADR
defines it: more than 10% relative increase for p95 or throttling sustained for
five minutes. Both the absolute SLO and relative comparison must pass.

## Stop conditions

Stop Locust immediately and do not run the surge exercise when any condition is
observed:

- Storefront p95 is at least 1 second for five consecutive minutes.
- Browse, Cart, or Checkout breaches its approved error-rate SLO or fails its
  volume guard.
- Any new OOMKilled termination or restart burst occurs.
- Any application pod remains Pending or enters CrashLoopBackOff.
- Node MemoryPressure, DiskPressure or PIDPressure becomes true.
- CPU throttling crosses the pre-approved regression threshold for five
  minutes.
- HPA metrics become `unknown` or desired replicas cannot schedule.

Stop means: select **Stop** in the existing Locust UI, record UTC, capture the
same-window dashboards and pod events, and leave application resources
unchanged pending incident review.

## Surge scheduling exercise

After the steady-state SLO gates are healthy, restart only `frontend` within the
same approved window:

```powershell
kubectl -n techx-tf4 rollout restart deployment/frontend
kubectl -n techx-tf4 rollout status deployment/frontend --timeout=5m
kubectl -n techx-tf4 get pods -w
```

Record the old/new ReplicaSet, maximum simultaneous replicas, scheduling delay,
Pending duration and rollout result. Do not restart Browse, Cart and Checkout
services together. If the rollout fails, stop load and use the reviewed Helm
rollback revision; do not patch resources ad hoc.

## Required evidence layout

```text
docs/evidence/directive-05/official-<RUN_ID>/performance-regression/
├── metadata.md
├── precheck-verdict.md
├── comparison.md
├── raw/
│   ├── locust-stats.csv
│   ├── locust-stats-history.csv
│   ├── locust-failures.csv
│   ├── locust-exceptions.csv
│   ├── locust-report.html
│   ├── pods-before.yaml
│   ├── pods-after.yaml
│   ├── hpa-before.yaml
│   ├── hpa-after.yaml
│   ├── nodes-before.txt
│   ├── nodes-after.txt
│   ├── events.txt
│   └── surge-rollout.txt
└── dashboard/
    ├── 01-window-and-volume.png
    ├── 02-browse-cart-checkout-slo.png
    ├── 03-cpu-throttling.png
    ├── 04-memory-oom-restarts.png
    ├── 05-hpa.png
    └── 06-node-headroom-and-surge.png
```

Dashboard screenshots must use the same absolute UTC T0/T1 range. Raw Locust
CSV/HTML and dashboard screenshots are both mandatory; one does not replace the
other.

## Final verdict

`comparison.md` records baseline, post-enforcement value, absolute threshold,
relative delta, evidence path and PASS/FAIL for every acceptance signal. The
task is Done only when all rows pass and the admission/remediation evidence
links are valid.
