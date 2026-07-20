# D16-PERF-01 — Sustained-Load Contract and Tail-Latency Budget

**Status:** Proposed for approval before the strict baseline run  
**Owner:** CDO04  
**Applies to:** Browse → Cart → Checkout baseline and optimized runs  
**Rule:** The contract and budgets below are frozen before the optimized run. Any change invalidates comparability and requires both runs to be repeated.

## 1. Exact UTC windows

| Run | Warm-up | Ramp-up | Sustained measurement | Stability observation | Full run |
|---|---|---|---|---|---|
| Baseline | 2026-07-21 01:00–01:05Z | 01:05–01:10Z | 01:10–01:35Z | 01:35–01:45Z | 2026-07-21 01:00–01:45Z |
| Optimized | 2026-07-21 03:00–03:05Z | 03:05–03:10Z | 03:10–03:35Z | 03:35–03:45Z | 2026-07-21 03:00–03:45Z |

The test operator must record actual `T0` and `T1` in UTC. A start drift of at most five minutes is allowed only when every phase shifts by the same amount and the complete 45-minute schedule remains intact. A larger drift requires a new approved window. Warm-up data must not be included in the primary latency result.

## 2. Fixed load profile

| Phase | Virtual users | Spawn rate | Duration | Purpose |
|---|---:|---:|---:|---|
| Warm-up | 50 | 10 users/s from zero | 5 minutes | Warm runtime, connection pools and caches |
| Ramp-up | 50 → 200 | 5 users/s | 5 minutes | Observe latency while load increases |
| Sustained measurement | 200 | 0 after target is reached | 25 minutes | Primary p50/p95/p99 and resource window |
| Stability observation | 200 | 0 | 10 minutes | Detect jitter, queue growth and degradation |

Baseline and optimized runs must use the same Locust file Git SHA, load-generator image and limits, host, user classes, wait-time policy, test accounts and seeded catalog/cart data. Application Git SHA/image is expected to differ only by the reviewed optimization change and must be recorded for each run. No test parameters may be tuned between runs.

## 3. Endpoint mix and correctness

Use `WebsiteUser` from `techx-corp-platform/src/load-generator/locustfile.py` without changing its task weights. The frozen task-selection mix is:

| Group | Locust tasks and weights | Total weight | Selection share |
|---|---|---:|---:|
| Browse/Search | `index` (10), `browse_product_list` (8), `browse_product` (12), `get_recommendations` (8), `get_product_reviews` (6) | 44 | 43.56% |
| Cart | `view_cart` (12), `add_to_cart` (13) | 25 | 24.75% |
| Checkout | `checkout` (8), `checkout_multi` (7) | 15 | 14.85% |
| Navigation/AI | `ask_product_ai_assistant` (10), `get_ads` (6) | 16 | 15.84% |
| Feature-flag gated | `flood_home` (1) | 1 | 0.99% |

`loadGeneratorFloodHomepage` must remain unchanged and disabled, making `flood_home` a no-op in both runs. Selection share is based on the total weight of 101; it is not the final HTTP request share because Checkout and Cart tasks issue nested requests. The observed HTTP request mix must therefore be recorded by named route and compared under Section 4 rather than inferred from weights.

Report Browse as `GET /`, Cart as combined `GET /api/cart` and `POST /api/cart` plus both route-level rows, and Checkout as `POST /api/checkout`. Other workload routes remain enabled to preserve realistic contention but are not part of the frozen tail-latency budget. Random item counts, products, synthetic user IDs and `people.json` fixtures must come from the identical load-generator revision and configuration. Every response must pass the existing status and payload validations; a fast invalid response is a failure, not a latency sample for a successful request.

## 4. Request denominator and comparable-workload rule

The primary denominator is **successful requests completed during the 25-minute sustained measurement window**. Stability results use the subsequent 10-minute window and are reported separately. For each flow, retain total requests, successful requests, failures, timeouts, retries and Locust exceptions.

Runs are comparable only when all of the following are true:

- Same phase durations, peak users, spawn rates, endpoint mix, dataset and load-generator configuration.
- Same cluster capacity, instance classes, HPA policy, replica minimums and CPU/memory requests and limits.
- Total requests and per-flow request counts differ by no more than 5%.
- Observed per-route HTTP request share differs by no more than 2 percentage points between runs.
- Both runs contain the complete 25-minute measurement and 10-minute stability windows.
- The success denominator is stated explicitly for every percentile table.

If a tolerance is exceeded, do not normalize the headline percentiles; mark the comparison invalid and repeat both runs under the same contract.

## 5. Frozen tail-latency budget

Percentiles are calculated from successful client-observed requests in the sustained measurement window.

