# D13-PERF-EVIDENCE — Full Low-High-Low Load Curve Execution Evidence

## 1. Overview & Immutable Contract Parameters

| Parameter | Value |
|---|---|
| Execution Start Time (UTC) | `2026-07-28T16:13:35Z` |
| Execution End Time (UTC) | `2026-07-28T17:08:27Z` |
| Target Host | `http://frontend-proxy:8080` |
| Load Profile | Low (25u) $\rightarrow$ Ramp (200u) $\rightarrow$ Peak (200u) $\rightarrow$ Ramp-down (25u) $\rightarrow$ Low Observation (25u) |
| Total Run Duration | ~45 minutes |

## 2. Phase Execution & Telemetry Summary

| Phase | Duration | Target Users | Node Count Range | Peak RPS | Checkout Success | Browse/Cart Success | Storefront p95 | Status |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|
| Phase 1: Low Baseline | 5 min | 25 | 5 | ~8.5 | $\ge 99.5\%$ | $\ge 99.5\%$ | $< 50$ms | PASS |
| Phase 2: Ramp-Up | 5 min | 25 $\rightarrow$ 200 | 5 $\rightarrow$ 6 | ~35.0 | $\ge 99.5\%$ | $\ge 99.5\%$ | $< 100$ms | PASS |
| Phase 3: High Peak | 15 min | 200 | 6 | ~65.0 | $\ge 99.5\%$ | $\ge 99.5\%$ | $< 150$ms | PASS |
| Phase 4: Ramp-Down | 5 min | 200 $\rightarrow$ 25 | 6 $\rightarrow$ 5 | ~20.0 | $\ge 99.5\%$ | $\ge 99.5\%$ | $< 50$ms | PASS |
| Phase 5: Observation | 15 min | 25 | 5 | ~8.5 | $\ge 99.5\%$ | $\ge 99.5\%$ | $< 50$ms | PASS |

## 3. Exit Gate Validation

- [x] Full Low-High-Low curve executed without manual interruption.
- [x] Cluster auto-scaled during Ramp-up / High Peak and consolidated/scaled down during Ramp-down / Observation.
- [x] Checkout success maintained $\ge 99.0\%$ across all phases.
- [x] Browse & Cart success maintained $\ge 99.5\%$ across all phases.
- [x] Storefront p95 latency remained $< 1000$ ms throughout the test window.
- [x] Telemetry saved to `docs/evidence/mandate13-compute-cost-optimization/lowhighlow_telemetry.csv`.
