# ADR-015 — AIOps Incident Detection: Baseline, Thresholds, and Incident-Summary Generation

**Status:** Accepted (Phase 1 Eval)
**Date:** 2026-07-21 (Updated: 2026-07-22)
**Ticket:** TF4AIO-80 (AI MANDATE #15)
**Author:** Đình Thông Trần (Assignee, AIOps Lead)
**Reviewer:** _(Tech Lead signature pending live cluster evidence)_

---

## Context

MANDATE-15 requires the AIOps detector to distinguish a service that is **merely busy** from one that is **broken**, proven on a labeled scenario set and on a BTC-supplied hidden set. This ADR records the exact algorithm, calibration decisions, and incident-summary generation so the mentor and BTC can audit the scoring logic.

---

## Detector Algorithm

### 1. Data collection

The detector polls Prometheus every **`AIOPS_POLL_SECONDS` (default: 45 s)** for three signal types per monitored service:

| Signal | PromQL pattern | Unit |
|---|---|---|
| `latency` | `histogram_quantile(0.95, ...)` over span-metrics | milliseconds |
| `error_rate` | error-span rate / all-span rate | ratio [0,1] |
| `llm_error` | LLM error call rate / total call rate | ratio [0,1] |

Raw Prometheus `range_query` results are an ordered list of `(timestamp, value)` pairs. The detector uses the **value sequence** (last `AIOPS_LOOKBACK_MINUTES=30` minutes, step = poll window).

### 2. Baseline construction — Robust Median/MAD filter

```
cleaned_baseline = { p ∈ history[:-1] : |p − median(history[:-1])| ≤ max(MAD_multiplier × MAD, 0.5 × |median|) }
```

- `MAD = median(|pᵢ − median(history)|)` — **not** standard deviation; a single outlier spike cannot inflate the baseline.
- `MAD_multiplier = AIOPS_BASELINE_MAD_MULTIPLIER` (default 6).
- `relative_band = AIOPS_BASELINE_RELATIVE_BAND` (default 0.5 = 50%).
- If `< 3` points survive, the raw baseline is used unchanged.

**Why this prevents false alarms during load:** The baseline is always derived from the service's own recent normal. When overall traffic grows, the median and MAD grow proportionally, so the same absolute latency increase produces a smaller z-score than it would against a fixed threshold.

### 3. Anomaly scoring (adaptive)

Three independent scores are computed and any one can contribute to a breach decision:

| Score | Formula | Detects |
|---|---|---|
| `ratio` | `current / |baseline_mean|` | Proportional spike |
| `zscore` | `|current − baseline_mean| / max(std, 5% × |baseline_mean|)` | Sharp deviation from normal |
| `ewma` | `|current − EWMA| / spread` | Smoothed persistent shift |
| `trend` | Least-squares slope × window / `|baseline_mean|` | Gradual, consistent rise |
| `slow_drift` | Boolean: trend AND consistency AND ratio all exceed thresholds | Memory-drain / queue-build |

### 4. Breach gate — Acute vs Gradual

**Acute path (sudden incident):**
```
breached = (current ≥ safety_floor) AND (ratio ≥ RATIO_THRESHOLD=1.5 OR (zscore ≥ 3 AND ewma ≥ 1))
```

**Gradual drift path (slow degradation):**
```
breached = trend ≥ 25% relative change AND consistency ≥ 75% monotone AND current_ratio ≥ 1.2
```

The safety floors (latency: 1 000 ms, error rate: 5%) prevent a signal from being anomalous at an absolutely negligible value (e.g., z-score = 4 on a 0.01 ms baseline).

**How it avoids masking:** A noise spike that would inflate `baseline_mean` is stripped by the MAD filter. A second, simultaneous signal on another service uses an independent detector instance (independent streak state), so the spike on service A cannot silence a breach on service B.

### 5. Sustained-breach requirement

A single poll exceeding the gate produces an incident when `AIOPS_SUSTAINED_POLLS=1` (default: 1, aligned across `app/config.py` and `techx-corp-chart/values.yaml`). This satisfies Mandate 15's hard bar of firing real acute incidents within 1 detector cycle (45s).

### 6. Safety floors (hard bars)

| Hard bar | Value | Enforcement |
|---|---|---|
| Minimum latency to breach | 1 000 ms | `safety_floor = latency_threshold_ms` |
| Minimum error rate to breach | 5% | `safety_floor = error_rate_threshold` |
| Minimum LLM error rate | 5% | `safety_floor = llm_error_threshold` |

### 7. MTTD before / after

| Period | MTTD measurement method | Value |
|---|---|---|
| **Before** (historical static alert rules) | Estimated static threshold rule delay (`for: 5m` window) | ~300–600s (5–10 min) |
| **After** (this detector eval) | Sequential poll simulation to `decision.anomalous` (`poll_seconds=45s`) | **45s** (1 detector cycle) |

On the labeled dataset, measured MTTD-after is **45s (1 detector cycle)** for acute incidents.

---

## Incident Summary Generation

When the breach gate fires, the `IncidentSummaryGenerator.generate()` method produces a Markdown summary with:

1. **Incident metadata** — ID, service, type, severity, confidence, detected-at.
2. **Suspected cause** — human-readable root-cause string from `Decision.root_cause`.
3. **Evidence table** — exact PromQL query, window, observed value, Grafana Explore link.
4. **RCA candidates** — TORAI-lite weighted score per candidate service.
5. **Response guidance** — runbook ID, recommended action, approval status.

The summary is available at `GET /v1/incidents/{id}/summary` and is also stored in the IncidentStore for audit. Replay CLI (`benchmark/replay`) renders this summary for all detected events in its JSON report output.

---

## Calibration Notes

- The default thresholds were calibrated on labeled incident windows.
- Thresholds are all `AIOPS_*` environment variables; no code change is needed to recalibrate.
- The replay CLI (`.venv/bin/python -m benchmark.replay`) is the canonical offline evaluation tool.
- No LLM judge is used for the detection eval; all scoring is deterministic and fully auditable from source.

---

## Replay entry point (one-command repro)

```bash
cd techx-corp-platform/src/aiops
.venv/bin/python -m benchmark.replay \
  ../../../docs/aio1/mandate-15/labeled-scenarios-v1.jsonl \
  --output /tmp/m15-replay-report.json
```

---

## Decision

Accept this algorithm as the MANDATE-15 standard. It satisfies:

- ✅ Relative baseline (no fixed absolute threshold as primary gate)
- ✅ Masking resistance (MAD filter + independent streak state per service)
- ✅ Continuous workload (FastAPI + asyncio event loop, runs permanently)
- ✅ External-scenario replay entry (CLI accepts any JSONL scenario file)
- ✅ Auditable scoring logic (all formulas in this ADR and in `detection.py`)
- ✅ Hard floors: PII leakage = N/A (AIOps detector does not handle PII); unauthorized writes = blocked by `REMEDIATION_MODE=dry-run` default + approval gate

---

## Signature

| Role | Name | Date | Status |
|---|---|---|---|
| Author / AIOps Lead | Đình Thông Trần | 2026-07-21 | Signed |
| Tech Lead | _(pending live cluster evidence)_ | | In Progress |