| Flow | p95 budget | p99 budget |
|---|---:|---:|
| Browse | < 500 ms | < 800 ms |
| Cart combined | < 700 ms | < 1,000 ms |
| Checkout | < 1,000 ms | < 1,500 ms |

The optimized run passes the latency gate only when:

1. Each flow stays below both its p95 and p99 budget.
2. Checkout p99, the selected primary critical path, improves by at least **20%** against the strict baseline: `(baseline p99 - optimized p99) / baseline p99 >= 0.20`.
3. Browse and Cart p99 do not regress by more than 5% or 25 ms, whichever allowance is smaller.
4. No flow's p95 regresses by more than 5% or 25 ms, whichever allowance is smaller.
5. During the stability window, each flow's p99 remains within 10% of its sustained-window p99 and does not show three consecutive five-minute buckets increasing by more than 10% bucket over bucket.

The historical 2026-07-18 run is diagnostic evidence only and is not the strict baseline denominator because its phase timing and resource time-series were incomplete.

## 6. Resource invariants

The optimized run is valid only when all invariants hold:

- Worker node-hours and peak worker node count are less than or equal to baseline.
- Cluster capacity and instance classes do not increase.
- HPA minimum replicas, HPA policy and maximums do not increase to obtain latency.
- Container CPU/memory requests and limits do not increase to obtain latency.
- Average CPU consumption increases by no more than 5%; peak CPU increases by no more than 10%.
- CPU seconds per successful request does not increase by more than 5%.
- Actual memory consumption does not increase by more than 5%, with no new OOMKilled or restart event.
- No sustained Pending/FailedScheduling, CPU throttling regression, connection-pool exhaustion or non-recovering queue buildup appears.

CPU, memory, replicas, nodes and queue/pool signals must be captured as time series over the exact sustained and stability windows. Post-run snapshots alone are insufficient.

## 7. Stop conditions

Stop the run and mark it invalid if any of these occurs:

- Browse, Cart or Checkout correctness validation fails.
- HTTP 5xx, timeouts, connection resets or retries materially increase above baseline, or success rate falls below 99.5%.
- Any rolling five-minute p95 or p99 exceeds twice its budget for two consecutive buckets.
- Sustained pool exhaustion, unrecoverable queue growth, new OOMKilled, or Pending/FailedScheduling lasts more than five minutes.
- Node count, capacity, HPA floor, requests/limits, endpoint mix or load is changed outside this contract.
- Jaeger, Grafana or Locust loses signal for more than two consecutive minutes in the measurement window.
- flagd, tracing, logging, validation, retry or reliability controls are disabled or changed.

An optimized run that triggers a stop condition must not be promoted. Follow the approved rollback plan, restore the known-good Git SHA/image through the source of truth, and run the Browse → Cart → Checkout smoke test.

## 8. Required evidence per run

- Actual UTC timestamps for every phase and the Git SHA/image versions under test.
- Locust raw statistics, failures, exceptions and HTML report, sliced by measurement and stability windows.
- p50/p95/p99 and five-minute p99 series for Browse, Cart read/write, Cart combined and Checkout.
- Representative and slow Jaeger traces from the exact window, including the slowest span and downstream contribution.
- Grafana exports/screenshots for CPU, memory, throttling, replicas, nodes, pool/queue signals, restarts and scheduling state.
- Worker node-hours, peak node count, CPU seconds and CPU seconds per successful request.
- Correctness results and request-volume/mix comparison.

## 9. Pre-run approval record

Complete this block before starting the baseline window. Empty required fields mean the contract is not approved.

```text
CHANGE_TICKET=D16-PERF-01
WINDOW_START_UTC=2026-07-21T01:00:00Z
WINDOW_END_UTC=2026-07-21T03:45:00Z
BASELINE_WINDOW=2026-07-21T01:00:00Z/2026-07-21T01:45:00Z
OPTIMIZED_WINDOW=2026-07-21T03:00:00Z/2026-07-21T03:45:00Z
REVIEWED_GIT_SHA=
APPLICATION_OWNER=
PLATFORM_SYNC_OWNER=
TEST_OPERATOR=
ROLLBACK_OWNER=
INCIDENT_CHANNEL=
APPROVED_BY=
APPROVED_AT_UTC=
```

## 10. Acceptance mapping

| Acceptance criterion | Contract section |
|---|---|
| Warm-up separate from measurement | Sections 1–2 |
| Sustained load at least 20 minutes | Section 2: 25 minutes |
| p95/p99 budgets for all three flows | Section 5 |
| p99 improvement target | Section 5: Checkout ≥20% |
| Comparable workload rule | Sections 3–4 |
| Resource invariants | Section 6 |
| Stop conditions | Section 7 |
| Same baseline/optimized contract | Sections 1–4 |
