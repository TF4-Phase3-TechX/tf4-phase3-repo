# AIO Weekly Ops Review Section

This document maintains the weekly operational status, risk assessments, key metrics, and incident reports for the AI subsystem of project AIO1. It is updated at the end of each sprint week for the Ops Review meeting.

---

## Week 2 Ops Review (Date: July 14, 2026)

### 📊 AI Subsystem Health Summary
- **Current Mode:** Mock LLM (readying for controlled real LLM migration).
- **Service Status:** Green (No major degradations observed on mock endpoint).
- **Average Latency (Mock):** 12ms
- **API Error Rate:** 0% (Simulated rate limiting injected via flagd is resolved gracefully by the application fallback client).

### 🔍 Key Metrics & Telemetry Gaps Fixed
- **Status:** **PASS**
- **Action Taken:** Instrumented `product_reviews_server.py` with custom OpenTelemetry tracking for token usage, final LLM call latency, and estimated cost.
- **Evidence:** Custom attributes `app.llm.prompt_tokens`, `app.llm.completion_tokens`, and `app.llm.estimated_cost_usd` are now attached to `get_ai_assistant_response` spans.

### ⚠️ Top Risks & Mitigation Status

| Risk Description | Severity | Mitigation Status | Next Action / Owner |
| --- | --- | --- | --- |
| **LLM Upstream Outage / Timeout** | High | Fallback UI response and gRPC timeouts implemented. | Test with mock rate-limiting and latency injection. (Văn) |
| **LLM API Cost Runaway** | Medium | Defined daily budgets ($10/day for Staging) and alerting thresholds. | Deploy OTel metrics dashboard on Grafana. (Thông) |
| **Prompt Injection Vulnerability** | Medium | Allow-list of tools and system output filtering are in design. | Implement input validation before invoking completions. (Văn) |

### 🚨 Week 2 Incident Notes
- **Incident ID:** None.
- **Summary:** Simulated Rate Limit error drill was successfully run by injecting the `llmRateLimitError` feature flag. The application fell back to the graceful warning UI without cascading failures.
- **Evidence:** Span exception log shows: `Caught Exception: Rate limit exceeded (simulated)`.

### ➡️ Next Actions (Week 3)
1. Perform canary cutover of real LLM in Staging environment using the newly created [Readiness Checklist](./real_llm_readiness_checklist.md).
2. Wire rule-based detector to poll OTel token count and alert on Slack channel.
3. Conduct failure drill with simulated model failure.
