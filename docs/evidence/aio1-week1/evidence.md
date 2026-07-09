# AIO01 Week 1 Evidence — AI Baseline Verification

## 1. Scope

Evidence này dùng để xác nhận phần AI baseline của TF4 đã chạy trên môi trường EKS Week 1.

Mục tiêu không phải chứng minh real LLM đã được tích hợp, mà là xác nhận:

- storefront gọi được AI assistant trên product page;
- `product-reviews` có telemetry trong Jaeger;
- Grafana/Jaeger public access hoạt động;
- AI response hiện tại là mock LLM baseline, không phải real LLM.

---

## 2. Environment

| Item | Value |
|---|---|
| Environment | TF4 EKS baseline |
| App/Product URL tested | `http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/product/0PUK6V6EV0` |
| Grafana URL | `http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/grafana/dashboards` |
| Jaeger URL | `http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/jaeger/ui/search` |
| Product ID tested | `0PUK6V6EV0` |
| Question tested | `Can you summarize the product reviews?` |

---

## 3. Evidence files

| Evidence | File |
|---|---|
| AI response on product page | [`screenshots/ai-smoke-test-product-page.png`](./screenshots/ai-smoke-test-product-page.png) |
| Grafana access | [`screenshots/grafana-access.png`](./screenshots/grafana-access.png) |
| Jaeger access with `product-reviews` service | [`screenshots/jaeger-access.png`](./screenshots/jaeger-access.png) |

---

## 4. Result

AI assistant trả response thành công trên product page `0PUK6V6EV0`.

Observed response:

```txt
This solar system color imager is highly praised as an excellent solution for both beginners and serious planetary observers looking to capture stunning, vibrant images of planets like Saturn and Jupiter. Users commend its superb color quality, excellent resolution, and straightforward setup, making astrophotography accessible.
```

Kết luận:

```txt
AI request path is functional on TF4 EKS baseline with the current mock OpenAI-compatible LLM.
```

---

## 5. Mock LLM confirmation

Response trên UI khớp với hard-coded fixture trong source:

```txt
techx-corp-platform/src/llm/product-review-summaries/product-review-summaries.json
```

Entry tương ứng:

```json
{
  "product_id": "0PUK6V6EV0",
  "average_score": 4.6,
  "product_review_summary": "This solar system color imager is highly praised as an excellent solution for both beginners and serious planetary observers looking to capture stunning, vibrant images of planets like Saturn and Jupiter. Users commend its superb color quality, excellent resolution, and straightforward setup, making astrophotography accessible."
}
```

Mock LLM implementation:

```txt
techx-corp-platform/src/llm/app.py
```

The mock LLM exposes an OpenAI-compatible endpoint:

```txt
/v1/chat/completions
/v1/models
```

Therefore, this evidence confirms the deployed AI baseline path works, but it does not prove real LLM integration, real model quality, real latency, or real token/cost behavior.

---

## 6. Source flow confirmed from repo

Current AI flow:

```txt
Browser
  -> frontend product page
  -> frontend API route: /api/product-ask-ai-assistant/[productId]
  -> ProductReviewService.askProductAIAssistant
  -> gRPC ProductReviewServiceClient.askProductAiAssistant
  -> product-reviews AskProductAIAssistant
  -> OpenAI-compatible client using LLM_BASE_URL
  -> llm mock service
```

Relevant files:

```txt
techx-corp-platform/src/frontend/pages/api/product-ask-ai-assistant/[productId]/index.ts
techx-corp-platform/src/frontend/providers/ProductAIAssistant.provider.tsx
techx-corp-platform/src/frontend/gateways/rpc/ProductReview.gateway.ts
techx-corp-platform/src/product-reviews/product_reviews_server.py
techx-corp-platform/src/llm/app.py
```

---

## 7. Observability evidence

### Grafana

Grafana public URL is accessible:

```txt
http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/grafana/dashboards
```

Evidence file:

```txt
docs/evidence/aio1-week1/screenshots/grafana-access.png
```

Confirmed:

- Grafana UI loads successfully.
- Dashboards are available through public ALB/frontend-proxy route.

### Jaeger

Jaeger public URL is accessible:

```txt
http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/jaeger/ui/search
```

Evidence file:

```txt
docs/evidence/aio1-week1/screenshots/jaeger-access.png
```

Confirmed:

- Jaeger UI loads successfully.
- Service list includes `product-reviews`.

Limitation:

```txt
Request-level trace for the exact Ask AI click has not been captured yet in this evidence note.
```

---

## 8. Findings / gaps

| Finding | Impact | Follow-up |
|---|---|---|
| Current AI response comes from mock LLM fixture | Real model quality is not validated | Keep as Week 1 baseline; evaluate real LLM later |
| Real LLM latency/cost/token usage not measured | Cannot defend production model cost/performance yet | Add AI cost/latency metrics before real rollout |
| No eval result for summary faithfulness yet | Cannot quantify hallucination or summary quality | Build eval cases and reproducible script |
| LLM failure behavior needs validation | Real LLM timeout/rate-limit may degrade product page | Test fallback with `llmRateLimitError` and real error scenarios |
| AI-specific observability is incomplete | Hard to separate LLM latency/errors from product page latency | Add/request metrics/log fields for AI path |
| Request-level AI trace not captured in this note | Trace evidence is partial | Capture Jaeger trace for `AskProductAIAssistant` if available |

---

## 9. Week 1 decision

Decision:

```txt
Keep mock LLM for Week 1 baseline evidence.
```

Reason:

- Week 1 priority is baseline deployment, discovery, assessment, evidence, backlog and pitch.
- Real LLM integration is optional in `values-aio-llm.yaml`, not mandatory for Week 1.
- Real LLM rollout should happen after eval, fallback, observability and cost plan are defined.

Follow-up:

```txt
Week 2 should prioritize AI eval, fallback/timeout handling, guardrails, and AI-specific observability before enabling real LLM as a scored production-like path.
```

---

## 10. Summary for Jira / Week 1 Pitch

```txt
AIO01 verified that the AI assistant path works on the TF4 EKS baseline for product 0PUK6V6EV0. The UI returns a product-specific AI response, Grafana is accessible, and Jaeger shows product-reviews telemetry.

However, the response matches the mock LLM fixture in src/llm/product-review-summaries/product-review-summaries.json. Therefore this is valid mock LLM baseline evidence, not real LLM quality/cost/latency evidence.

Next priorities are eval, fallback/timeout handling, guardrails, and AI-specific observability before enabling or claiming real LLM integration.
```
