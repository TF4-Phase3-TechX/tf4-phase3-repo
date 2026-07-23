# AI / Tool Auditability — Mandate 14 Runtime Evidence

## Runtime evidence và canonical audit schema đề xuất

| Thuộc tính | Giá trị |
|---|---|
| Scope | Shopping Copilot và Product Q&A |
| Cluster | `techx-tf4-cluster` / namespace `techx-tf4` |
| Thời gian lấy mẫu | 2026-07-23 02:00–02:20 UTC (09:00–09:20 Asia/Saigon) |
| Nguồn | OpenSearch `otel-logs-*`, Prometheus, Jaeger |
| Kết quả request | Hai Bedrock `Converse` call timeout và fail-safe |

## Kết luận

Runtime tại thời điểm lấy mẫu có structured logs, metrics và distributed traces cho AI call. Từ structured log có thể lấy `trace_id` và truy đúng Jaeger trace tương ứng.

Snapshot live bên dưới được thu trước thay đổi canonical nên chưa có một event đủ tám field. PR này đã bổ sung code emit `ai_tool_audit` cho Bedrock Q&A, Copilot search và cart confirmation; deployment và live recapture vẫn còn pending. Evidence này chứng minh telemetry wiring và correlation, **không phải bằng chứng đóng Mandate 14**.

## 1. Structured log sample

![OpenSearch structured log runtime sample](assets/01-structured-log-runtime-sample.png)

Sample Q&A thực tế:

```text
timestamp:              2026-07-23T02:00:53.098937088Z
body:                   ai_assistant_completed
service:                product-reviews
trace_id:               ec1f8f0087cd980b7bdad98ba0daf39d
model_id:               us.amazon.nova-2-lite-v1:0
guardrail_version:      3
outcome:                unavailable
error_class:            timeout
provider_stop_reason:   not_received
input_tokens:           0
output_tokens:          0
estimated_cost_usd:     0
```

Privacy boundary đã kiểm tra:

- Không có raw prompt/query.
- Không có raw model response.
- Không có user ID hoặc session ID.
- Không có confirmation token.
- Log vẫn giữ model, guardrail, outcome, error và trace correlation.

Copilot search cũng sinh structured log:

```text
timestamp:   2026-07-23T02:00:25.607132160Z
body:        nl_search_provider_failure
trace_id:    0e23c597ddca0288b672e845103e9abf
error_class: timeout
```

## 2. Prometheus metrics sample

![Prometheus AI metrics runtime sample](assets/02-prometheus-ai-metrics-runtime-sample.png)

Các series đã query:

```promql
sum(increase(app_llm_calls_total{service_name="product-reviews"}[30m]))
sum(increase(app_llm_errors_total{service_name="product-reviews"}[30m]))
sum(increase(app_llm_prompt_tokens_total{service_name="product-reviews"}[30m]))
sum(increase(app_llm_completion_tokens_total{service_name="product-reviews"}[30m]))
sum(increase(app_llm_estimated_cost_usd_USD_total{service_name="product-reviews"}[30m]))
histogram_quantile(0.95, sum by (le) (rate(app_llm_latency_seconds_bucket{service_name="product-reviews"}[30m])))
```

`increase()` trả khoảng `1.04469` cho call/error do Prometheus extrapolate theo scrape boundary; đây là bằng chứng có activity, không được diễn giải thành request count chính xác. Token và cost bằng `0` vì provider timeout trước khi trả usage metadata. Thời lượng thực tế vẫn có trong Jaeger span.

## 3. Jaeger trace correlation

![Jaeger trace correlation runtime sample](assets/03-jaeger-trace-correlation-runtime-sample.png)

### Copilot search

```text
trace_id:                 0e23c597ddca0288b672e845103e9abf
surface:                  copilot_search
application operation:   search_products_ai
provider operation:      Bedrock Runtime/Converse
provider duration:       8049.5 ms
search outcome:           provider_failure
error class:              timeout
provider span status:     ERROR
```

### Product Q&A

