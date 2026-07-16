# Mandate 07a evidence — detector implementation and analysis

- **Jira:** [TF4AIO-71](https://aio1-xbrain.atlassian.net/browse/TF4AIO-71)
- **Deadline:** 2026-07-18
- **Evidence state:** Ready for human ADR sign-off after PR #137 and PR #208 merge
- **Runtime scope:** Mandate 07a is document/implementation evidence. Runtime calibration belongs to TF4AIO-72.

## Implementation evidence

| Work | Evidence | Current state at 2026-07-16 |
| --- | --- | --- |
| Detection rules and thresholds | [PR #181](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/181) | Merged |
| Detector output schema and probe | [PR #137](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/137) | Open; CI passing; eligible review/merge required |
| Rule-based detector, LLM failure detector, incident summary | [PR #208](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/208) | Open; tests and CI passing; eligible review/merge required |
| Architecture decision | [ADR-M07](./ADR-M07-rule-based-aiops-detection.md) | Proposed; human signature required |

## Metric analysis

### 1. p95 latency

- **Services:** `product-reviews`, `checkout`, `cart`.
- **Why:** It is a user-visible symptom and detects slow success responses that error rate misses.
- **Real signal:** `traces_span_metrics_duration_milliseconds_bucket`.
- **Initial normal assumption:** candidate `200–800 ms` under active traffic.
- **Anomaly:** warning `>1000 ms`; critical `>2000 ms`; sustained `3m`.
- **Method:** per-service `histogram_quantile(0.95, ...)`.
- **Evidence qualification:** The range is provisional. The latest schema check found no span-metric samples while the cluster was idle, so this is not claimed as a measured 48-hour baseline.

### 2. Service error rate

- **Services:** `product-reviews`, `checkout`, `cart`.
- **Why:** It directly measures failed requests and error-budget consumption.
- **Real signal:** `traces_span_metrics_calls_total`, split by `status_code`.
- **Initial normal assumption:** candidate `0–1%` under active traffic.
- **Anomaly:** warning `>1%`; critical `>5%`; at least 10 requests; sustained `2m`.
- **Method:** per-service error/total ratio with a minimum-volume guard.
- **Evidence qualification:** Thresholds are aligned with the current rule specification; the normal band still requires labeled live calibration.

### 3. LLM provider failures

- **Service:** `product-reviews` AI assistant.
- **Why:** The application can return a safe static fallback while the provider path is unavailable, so storefront HTTP success alone can hide an LLM outage.
- **Real signals:** `app_llm_errors_total`, `app_llm_calls_total`, `app_llm_latency_seconds`, plus sanitized `otel-logs-*` provider error metadata.
- **Initial normal assumption:** `rate(app_llm_errors_total[3m]) = 0` in a healthy provider window.
- **Anomaly:** warning `>0.1 errors/s`; critical `>0.5 errors/s`; sustained `3m`.
- **Method:** Prometheus provider-error rate with OpenSearch corroboration; unavailable telemetry is `unknown`, not healthy zero.
- **Evidence qualification:** Account-level Bedrock quota zero is an observed failure condition for Mandate 06. It may be used as one labeled 07b incident only inside a controlled window; it is not a normal baseline.

## What is deliberately not claimed in 07a

- No successful end-to-end production alert has been claimed.
- No 48-hour normal baseline has been claimed.
- No precision, recall, or lead-time result has been claimed.
- No ADR signature has been inferred from authorship or from an AI review.

Those items require human approval or the controlled runtime evidence tracked in [TF4AIO-72](https://aio1-xbrain.atlassian.net/browse/TF4AIO-72).
