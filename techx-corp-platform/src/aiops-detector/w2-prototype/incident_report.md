# 🚨 AIOps Incident Summary

**Service:** `product-reviews`
**Environment:** `production`
**Tenant:** `default`
**Severity:** `UNKNOWN`
**Detected At:** 2026-07-15T09:40:00Z
**Confidence:** Partial — score 0.83, 1 source(s) unavailable

---

## 📊 RCA Score Breakdown

| Signal | Score | Weight |
|---|---|---|
| Metric Anomaly (HTTP 5xx / app errors) | 0.90 | 0.35 |
| Trace Errors (Jaeger) | N/A (source unavailable) | 0.25 |
| Log Anomaly (OpenSearch) | 0.60 | 0.20 |
| AI Telemetry (app_llm_* errors) | 1.00 | 0.20 |
| **Total Service Score** | **0.83** | — |

---

## 🔍 Verification Queries
Paste these into your observability stack to reproduce the detector signal.

**Metrics (Prometheus):**
```promql
sum(rate(http_server_requests_total{service="product-reviews", status=~"5.."}[5m])) / sum(rate(http_server_requests_total{service="product-reviews"}[5m]))
```

**AI Telemetry (Prometheus):**
```promql
sum(rate(app_llm_requests_total{service="product-reviews", status=~"error|timeout|rate_limited"}[5m]))
```

**Logs (OpenSearch / Lucene):**
```lucene
kubernetes.labels.app:"product-reviews" AND level:"ERROR"
```
[🔗 View Logs in Grafana (URL-encoded)](http://grafana.internal/explore?left=%5B%22now-1h%22%2C+%22now%22%2C+%22opensearch%22%2C+%7B%22query%22%3A+%22kubernetes.labels.app%3A%5C%22product-reviews%5C%22+AND+level%3A%5C%22ERROR%5C%22%22%7D%5D)

---

## ⚠️ Limitations & Signal Gaps
- **Source availability:** 1 telemetry source(s) were unavailable during this evaluation; unavailable sources are excluded from score re-normalisation.
- **Trace Context:** OTel span status may not reflect LLM errors if the SDK handles failures gracefully without calling `span.set_status(StatusCode.ERROR)`.
- **Rate Limits vs. Crashes:** A `429 rate_limited` event scores the same as a hard error. Check provider billing dashboard if `ai_score` is the primary driver.
