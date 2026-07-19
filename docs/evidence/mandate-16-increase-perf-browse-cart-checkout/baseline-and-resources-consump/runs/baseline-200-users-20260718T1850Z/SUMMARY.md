# Baseline — 200 users

## Window

| Field | Value |
|---|---|
| T0 UTC | 2026-07-18T18:50:45Z |
| T1 UTC | 2026-07-18T19:31:33Z |
| Observed duration | 40 phút 48 giây |
| Requested load | 200 users, spawn rate 3.33 |
| Post-capture state | Locust đã stop rồi được đưa về 10 actual users |

> Window dài hơn planned 15 phút vì capture T1 diễn ra sau khi 15-minute threshold đã qua. Tài liệu này không được gọi là strict 15-minute contract run; dùng làm 200-user baseline evidence và phải rerun exact contract trước acceptance final.

## Locust snapshot tại T1

| Route | Requests | Failures | p50 | p95 | p99 | Average | Max |
|---|---:|---:|---:|---:|---:|---:|---:|
| Browse `GET /` | 3,894 | 1 | 17 ms | 310 ms | 520 ms | 55.45 ms | 797.65 ms |
| Cart `GET /api/cart` | 10,918 | 0 | 10 ms | 290 ms | 500 ms | 44.10 ms | 998.80 ms |
| Cart `POST /api/cart` | 21,505 | 0 | 14 ms | 99 ms | 320 ms | 29.80 ms | 998.38 ms |
| Checkout `POST /api/checkout` | 7,095 | 0 | 80 ms | 500 ms | 820 ms | 143.78 ms | 1,756.42 ms |

`failures.csv` contains four cumulative historical 503s: one pre-window `GET /`, and three requests near/after T1 while the swarm was being reduced. `exceptions.csv` has only its header. No Checkout failure is recorded in the T1 Locust aggregate.

## Jaeger evidence in exact T0–T1 window

| Evidence | Trace ID | Detail |
|---|---|---|
| Representative Checkout | `0606c19c958648f9a92402a763394dc2` | 49 spans; `PlaceOrder` 62.533 ms; preparation 29.539 ms |
| Slow Checkout | `c2d1f3c03b6abbf5ac625dd285e74bb3` | 57 spans; `PlaceOrder` 1,008.567 ms; preparation 759.897 ms |
| Browse/Cart chain | `2263a6ba4d50407067a0090ff6de4c76` | Frontend trace captured in the same Jaeger window |

## Files

- `locust/stats.csv` — aggregate client-side result at T1.
- `locust/failures.csv`, `locust/exceptions.csv`, `locust/report.html`, `locust/stats-live.json`.
- `traces/checkout-representative-*.json`, `traces/checkout-slow-*.json`, `traces/browse-cart-*.json`.
- `resources/nodes.txt`, `hpa.txt`, `pods.txt`, `node-usage.txt`, `pod-usage.txt`, `events.txt` — Kubernetes snapshot captured directly after T1.

## Resource evidence limitation

Resource snapshots are post-window captures rather than peak time-series. They record current nodes/HPA/pods/CPU/memory/events but cannot prove resource maxima or node-hours across the entire T0–T1 period. Grafana resource time-series remains required for final acceptance comparison.
