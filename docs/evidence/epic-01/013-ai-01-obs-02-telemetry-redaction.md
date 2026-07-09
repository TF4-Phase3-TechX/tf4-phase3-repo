# 013 — AI-01 / OBS-02 Telemetry Redaction Baseline

## 1. Đã làm gì?

AIO-01 reviewed the AI telemetry/privacy gap identified in TF4 Jira:

- `SCRUM-16` — TASK-01: System gap analysis
- `SCRUM-17` — TASK-02: Prioritized gap fix/mitigation

The reviewed gap is:

- `AI-01` — AI prompt/content may be captured into telemetry/logs by default.
- Shared with `OBS-02` because telemetry redaction also affects observability/audit evidence.

## 2. Kết quả hiện tại

Current Week 1 baseline is still using the mock OpenAI-compatible LLM. This evidence does not claim that real LLM telemetry has been safely rolled out.

AIO-01 identified the telemetry boundary that must be protected before real LLM integration:

Fields/content that should not be stored in logs/traces by default:

- user prompt/question text;
- full LLM request messages;
- full LLM response content;
- product review text if it can contain user-provided PII;
- any customer/order/payment identifiers if they appear in AI context.

Fields that can be kept as structured non-sensitive telemetry:

- request count;
- service name and route;
- model/provider name;
- latency;
- error type/status;
- fallback count;
- token count and estimated cost when real LLM is enabled;
- trace/correlation ID.

Dependencies:

- CDO-08: review security/redaction boundary.
- CDO-07: verify no prompt/PII remains in OpenSearch/Jaeger after implementation.

## 3. Bằng chứng nằm ở đâu?

Related Jira:

- TF4 Jira tổng: `SCRUM-16`, `SCRUM-17`
- AIO Jira private tracking: `TF4AIO-16`

Related Week 1 evidence:

- `docs/evidence/aio1-week1/evidence.md`
- `docs/evidence/aio1-week1/screenshots/grafana-access.png`
- `docs/evidence/aio1-week1/screenshots/jaeger-access.png`

Related source areas for future implementation review:

- `techx-corp-platform/src/product-reviews/product_reviews_server.py`
- `techx-corp-platform/src/llm/app.py`
- Helm values/env configuration for OpenTelemetry GenAI content capture.

## 4. Ghi chú / Follow-up

Week 1 output is assessment and evidence planning, not a claim that all redaction controls are already implemented.

Week 2 follow-up should:

1. confirm effective OpenTelemetry settings for GenAI content capture;
2. redact AI prompt/response content from application logs;
3. preserve safe structured metrics;
4. verify in Jaeger/OpenSearch that prompt/PII content is not present;
5. attach runtime evidence after the fix.
