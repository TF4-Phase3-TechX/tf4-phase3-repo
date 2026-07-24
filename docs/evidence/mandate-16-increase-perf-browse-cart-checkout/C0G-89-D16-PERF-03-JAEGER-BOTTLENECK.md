# C0G-89 — D16-PERF-03: Jaeger metric observation

**Jira:** `C0G-89` — `[D16-PERF-03] Identify Critical-Path Latency Bottleneck with Jaeger`  
**Evidence status:** Captured; trace-level bottleneck is not established by this metrics-only refresh.

## Scope and provenance

This replaces the removed stale 2026-07-18 Locust/trace baseline with Jaeger span-metric evidence for the following historical Grafana range:

- **Dashboard-local (ICT, UTC+07:00):** `2026-07-23 11:03:00`–`11:18:00`
- **UTC:** `2026-07-23T04:03:00Z`–`2026-07-23T04:18:00Z`
- **Dashboard:** [Flash Sale Verification Dashboard](http://localhost:13000/grafana/d/flash-sale-verification/flash-sale-verification-dashboard?orgId=1&from=2026-07-23T04%3A03%3A00.000Z&to=2026-07-23T04%3A18%3A00.000Z&timezone=browser)
- **Dashboard image:** [`grafana/flash-sale-verification-20260723T0403Z-0418Z.png`](grafana/flash-sale-verification-20260723T0403Z-0418Z.png)
- **Raw metrics:** [`jaeger/span-metrics-20260723T0403Z-0418Z.json`](jaeger/span-metrics-20260723T0403Z-0418Z.json)
- **Locust run evidence:** [`locust/Locust-20260723T040040Z-041540Z.html`](locust/Locust-20260723T040040Z-041540Z.html), `2026-07-23T04:00:40Z`–`04:15:40Z` (15 minutes; SHA-256 `6bb44957a89015961057cdc693cbd4df472640050de6d714a6b53956abe63559`)
- **Trace selection and exports:** [`jaeger/checkout-trace-selection-20260723T040040Z-041540Z.md`](jaeger/checkout-trace-selection-20260723T040040Z-041540Z.md)

The Locust report overlaps, but is not identical to, the Grafana metric interval (`04:03:00Z`–`04:18:00Z`); this document does not treat them as one exact acceptance window.

All latency values below are **Jaeger-derived server/internal span metrics in milliseconds**, not Locust client percentiles. Each point is:

```promql
histogram_quantile(q, sum by (le) (rate(traces_span_metrics_duration_milliseconds_bucket{...}[5m])))
```

The query range contains 61 points at a 15-second step. Each value is a rolling five-minute estimate; therefore the first points include observations as early as `2026-07-23T03:58:00Z`.

## Observed span metrics

| Scope / labels | p50 range | p95 range | p99 range | Peak observation |
|---|---:|---:|---:|---|
| Frontend browse server spans: `GET /`, `GET /product.*`, `GET /api/products.*`, `GET /api/data.*` | 39.6–128.8ms | 329.1–1,701.7ms | 659.7–3,639.2ms | p99 **3,639.2ms** |
| Frontend cart server spans: `(GET\|POST\|DELETE) /api/cart` | 48.5–180.1ms | 315.4–1,598.6ms | 567.8–1,979.4ms | p99 **1,979.4ms** |
| Frontend checkout server span: `POST /api/checkout` | 303.9–553.4ms | 896.1–3,815.3ms | 1,143.3–4,848.0ms | p99 **4,848.0ms** |
| Checkout server span: `oteldemo.CheckoutService/PlaceOrder` | 129.8–245.2ms | 399.6–965.5ms | 719.3–2,309.9ms | p99 **2,309.9ms** |
| Checkout internal span: `prepareOrderItemsAndShippingQuoteFromCart` | 42.1–70.0ms | 197.3–728.7ms | 503.3–1,427.8ms | p99 **1,427.8ms** |

The raw JSON records the exact PromQL, label filters, timestamps, and every returned point; the table only reports the minimum and maximum point in each 15-minute range.

## Narrow observation

`POST /api/checkout` had the highest observed p99 span-metric peak among the three frontend flow groups in this window (**4,848.0ms**). Its peak is higher than the matched checkout-service `PlaceOrder` p99 peak (**2,309.9ms**).

This identifies a latency concentration at the frontend checkout server-span boundary during the sampled period. It does **not** prove that the difference is queueing, frontend CPU, a particular downstream dependency, or a specific code path. The preparation span is present and has its own p99 peak (**1,427.8ms**), but span metrics do not expose parent/child timing for a single request.

## Trace-level critical path

The supplied Locust report proves a 15-minute load run from `2026-07-23T04:00:40Z` to `04:15:40Z`. It reports `POST /api/checkout` p95/p99 of **5,200ms / 6,200ms** over 3,195 requests, with 11 failures; this is run provenance, not a comparison to the removed baseline.

The trace selection exports include two successful `POST /api/checkout` requests from that run. The slow trace (`72708ed65492c14ff800826e3857eadf`, HTTP 200 and gRPC 0) establishes this parent/child path:

```text
frontend POST /api/checkout (1,086.296ms)
└─ checkout PlaceOrder server (979.617ms)
   └─ prepareOrderItemsAndShippingQuoteFromCart (949.506ms)
```

Preparation occupies **96.9%** of the slow trace's `PlaceOrder` server span (`949.506 / 979.617ms`). The same trace family has a representative success (`94c68de4ca5269a7a092129a71ed4be9`): frontend checkout 46.849ms, `PlaceOrder` 36.483ms, preparation 12.700ms. See the exported JSON and selection rationale in [`jaeger/checkout-trace-selection-20260723T040040Z-041540Z.md`](jaeger/checkout-trace-selection-20260723T040040Z-041540Z.md).

This establishes the trace-level bottleneck relationship for the selected slow successful checkout. It does not establish why preparation was slow, that it is slow for every checkout, or a code-level cause.

## Evidence limits

- The Grafana/Jaeger histograms aggregate spans; without the selected trace exports they cannot establish an individual trace critical path. The exports do not establish item count, database query count, retry, cache state, pool wait, serialization, or causality.
- Do not compare the Locust report or rolling span percentiles numerically with the removed Locust baseline, and do not use them as a Mandate 16 acceptance or before/after performance verdict.
- The Locust run and Grafana metric ranges overlap but differ; no exact cross-source client/metric correlation is claimed.
- No resource, HPA, Kubernetes, or load-generator configuration evidence was collected for this refresh, by request.

## Acceptance checklist

- [x] Exact Grafana window and timezone recorded.
- [x] Jaeger span-metric queries and raw returned values preserved.
- [x] Dashboard image captured for the requested range.
- [x] Stale Locust, trace, and resource baseline evidence removed.
- [x] Trace-level critical-path bottleneck established — representative Jaeger trace exports preserved.
- [ ] Tech Lead review completed.

## Known out-of-scope references

The requested deletion leaves historical label-evidence paths in the following AIOps calibration files. They were intentionally not changed because they are outside this refresh scope:

- `docs/aiops/evidence/production-informed-calibration.json`
- `docs/aiops/evidence/tf4-prometheus-labelled-windows-20260721.json`
- `techx-corp-platform/src/aiops/benchmark/prometheus-calibration-job.yaml`
