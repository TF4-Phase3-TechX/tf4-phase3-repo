# AIOPS-02: AIOps MVP Incident Type Selection

**Related Epic:** EPIC-AIOPS-01 — AIOps Discovery & Data Foundation  
**Output owner:** AIO01  
**Status:** Done — MVP types selected

---

## 1. Selection Methodology

Each candidate is scored across 4 dimensions on a 1–3 scale (3 = best):

| Dimension | Definition |
|---|---|
| **Signal Readiness** | Are the required metrics/logs/traces already emitted by the system without code changes? |
| **Evidence Quality** | Can AIOps demonstrate detection with a concrete, reproducible evidence artifact (trace ID, log line, metric graph)? |
| **Demo Value** | Does the incident type map directly to a business-critical path (SLO, revenue, AI safety)? |
| **Trigger Feasibility** | Can we reliably reproduce this incident in a controlled way (flag, load-gen, chaos) to validate the detector? |

---

## 2. Candidate Comparison

### Candidate A — LLM Timeout / Error

**Incident pattern:** `product-reviews` calls `llm` over HTTP; LLM returns 429, raises exception, or hangs indefinitely causing gRPC thread exhaustion.

| Dimension | Score | Evidence |
|---|---|---|
| Signal Readiness | **3** | `span.record_exception(e)` and `span.set_status(ERROR)` already in [`product_reviews_server.py:L194-L200`](file:///d:/DevopsAndCloud/xbrain-docs/xbrain-learners/phase3/techx-corp-platform/src/product-reviews/product_reviews_server.py#L194-L200). Metric `app_ai_assistant_counter` already emitted. OTLP log includes "Caught Exception" string. |
| Evidence Quality | **3** | BTC-controlled `llmRateLimitError` feature flag ([`product_reviews_server.py:L164`](file:///d:/DevopsAndCloud/xbrain-docs/xbrain-learners/phase3/techx-corp-platform/src/product-reviews/product_reviews_server.py#L164)) can trigger a reproducible 429 path on demand — guaranteed test signal, no load needed. |
| Demo Value | **3** | Directly maps to AI Safety SLO: *"không được hiển thị tóm tắt sai lệch"* ([`SLO.md`](file:///d:/DevopsAndCloud/xbrain-docs/xbrain-learners/phase3/onboarding/SLO.md#L13)). Also triggers the `gRPC ThreadPoolExecutor` exhaustion risk (`max_workers=10`, [`L361`](file:///d:/DevopsAndCloud/xbrain-docs/xbrain-learners/phase3/techx-corp-platform/src/product-reviews/product_reviews_server.py#L361)). Tells the PM story: *"AI broke, here's how we caught it."* |
| Trigger Feasibility | **3** | BTC owns the flag. AIO triggers it by querying the endpoint; flag flips the behaviour with 50% probability. Fully controllable, no cluster changes needed. |
| **Total** | **12 / 12** | |

---

### Candidate B — Service Latency Spike

**Incident pattern:** A microservice (e.g. `product-reviews`, `checkout`) shows elevated p95/p99 latency. Most likely triggers: DB connection pool exhaustion (INC-1 pattern) or downstream call waiting.

| Dimension | Score | Evidence |
|---|---|---|
| Signal Readiness | **3** | `grpc_server_handling_seconds_bucket` and `http_server_duration_milliseconds_bucket` are collected by OTel Collector and stored in Prometheus. No instrumentation changes required. Histogram buckets already configured ([`values.yaml:L1016-L1019`](file:///d:/DevopsAndCloud/xbrain-docs/xbrain-learners/phase3/techx-corp-chart/values.yaml#L1016-L1019)). |
| Evidence Quality | **2** | Readable from Prometheus via PromQL (e.g. `histogram_quantile(0.95, rate(grpc_server_handling_seconds_bucket[5m]))`). Span-level breakdown visible in Jaeger. Requires `load-generator` to be running, which is included in chart ([`ARCHITECTURE.md:L32`](file:///d:/DevopsAndCloud/xbrain-docs/xbrain-learners/phase3/onboarding/ARCHITECTURE.md#L32)). Score -1 because latency spike detection needs a baseline window first. |
| Demo Value | **3** | INC-1 ([`INCIDENT_HISTORY.md:L9-L15`](file:///d:/DevopsAndCloud/xbrain-docs/xbrain-learners/phase3/onboarding/INCIDENT_HISTORY.md#L9-L15)) shows this pattern already happened: checkout latency caused 95% success rate (below 99% SLO). SRE lead and CFO both care: "can we see it coming before SLO burns?" |
| Trigger Feasibility | **2** | `load-generator` provides continuous traffic signal. Artificial spike requires temporarily raising load-gen concurrency or running a targeted locust script. CDO coordination needed to avoid unintended SLO burn during test. Score -1 for coordination dependency. |
| **Total** | **10 / 12** | |

---

### Candidate C — Error Rate Spike

**Incident pattern:** A service returns a sustained burst of 4xx/5xx HTTP or non-OK gRPC status codes.

| Dimension | Score | Evidence |
|---|---|---|
| Signal Readiness | **2** | `grpc_server_handling_seconds_count{rpc_grpc_status_code!="0"}` available in Prometheus. However, several services use HTTP-level routing through Envoy (`frontend-proxy`) so HTTP 5xx detection also requires `http_server_duration_milliseconds_count{http_status_code=~"5.."}` which may need label verification in the live cluster. |
| Evidence Quality | **2** | In steady-state baseline with load-gen running, error rate is near-zero, making the signal very clean. But *generating* a controlled error burst (without touching flagd) requires either deliberate misconfiguration or killing a pod — more disruptive than the LLM flag path. |
| Demo Value | **2** | While important, error rate spikes are a *consequence* of latency or LLM failures — not an independent incident type at MVP scale. It largely duplicates what Candidate A (LLM error) and Candidate B (latency → timeout → error) already cover. Adds marginal AIOps value as a standalone detector. |
| Trigger Feasibility | **1** | Controlled error generation without using BTC flags is risky (could burn SLO budget). Relying on BTC to trigger errors is valid but then it overlaps with Candidate A (LLM path). No clean independent trigger exists at MVP scope without flag access. |
| **Total** | **7 / 12** | |

---

## 3. MVP Selection Decision

| Rank | Incident Type | Score | Decision | Rationale |
|---|---|---|---|---|
| 🥇 1 | **LLM Timeout / Error** | 12/12 | ✅ **MVP — Week 2** | Highest signal readiness. BTC flag provides a repeatable trigger with zero risk to production SLO. Directly demonstrates AI Safety monitoring — the highest-value story for AIO01. |
| 🥈 2 | **Service Latency Spike** | 10/12 | ✅ **MVP — Week 2** | Covers the INC-1 historical pattern. Prometheus histograms are already in place. Ties latency detection directly to checkout SLO ($revenue-critical path). Requires load-gen baseline but that is already deployed. |
| — | **Error Rate Spike** | 7/12 | ⛔ **Deferred to Week 3** | Overlaps with both selected types. Trigger mechanism is high-risk. Will be incorporated as an *output signal* of the Latency Spike detector (high latency → timeout → 5xx), not as a standalone MVP detector. |

---

## 4. Required Signals per Selected Incident Type

### MVP-1: LLM Timeout / Error

**Detection goal:** Alert when `product-reviews` fails to get a valid LLM response, either due to a 429 (rate-limit), unhandled exception, or future timeout (missing today — see Risk R2/R3 in baseline findings).

| Signal | Source | Query / Filter | Threshold |
|---|---|---|---|
| **LLM Error Span** | Jaeger (via OpenSearch) | `service.name = "product-reviews" AND status.code = "ERROR"` in `otel-logs-*` | Any occurrence = alert candidate |
| **LLM Exception Log** | OpenSearch (`otel-logs-*`) | `body: "Caught Exception"` AND `resource.attributes.service.name: "product-reviews"` | Any log in rolling 2-min window |
| **AI Counter Rate Drop** | Prometheus | `rate(app_ai_assistant_counter[5m])` near zero while traffic continues (`rate(grpc_server_handling_seconds_count{rpc_service=~".*ProductReview.*"}[5m]) > 0`) | Counter rate drops > 90% vs baseline |
| **gRPC Error Rate (AI path)** | Prometheus | `rate(grpc_server_handling_seconds_count{service_name="product-reviews", rpc_grpc_status_code!="0"}[5m])` | > 0.5 errors/sec sustained for 2m |
| **LLM 429 Log** | OpenSearch | `body: "Returning a rate limit error"` AND `resource.attributes.service.name: "llm"` | Any match = trigger |

**Controlled trigger:** Set `llmRateLimitError` flag to `true` via BTC flagd → 50% of `AskProductAIAssistant` calls will return 429 path. Evidence: OpenSearch log `"Returning a rate limit error"` + Jaeger span status `ERROR` on `get_ai_assistant_response`.

---

### MVP-2: Service Latency Spike

**Detection goal:** Alert when p95 latency on a critical-path service exceeds the SLO threshold (>1s for browse, implicit SLO for checkout derived from INC-1 pattern at ~2-3s).

| Signal | Source | Query / Filter | Threshold |
|---|---|---|---|
| **p95 gRPC Latency** | Prometheus | `histogram_quantile(0.95, sum by(le, service_name) (rate(grpc_server_handling_seconds_bucket{service_name=~"product-reviews|checkout|cart"}[5m])))` | > 1.0 second sustained for 3 minutes |
| **DB Connection Wait** | OpenSearch (Logs) | `body: "timeout"` OR `body: "connection"` AND `resource.attributes.service.name: "product-reviews"` | Any match correlated with latency spike |
| **Span Duration Outlier** | Jaeger | Spans on `get_product_reviews` or `get_ai_assistant_response` with duration > 2000ms | Manual correlation during incident window |
| **gRPC Request Queue Buildup** | Prometheus | `sum(grpc_server_started_total) - sum(grpc_server_handled_total)` for target service | > 20 in-flight requests sustained for 2m |
| **Load Generator Throughput Drop** | Prometheus | `rate(http_server_duration_milliseconds_count{service_name="frontend"}[5m])` | > 30% drop from rolling 10m baseline |

**Controlled trigger:** Increase `load-generator` concurrency temporarily (edit locust users) OR use DB connection exhaustion simulation (multiple concurrent requests to `product-reviews`). Coordinate with CDO to avoid SLO burn. Prefer testing against `product-reviews` first (isolated to AI path) before touching `checkout` (revenue-critical).

---

## 5. Deferred Incident Types

| Incident Type | Defer Reason | Re-evaluate When |
|---|---|---|
| **Error Rate Spike (standalone)** | Overlaps with MVP-1 and MVP-2 outcomes. No clean independent trigger. Will be detected as a downstream signal of the two selected types. | Week 3: after Latency and LLM detectors are validated; wire in as a composite rule. |
| **Pod Crash / CrashLoopBackOff** | Requires K8s Events API integration (not in Prometheus; needs separate watcher). Trigger requires killing pods (disruptive). | Week 3: add K8s event watcher as a secondary detection channel. |
| **Kafka Consumer Lag** | `otelcol_kafkametrics_consumer_offset_lag` metric is available ([`values.yaml:L944-L951`](file:///d:/DevopsAndCloud/xbrain-docs/xbrain-learners/phase3/techx-corp-chart/values.yaml#L944-L951)), but the Kafka path (`accounting`, `fraud-detection`) is not on the critical SLO path. Lower business impact at MVP scope. | Week 3: add as monitoring-only panel, not an alerting detector. |
| **DB Saturation** | No direct DB metrics in Prometheus yet (PostgreSQL receiver not configured). Would require adding `postgresqlreceiver` to OTel Collector config. Scope creep for Week 2. | Week 3: add PostgreSQL receiver to OTel Collector if DB incidents surface. |

---

## 6. Summary

```
AIOps MVP Scope — Week 2:

  ✅ MVP-1: LLM Timeout / Error
     Trigger: BTC flagd (llmRateLimitError)
     Signals: OpenSearch error logs + Jaeger ERROR spans + Prometheus AI counter drop

  ✅ MVP-2: Service Latency Spike
     Trigger: load-generator ramp + DB connection pressure
     Signals: Prometheus p95 histogram + gRPC queue buildup + Jaeger span duration

  ⛔ Deferred: Error Rate Spike (Week 3 composite rule)
  ⛔ Deferred: Pod Crash / CrashLoopBackOff (Week 3 K8s watcher)
  ⛔ Deferred: Kafka Consumer Lag (Week 3 monitoring panel)
  ⛔ Deferred: DB Saturation (Week 3, requires OTel receiver addition)
```

> [!NOTE]
> The two selected MVP types cover **both sides of the AI reliability surface**: internal AI feature degradation (MVP-1) and infrastructure-level degradation affecting the AI path (MVP-2). Together they allow AIO01 to demonstrate a full detect-correlate-recommend loop at the Week 2 Ops Review without requiring infrastructure changes or risking the production SLO error budget.
