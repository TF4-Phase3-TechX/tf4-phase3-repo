# AIOps Data Sources, Incident Taxonomy, and MVP Selection

Jira: `TF4AIO-12`, `TF4AIO-13`, `TF4AIO-14`

## 1. Confirmed Week 1 data sources

| Data source | Evidence | Week 1 conclusion |
| --- | --- | --- |
| Grafana UI | `screenshots/grafana-access.png` | Public Grafana route is reachable. |
| Jaeger UI | `screenshots/jaeger-access.png` | Public Jaeger route is reachable and can be used for follow-up trace validation. |
| Product page AI UI | `screenshots/ai-smoke-test-product-page.png` | AI assistant returns a product-specific mock LLM response. |

## 2. Not yet proven

The following are not fully proven by the current evidence folder:

- exact Jaeger trace ID for the exact Ask AI click;
- exact AI end-to-end latency from trace evidence;
- separated LLM call latency;
- programmatic Prometheus query access from an AIOps workload/script;
- programmatic OpenSearch query access from an AIOps workload/script;
- detector running continuously inside Kubernetes.

These remain Week 2/3 verification tasks.

## 3. Incident taxonomy

| Incident type | Why it matters | Candidate signals |
| --- | --- | --- |
| Service latency spike | Direct SLO risk and common platform failure mode. | HTTP/gRPC latency histogram, Jaeger trace latency, load-generator traffic. |
| Error rate spike | User-facing failures and reliability degradation. | HTTP/gRPC status codes, service logs, trace status. |
| Pod crash/restart | Service instability and possible deployment/resource issue. | Kubernetes restart count, pod status, logs. |
| DB saturation / connection pressure | Known historical failure pattern from incident history. | DB connection count, DB latency, app errors, request queueing. |
| Kafka lag | Async pipeline delay and downstream data freshness issue. | Kafka consumer lag metrics, order/accounting event delay. |
| LLM timeout/error | AI-specific reliability risk when moving from mock to real LLM. | LLM error logs, fallback count, trace status, AI request latency. |
| AI unsafe/misleading response | Product AI must not show misleading summaries to customers. | Eval failures, user reports, safety filter events, trace/log evidence. |
| AI telemetry/privacy leak | Prompt/review content can appear in logs/traces if not redacted. | OpenSearch/Jaeger inspection, redaction tests. |

## 4. MVP selection

Recommended Week 2 MVP incidents:

1. LLM timeout/error
2. Service latency spike

Rationale:

- LLM timeout/error is AIO-owned and directly tied to real LLM readiness.
- Service latency spike is easy to explain to SRE/mentor reviewers and maps to existing observability surfaces.
- Both can be demonstrated with conservative evidence if CDO/DevOps exposes Prometheus/OpenSearch/Jaeger query access.

## 5. Deferred incidents

| Deferred item | Reason |
| --- | --- |
| Error rate spike | Useful, but overlaps with latency/LLM failure in W2; can become composite output later. |
| Pod crash/restart | Needs Kubernetes/runtime signal access and safe trigger plan. |
| DB saturation | Important, but should be coordinated with CDO and load-test plan. |
| Kafka lag | Requires Kafka metrics and a clean demo trigger. |
| ML-based anomaly detection | Needs historical data; rule-based MVP is more defensible for W2. |

## 6. Conservative Jira wording

Use this wording:

> Week 1 selected AIOps MVP incident types and identified required signals. Grafana and Jaeger UI access are confirmed. Programmatic Prometheus/OpenSearch access and live detector validation are not yet proven and should be tracked as Week 2/3 implementation evidence.

