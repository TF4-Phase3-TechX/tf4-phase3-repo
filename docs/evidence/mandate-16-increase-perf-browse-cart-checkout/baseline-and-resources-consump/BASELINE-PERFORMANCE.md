# C0G-88 — Baseline p95/p99 và Resource Consumption

**Baseline source:** [200-user run](runs/baseline-200-users-20260718T1850Z/SUMMARY.md)  
**Verdict:** PARTIAL — đủ evidence để xác định performance baseline và critical path; chưa phải final acceptance run vì duration thực tế là 40m48s thay vì strict planned 15 phút, và resource evidence là post-window snapshot.

## Measurement window

| Field | Value |
|---|---|
| T0 | 2026-07-18T18:50:45Z |
| T1 | 2026-07-18T19:31:33Z |
| Peak users | 200 |
| Spawn rate | 3.33 users/s |
| Duration thực tế | 40 phút 48 giây |
| Current post-run Locust state | 10 actual users |

## Latency baseline từ Locust

| Flow | Requests | Failures | p50 | p95 | p99 | Average | Max |
|---|---:|---:|---:|---:|---:|---:|---:|
| Browse `GET /` | 3,894 | 1 | 17 ms | 310 ms | 520 ms | 55.45 ms | 797.65 ms |
| Cart read `GET /api/cart` | 10,918 | 0 | 10 ms | 290 ms | 500 ms | 44.10 ms | 998.80 ms |
| Cart write `POST /api/cart` | 21,505 | 0 | 14 ms | 99 ms | 320 ms | 29.80 ms | 998.38 ms |
| Checkout `POST /api/checkout` | 7,095 | 0 | 80 ms | 500 ms | 820 ms | 143.78 ms | 1,756.42 ms |

Raw client-side artifacts: [stats.csv](runs/baseline-200-users-20260718T1850Z/locust/stats.csv), [failures.csv](runs/baseline-200-users-20260718T1850Z/locust/failures.csv), [exceptions.csv](runs/baseline-200-users-20260718T1850Z/locust/exceptions.csv), [report.html](runs/baseline-200-users-20260718T1850Z/locust/report.html).

## Trace baseline

| Trace | Evidence | Critical path |
|---|---|---|
| Representative Checkout | [`0606c19c958648f9a92402a763394dc2`](runs/baseline-200-users-20260718T1850Z/traces/checkout-representative-0606c19c958648f9a92402a763394dc2.json) | `PlaceOrder` 62.533 ms; preparation 29.539 ms |
| Slow Checkout | [`c2d1f3c03b6abbf5ac625dd285e74bb3`](runs/baseline-200-users-20260718T1850Z/traces/checkout-slow-c2d1f3c03b6abbf5ac625dd285e74bb3.json) | `PlaceOrder` 1,008.567 ms; preparation 759.897 ms |
| Browse/Cart chain | [`2263a6ba4d50407067a0090ff6de4c76`](runs/baseline-200-users-20260718T1850Z/traces/browse-cart-2263a6ba4d50407067a0090ff6de4c76.json) | Captured in same T0–T1 Jaeger query window |

Selected slow trace shows preparation work dominates the Checkout path. This is evidence for investigation; it does not alone prove the root cause of aggregate p99.

## Resource baseline

Post-window Kubernetes evidence: [resources/](runs/baseline-200-users-20260718T1850Z/resources/).

- `nodes.txt`: node count and identity.
- `hpa.txt`: Checkout/Currency/Frontend replica policy and observed replica count.
- `pod-usage.txt`, `node-usage.txt`: CPU/memory snapshot.
- `pods.txt`, `events.txt`: restart, pod state and scheduling-event snapshot.

The captured files show the resource state immediately after T1. They are not peak time-series and therefore cannot establish node-hours, CPU throttling or peak consumption across the full run.

## C0G-88 checklist

| Requirement | Status |
|---|---|
| Exact UTC window | PASS |
| 200-user load evidence | PASS |
| Locust p95/p99 Browse/Cart/Checkout | PASS |
| Request denominator, failures, exceptions | PASS |
| Same-window Jaeger trace IDs | PASS |
| Resource snapshot | PASS |
| Grafana + Jaeger exact same window | PARTIAL — Jaeger exact window available; Grafana capture missing |
| Strict sustained-load contract / exact 15 minutes | FAIL — actual run lasted 40m48s |
| Node-hours, throttling, peak resource time-series | PARTIAL — requires Grafana/Kubernetes time-series rerun |

Before declaring Directive #16 acceptance, repeat using the approved warm-up/ramp/sustained/stability contract and capture Grafana resource/latency panels for the exact same T0–T1 window.