```text
trace_id:                 ec1f8f0087cd980b7bdad98ba0daf39d
surface:                  product_qa
application operation:   get_ai_assistant_response
provider operation:      Bedrock Runtime/Converse
provider duration:       8063.3 ms
model:                    us.amazon.nova-2-lite-v1:0
guardrail version:        3
application outcome:      unavailable
provider span status:     ERROR
```

## 4. Coverage theo schema CDO-07 yêu cầu

| Field canonical | Live snapshot trước thay đổi | Implementation trong PR |
|---|---|---|
| `log_type` | Body là `ai_assistant_completed` hoặc `nl_search_provider_failure`. | Emit cố định `ai_tool_audit`. |
| `trace_id` | Có tại `attributes.otelTraceID`, truy được đúng Jaeger trace. | Alias W3C trace hiện tại thành `trace_id`. |
| `surface` | Có tại span `app.caller.feature`. | Emit trực tiếp `product_qa`, `copilot_search` hoặc `shopping_copilot`. |
| `model_id` | Có tại log và `gen_ai.request.model`. | Emit model ID; business tool không dùng model ghi `not_applicable`. |
| `tool_name` | Converse mới nằm ở span operation. | Emit `bedrock.converse` hoặc `modify_cart`. |
| `tool_input_redacted` | Raw input được loại bỏ nhưng chưa có marker. | Emit `{"redacted": true, "content_logged": false}`; helper không nhận raw content. |
| `safety_decision` | Tách thành outcome/error/guardrail. | Giới hạn `allow/block/refuse/provider_unavailable`. |
| `confirmation_status` | Chỉ có cart outcome trên span. | Giới hạn `not_required/confirmed/rejected`. |

## 5. Canonical event đã implement

```json
{
  "log_type": "ai_tool_audit",
  "trace_id": "ec1f8f0087cd980b7bdad98ba0daf39d",
  "surface": "product_qa",
  "model_id": "us.amazon.nova-2-lite-v1:0",
  "tool_name": "bedrock.converse",
  "tool_input_redacted": {
    "redacted": true,
    "content_logged": false
  },
  "safety_decision": "provider_unavailable",
  "confirmation_status": "not_required"
}
```

Đối với tool có business mutation, `confirmation_status` độc lập với model output. Model chỉ được đề xuất; application confirmation boundary mới được execute action. Nếu downstream cart write lỗi sau khi user đã confirm, audit vẫn ghi `confirmed`; operational log riêng giữ execution failure.

Implementation:

- `audit_logging.py` sở hữu schema, bounded vocabularies, trace alias và redaction marker.
- Q&A và Copilot search chỉ emit `bedrock.converse` khi provider thực sự được attempt.
- Cart confirmation emit `modify_cart` với `confirmed` hoặc `rejected`; không log confirmation token.
- Unit/integration suite kiểm tra exact eight-field event, enum validation, safety mapping và cart transitions.

## 6. Boundary và next actions

1. Sample này chứng minh provider-failure telemetry và log-to-trace correlation; chưa chứng minh successful model response hoặc successful tool execution.
2. Merge/deploy canonical logger, sau đó query OpenSearch để chứng minh đủ tám field trên event thật.
3. Lấy thêm một successful Bedrock sample khi provider ổn định để có token, cost, stop reason và safety decision đầy đủ.
4. Lấy thêm cart confirmation sample để chứng minh `confirmed/rejected` transition mà không log confirmation token.
5. Chốt với CDO-07 về retention và access control trước khi đóng Mandate 14.

## 7. Runtime caveat tại thời điểm lấy mẫu

- Stable pod `product-reviews-6576656b6b-m9bl6` vẫn Ready và phục vụ request.
- Pod rollout mới `product-reviews-8cf7dd5c8-dtjth` không Ready do không kết nối được Valkey; đây là blocker riêng, không được che trong audit evidence.
- Các Job probe chỉ đọc đã được xóa sau khi thu evidence; không còn Job `tf4-ai-audit-*` trong namespace.

## 8. Raw evidence files

- [`runtime-probe-2026-07-23.json`](runtime-probe-2026-07-23.json)
- [`runtime-traces-2026-07-23.json`](runtime-traces-2026-07-23.json)
