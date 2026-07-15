# AIOps Incident Summary: AI_LLM_TIMEOUT_ERROR

**Service:** `tf1-ai-triage-engine`
**Severity:** `HIGH`
**Detected At:** 2026-07-14T15:40:00Z

## Overview
The AIOps detector identified a potential issue matching the rule `ai_llm_timeout_error`.
- **Metrics triggered:** 1
- **Logs matched:** 15
- **Confidence Level:** High (Correlated Metrics and Logs)

## Evidence & Queries
You can verify the signals using the following queries in the observability stack:

**Metrics (Prometheus):**
```promql
sum(rate(aiops_llm_calls_total{service="tf1-ai-triage-engine", status=~"error|timeout|429"}[15m])) > 0
```

**Logs (Loki):**
```logql
{service="tf1-ai-triage-engine"} |~ "(?i)(llm|openai|anthropic).*?(timeout|429|rate limit|failed)"
```
[View Logs in Grafana](http://grafana.internal/explore?left=%5B%22now-1h%22,%22now%22,%22loki%22,%7B%22expr%22:%22{service="tf1-ai-triage-engine"} |~ "(?i)(llm|openai|anthropic).*?(timeout|429|rate limit|failed)"%22%7D%5D)

## Limitations & Notes
- **Trace Context:** Traces might not be linked if the downstream SDK handled the error gracefully without setting the OpenTelemetry span status to ERROR.
- **Cost Impact:** Rate limits (429) might trigger this alert but do not necessarily indicate a system crash, they might just be a quota exhaustion. Check billing metrics if applicable.
