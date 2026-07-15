# 🚨 AIOps Incident Summary: AI_LLM_TIMEOUT_ERROR

**Service:** `product-reviews`
**Severity:** `HIGH`
**Detected At:** 2026-07-15T15:40:00Z

## 📊 Overview
The AIOps detector identified a potential issue matching the rule `ai_llm_timeout_error`.
- **Metrics triggered:** 1
- **Logs matched:** 15
- **Confidence Level:** High (Service Score: 1.00)

## 🔍 Evidence & Queries
You can verify the signals using the following queries in the observability stack:

**Metrics (Prometheus):**
```promql
sum(rate(aiops_llm_calls_total{service="product-reviews", status=~"error|timeout|429"}[5m])) / sum(rate(aiops_llm_calls_total{service="product-reviews"}[5m])) > 0.05
```

**Logs (OpenSearch):**
```lucene
kubernetes.labels.app:"product-reviews" AND (message:*timeout* OR message:*429* OR message:*rate limit*) AND message:(*llm* OR *openai* OR *bedrock*)
```
[🔗 View Logs in Grafana](http://grafana.internal/explore?left=%5B%22now-1h%22,%22now%22,%22opensearch%22,%7B%22expr%22:%22kubernetes.labels.app:"product-reviews" AND (message:*timeout* OR message:*429* OR message:*rate limit*) AND message:(*llm* OR *openai* OR *bedrock*)%22%7D%5D)

## ⚠️ Limitations & Notes
- **Trace Context:** Traces might not be linked if the downstream SDK handled the error gracefully without setting the OpenTelemetry span status to ERROR.
- **Cost Impact:** Rate limits (429) might trigger this alert but do not necessarily indicate a system crash, they might just be a quota exhaustion. Check billing metrics if applicable.
