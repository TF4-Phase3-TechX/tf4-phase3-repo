# AIO Service Health Readout — Phase 3

- **Date:** 2026-07-17
- **Workgroup:** AIO1 (Nam, Thông, Vũ, Hậu, Hòa, Tâm, Văn)
- **Status:** **Completed & Signed Off**
- **Related Jira Task:** [TF4AIO-50](https://aio1-xbrain.atlassian.net/browse/TF4AIO-50)

---

## 1. Executive Summary

This Service Health Readout summarizes the operational readiness of the **product-reviews** assistant AI feature on the Amazon Bedrock path and the associated AIOps telemetry detection system for Week 3. All safety, quality, budget, and deployment gates have been met. The real model path has successfully been promoted from **Proposed** to **Accepted** following successful canary execution, rollback drills, and metric correlation.

---

## 2. AI Health & Model Selection (Bake-off Results)

A three-model bake-off was executed using `eval/run_bakeoff.py` on a dataset of 30 versioned cases (3 repetitions each, 270 total records) to evaluate suitability against hard safety and quality gates.

### 2.1 Bake-off Evaluation Matrix

| Metric / Gate | Target | Claude Haiku 4.5 | Qwen3 Next 80B | Amazon Nova 2 Lite |
| --- | --- | --- | --- | --- |
| **Model/Profile ID** | \- | `us.anthropic...` | `qwen.qwen3...` | `us.amazon.nova-2-lite-v1:0` |
| **Supported Quality** | $\\ge 90%$ | 63.33% (FAIL) | 53.33% (FAIL) | **96.67% (PASS)** |
| **Unsupported Questions** | 100% | 46.67% (FAIL) | 100% (PASS) | **100% (PASS)** |
| **Stored Injection Quarantine** | 100% | 100% (PASS) | 100% (PASS) | **100% (PASS)** |
| **Direct Attack Block** | 100% | 100% (PASS) | 100% (PASS) | **100% (PASS)** |
| **PII/Canary No-Leak** | 100% | 100% (PASS) | 100% (PASS) | **100% (PASS)** |
| **p95 Latency** | $\\le 5$s | 2,704 ms | 2,282 ms | **1,328 ms (PASS)** |
| **Cost / 1k Successes** | Min | $0.5833 | $0.0577 | **$0.4541** |
| **Disposition** | \- | Eliminated | Eliminated | **Winner (Score: 92.02)** |

### 2.2 Selected Model Architecture & Guardrail Pinnings

- **Production Model:** Amazon Nova 2 Lite (`us.amazon.nova-2-lite-v1:0`)
- **Guardrail Pinned Version:** `wckqh9dms6qa:1` (Production, READY)
- **IAM Authorization:** Pinned EKS Pod Identity association (`a-iuw7np6l5niq1k2zt`) using ServiceAccount `product-reviews-bedrock` mapping to `tf4-product-reviews-bedrock` role. Wildcards are disabled.

---

## 3. AIOps Telemetry & Detector Results

The AIOps track has successfully built and verified a rule-based detection engine and incident summary generator.

### 3.1 Prometheus & OpenSearch Telemetry Contract

- Telemetry metrics successfully registered and verified:
  - `app_llm_prompt_tokens_total`
  - `app_llm_completion_tokens_total`
  - `app_llm_estimated_cost_usd_total`
  - `app_llm_latency_seconds` (histogram)
  - `app_llm_errors_total` (counter)
  - `app_llm_calls_total` (counter)
- **Privacy Compliance:** No prompts, user reviews, or raw model responses are stored in traces or logs. Only metadata dimensions (model ID, outcome status, token counts, and latency) are recorded.

### 3.2 Anomaly Detector & Incident Summary MVP

- **Incident Detection:** Auto-monitors `app_llm_errors_total` and queries OpenSearch logs to catch LLM timeouts, unavailability, and format-validation errors.
- **RCA & Incident Summary (**`incident_summary.py`**):** Automatically generates standard Markdown postmortem summaries mapping contributors to high/medium severity.
- **Dynamic Grafana Correlation:** Generates custom gRPC/Prometheus visualization links pointing directly to the incident timeframe.
- **Validation Report:** Confirmed using mock telemetry in test script `validate_tf4aio45.py` and logged in `TF4AIO-45_EVIDENCE.md`.

---

## 4. Core Technical Findings & Remediation Records

During validation, the team resolved several high-priority system gaps:

1. **Metrics Initialization Gaps:**
   - **Problem:** OTel metrics initially failed to register/collect.
   - **Fix:** Added missing OTel Meter declarations in `metrics.py` and wrapped raw OpenAI/Bedrock client calls in `product_reviews_server.py` with custom metrics instrumentation.
2. **LLM Output Truncation & Schema Failures (Canary Failure):**
   - **Problem:** The canary crashed returning `invalid_response` because Nova 2 Lite requires more tokens (328 tokens observed) to return exact citation substrings, which got truncated under the original `maxTokens=300` limit. Also, Nova rejected the top-level `additionalProperties: false` tool definition.
   - **Fix:** Increased the bounded `maxTokens` cap to `512` and dynamically stripped unsupported top-level fields from Nova tool schemas while keeping strict validation on the python side.
3. **Database Connection Exhaustion:**
   - **Problem:** gRPC concurrency from AI requests exhausted raw PostgreSQL connections.
   - **Fix:** Switched to a global `ThreadedConnectionPool` (max 20 connections) and wrapped database interactions in a context-managed `get_db_connection()` to guarantee connection release.
4. **Budget Controls:**
   - **Spend Pinned:** Pinned daily caps ($2/Dev, $10/Staging, $50/Prod) and implemented hourly Prometheus warnings.

---

## 5. Remaining Risks & Mitigations

| Risk | Impact | Mitigation Plan / Control |
| --- | --- | --- |
| **Bedrock Outages / Latency Spikes** | Storefront availability drop | Static fallback returns canonical unavailable response. Process-local circuit breaker opens for 60s after 5 failures in 30s. Zero SDK retries to avoid cascading latency. |
| **Budget Runaway** | High AWS bill | Telemetry trackers alert when burn-rate threshold exceeded. Nova cost metrics mapped to fixed pricing coefficients. |
| **Model ID Updates** | Tool contract break | Strict CI/CD validation. Rollback to previous immutable Helm revision via GitOps (drill completed). |

---

## 6. Sign-off and Acceptance

We confirm that all acceptance gates, including pre-filter injection quarantine, exact evidence citations, telemetry contracts, and GitOps rollbacks have passed.

- **Nam (Tech Lead):** Signed Off (Architecture & Model Selection)
- **Văn (AIE):** Signed Off (Adapter, Fallback, Circuit Breaker)
- **Vũ (AIE):** Signed Off (Dataset, Runner & Bake-off)
- **Hậu (AIOps):** Signed Off (Injection, PII & Guardrails)
- **Hòa (AIOps):** Signed Off (Telemetry, Observability & Costs)
- **Tâm (AIOps):** Signed Off (Canary & Rollback Drill)
- **Thông (PM):** Signed Off (IAM, CDO & Handoff Evidence)