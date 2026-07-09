# AI Incident and Postmortem Readiness

Jira: `TF4AIO-19`

## 1. AI incident categories

| Category | Example |
| --- | --- |
| Misleading or incorrect AI answer | Product summary contradicts reviews or invents unsupported facts. |
| Unsafe AI output | Prompt injection succeeds, PII leaks, or system prompt content appears in response. |
| LLM availability/degradation | Timeout, 429/rate-limit, provider unavailable, or fallback failure. |
| AI latency regression | Product page waits too long for AI response. |
| AI cost spike | Token/call volume unexpectedly increases after real LLM is enabled. |
| AI observability gap | Incident cannot be debugged because traces/metrics/logs are missing or unsafe. |
| AIOps detector quality issue | Detector misses obvious incident or produces noisy false positives. |

## 2. Minimum evidence fields

Each AI/AIOps incident should collect:

- incident ID or Jira key;
- time window and environment;
- user-visible impact;
- affected service path;
- product ID and sanitized prompt class;
- LLM mode: mock or real;
- active feature flags;
- trace evidence;
- metric/dashboard evidence;
- sanitized log evidence;
- repro steps;
- mitigation or rollback action;
- confidence level;
- follow-up owner/task.

## 3. Lightweight postmortem template

```md
# Incident title

## Summary

What happened, when, and which user/system path was affected?

## Impact

Who was affected and what was the customer/business impact?

## Detection

How was it detected? Which metric, trace, log, eval, or report triggered investigation?

## Timeline

- T0:
- T1:
- T2:

## Root cause / confidence

What is the most likely cause? What evidence supports it? What remains uncertain?

## What worked

Which controls/evidence helped?

## What failed or was missing

Which controls/evidence were absent or insufficient?

## Corrective actions

| Action | Owner | Jira | Due |
| --- | --- | --- | --- |
```

## 4. Week 1 limitation

This is an operational readiness artifact. It does not prove incident automation exists yet. Detector implementation and live incident validation are Week 2/3 work.

