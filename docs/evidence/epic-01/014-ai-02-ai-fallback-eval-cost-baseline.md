# 014 — AI-02 Fallback, Eval, and Cost Gate Baseline

## 1. Đã làm gì?

AIO-01 reviewed the AI reliability/quality/cost gap identified in TF4 Jira:

- `SCRUM-16` — TASK-01: System gap analysis
- `SCRUM-17` — TASK-02: Prioritized gap fix/mitigation

The reviewed gap is:

- `AI-02` — The AI path does not yet have a complete fallback, evaluation, and cost-control gate for real LLM usage.

## 2. Kết quả hiện tại

Current Week 1 baseline uses a mock OpenAI-compatible LLM. The product page AI assistant returns a product-specific response, but the response matches the mock fixture.

This means Week 1 evidence proves:

- the deployed AI request path works;
- product page can call `product-reviews`;
- `product-reviews` can call the mock LLM service;
- Grafana/Jaeger access is available for baseline observation.

This evidence does not prove:

- real LLM integration readiness;
- real model answer quality;
- real LLM timeout/error behavior;
- token usage or cost tracking;
- faithfulness/hallucination performance.

Required gate before treating real LLM as production-like:

- timeout/error fallback behavior;
- 429/rate-limit handling;
- eval checklist and initial eval cases;
- response validation against product/review facts;
- token/cost metrics per request;
- observability for LLM latency/error/fallback.

Dependencies:

- CDO-08: review fallback behavior so LLM failure does not cascade into product page failures.
- CDO-04: review token/cost tracking metrics.
- CDO-07: verify evidence format and trace/log safety.

## 3. Bằng chứng nằm ở đâu?

Related Jira:

- TF4 Jira tổng: `SCRUM-16`, `SCRUM-17`
- AIO Jira private tracking: `TF4AIO-3`, `TF4AIO-11`, `TF4AIO-15`

Related Week 1 evidence:

- `docs/evidence/aio1-week1/evidence.md`
- `docs/evidence/aio1-week1/screenshots/ai-smoke-test-product-page.png`
- `docs/evidence/aio1-week1/screenshots/grafana-access.png`
- `docs/evidence/aio1-week1/screenshots/jaeger-access.png`

Related source areas:

- `techx-corp-platform/src/product-reviews/product_reviews_server.py`
- `techx-corp-platform/src/llm/app.py`
- `techx-corp-platform/src/llm/product-review-summaries/product-review-summaries.json`

## 4. Ghi chú / Follow-up

Week 1 output is baseline verification and readiness assessment.

Week 2 follow-up should:

1. add explicit timeout/error handling around the LLM call;
2. define safe fallback UX;
3. create a small reproducible eval set for summary faithfulness;
4. add token/cost tracking if real LLM is enabled;
5. capture Jaeger/Grafana evidence for AI latency, error, and fallback behavior.
