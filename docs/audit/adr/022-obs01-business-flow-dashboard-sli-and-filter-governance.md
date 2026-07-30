# ADR-022: Chuẩn hóa 3 OBS-01 Grafana dashboards theo request-level SLI, filter và evidence semantics

- **Ngày:** 2026-07-30
- **Trạng thái:** Accepted - source implemented, runtime verification sau GitOps sync
- **Tác giả:** Trần Minh Quang - CDO07
- **Người review:** TF4 leads, CDO08
- **Pillar liên quan:** Observability, Reliability, Auditability
- **Task:** OBS-01 - Bổ sung và chuẩn hóa dashboard theo business flow chính
- **Scope:** `techx-corp-chart/grafana/provisioning/dashboards/`

## 1. Bối cảnh

OBS-01 yêu cầu CDO07 bổ sung dashboard Grafana theo các luồng nghiệp vụ chính để theo dõi SLO/health và thu thập evidence nghiệm thu. Ba dashboard chính đã được triển khai:

- `Business Flow Health Overview`
- `Checkout Revenue Dashboard`
- `Product Review + AI Dashboard`

Sau khi sử dụng runtime, team phát hiện một số điểm dễ gây hiểu nhầm:

- Một số panel hiện `No data` khi filter theo service, dù trong nhiều trường hợp đây chỉ là "không có request/error series" chứ không phải dashboard hỏng.
- Error panel chỉ query `status_code="STATUS_CODE_ERROR"` nên khi không có lỗi có thể hiện `No data`, dễ bị hiểu nhầm là mất metric.
- Dashboard Product Review + AI đang làm mờ ranh giới giữa request-level SLI và span-level debug metrics.
- Tên `LLM` gây hiểu nhầm rằng AI production path đi qua deployment `llm`, trong khi source code hiện tại cho thấy Product Detail AI production path là `product-reviews -> Bedrock`.
- Service `llm` có thể tồn tại trong cluster nhưng là auxiliary service, không nằm trên primary AI production path.

## 2. Quyết định

Chuẩn hóa 3 dashboard OBS-01 theo các nguyên tắc sau:

1. Dashboard phải phân biệt rõ **request-level SLI**, **span-level debug**, **infra health**, **logs** và **alerts**.
2. Filter được bổ sung/tinh chỉnh để drill-down theo service/component, nhưng không được làm sai ý nghĩa của panel.
3. Panel SLI phải đo request/business operation chính, tránh double-count child spans như Bedrock/tool/DB.
4. Error panel nếu có traffic nhưng không có error series thì hiện `0 req/s` thay vì `No data`.
5. `No data` phải được diễn giải rõ: không có traffic, không có metric trong time range, hoặc filter đang chọn service không thuộc flow/panel đó.
6. Product Review + AI Dashboard phải trình bày AI production path là `product-reviews -> Bedrock`, không coi deployment `llm` là primary path.

## 3. Dashboard-level decisions

### 3.1. Business Flow Health Overview

Quyết định:

- Giữ dashboard là overview cho 5 flow chính: browse, product review + AI, cart, checkout, post-checkout async.
- Bổ sung/tinh chỉnh filter theo service để hỗ trợ drill-down.
- Nếu một service không phải entry point của flow hoặc không có error series, panel có thể `No data`; đây không mặc định là lỗi.
- Các panel error rate cần diễn giải rõ `No data` khác `0% success`.

Hệ quả:

- Khi filter `product-catalog`, `currency`, `quote`, `email` ở một số panel, `No data` có thể hợp lệ nếu query đang đo request/error series không phát sinh cho service đó.
- Dashboard không nên ép hiện `0` cho missing metric nếu việc đó làm sai evidence semantics.

### 3.2. Checkout Revenue Dashboard

Quyết định:

- Dashboard tiếp tục theo dõi checkout success rate, request volume, p95/p99 latency, error rate và dependency path.
- Dependency path gồm cart, product-catalog, currency, shipping/quote, payment, email và Kafka/post-checkout async.
- Phần sync checkout và post-checkout async phải được đặt tên rõ để tránh hiểu nhầm email/Kafka là thành phần nằm trong critical payment path.

Hệ quả:

- Checkout/payment SLI không bị phá bởi các async dependency nếu panel đang đo luồng sync.
- Vẫn có debug evidence cho post-checkout async flow khi cần điều tra accounting/email/Kafka.

### 3.3. Product Review + AI Dashboard

Quyết định:

- Đổi cách trình bày AI từ `LLM` chung chung sang `Product Reviews / Bedrock`.
- Request-level panels chỉ tính ProductReviewService request spans:
  - `get_product_reviews`
  - `get_average_product_review_score`
  - `get_ai_assistant_response`
  - `search_products_ai`
  - hoặc các gRPC server spans tương ứng của `ProductReviewService`.
- Bedrock-specific panels dùng span `bedrock.converse` phát ra từ `product-reviews`.
- `Review + AI Span Breakdown` là debug view, có thể gồm child spans như Bedrock/tool/DB và không dùng làm request-level SLI.
- Deployment `llm` được ghi rõ là auxiliary service; nó có thể có deployment availability/restarts nhưng không có request/latency/error data nếu không nằm trên primary path.
- Log panel mở rộng keyword timeout/deadline/throttling/AccessDenied/Bedrock và sort mới nhất trước để phục vụ audit nhanh hơn.

Hệ quả:

- Hai panel cũ `LLM Success Rate` và `LLM Latency` không còn gây hiểu nhầm là đo traffic của deployment `llm`.
- Bedrock signal được đọc đúng theo source code hiện tại: `product-reviews -> Bedrock`.
- Nếu filter `llm` và thấy `No data`, đây có thể là trạng thái hợp lệ vì `llm` không phải primary AI production path.

## 4. Lý do

| Lý do | Giải thích |
|---|---|
| SLI phải đo đúng tầng | Request-level SLI không nên gom child span, vì sẽ double-count và làm sai success/rate/latency. |
| Evidence semantics rõ ràng | `No data`, `0 req/s`, `0%` và "không có lỗi" là các trạng thái khác nhau. |
| Phù hợp source code | Product Detail AI production path hiện tại là `product-reviews -> Bedrock`, không phải deployment `llm`. |
| Hỗ trợ audit nhanh | Filter, logs và span breakdown giúp drill-down nhưng vẫn giữ SLI chính gọn và đáng tin. |
| Giảm hiểu nhầm với stakeholder | Dashboard cần dễ giải thích cho mentor/sếp trong incident/drill, không chỉ để nhìn đẹp. |

## 5. Alternatives considered

| Phương án | Kết luận | Lý do |
|---|---|---|
| Giữ nguyên dashboard cũ | Không chọn | Dễ tiếp tục gây hiểu nhầm về LLM, No data và request/span metrics. |
| Ép fallback `0` cho mọi missing series | Không chọn | Có thể che lấp việc metric chưa tồn tại hoặc service không thuộc flow. |
| Bỏ service `llm` khỏi dashboard | Không chọn hoàn toàn | Vẫn cần theo dõi infra health của `llm`, nhưng phải ghi rõ nó là auxiliary. |
| Tách request-level SLI và span-level debug | Chọn | Đúng với cách vận hành và forensic evidence. |

## 6. Consequences

### Tích cực

- Dashboard dễ đọc hơn khi dùng cho incident report và audit evidence.
- Request-level SLI đáng tin cậy hơn vì không double-count child spans.
- Product Review + AI Dashboard phản ánh đúng AI path hiện tại.
- Error panel giảm nhầm lẫn giữa "không có lỗi" và "không có metric".

### Trade-off / Giới hạn

- Query dài và phức tạp hơn, cần validate sau mỗi lần instrumentation thay đổi.
- Một số filter service vẫn có thể `No data` nếu service đó không thuộc panel/flow đang đo.
- `app_llm_*` vẫn là metric contract trong source code, nhưng dashboard hiện ưu tiên span `bedrock.converse` khi đây là signal đang có trên Grafana.
- Grafana dashboard không thay thế alert rule; alert vẫn cần được quản lý riêng trong Prometheus/Grafana alerting.

## 7. Validation

Validation local cho dashboard update:

- JSON parse pass bằng `ConvertFrom-Json`.
- `helm template techx-corp .\techx-corp-chart -n techx-observability` pass.
- ConfigMap render có các panel mới:
  - `Product Reviews API Success Rate`
  - `Product Reviews API Request Rate`
  - `Product Reviews API Error Rate`
  - `Product Reviews API Latency`
  - `Product Reviews / Bedrock Success Rate`
  - `Product Reviews / Bedrock Latency`
  - `Review + AI Span Breakdown`

Validation runtime sau GitOps sync:

```powershell
kubectl get cm -n techx-observability | Select-String "grafana-dashboard"
```

Kiểm tra trong Grafana:

- Filter `All` và từng service/component.
- Product Review + AI không còn title `LLM Success Rate` / `LLM Latency`.
- Error panel hiện `0 req/s` khi có traffic nhưng không có error.
- Bedrock panels có data khi có span `bedrock.converse` trong selected time range.

## 8. Rollback

Rollback source:

- Revert commit/PR thay đổi các dashboard OBS-01.
- Riêng Product Review + AI SLI fix có commit:
  `c6cfdb7 fix(cdo07): clarify product review ai dashboard sli`

Rollback GitOps/runtime:

- Revert GitOps promotion PR hoặc đưa chart `targetRevision` về SHA trước đó.
- Nếu từng apply bằng Helm thủ công, dùng `helm rollback` về revision trước.

Rủi ro runtime thấp vì thay đổi chỉ nằm trong Grafana dashboard JSON/ConfigMap:

- Không rebuild image.
- Không sửa app code.
- Không đổi Kubernetes workload runtime.

## 9. References

- ADR-015: `docs/audit/adr/015-business-flow-grafana-dashboards.md`
- Dashboard files:
  - `techx-corp-chart/grafana/provisioning/dashboards/business-flow-health-overview.json`
  - `techx-corp-chart/grafana/provisioning/dashboards/checkout-revenue-dashboard.json`
  - `techx-corp-chart/grafana/provisioning/dashboards/product-review-ai-dashboard.json`
- Commit `c6cfdb7`: `fix(cdo07): clarify product review ai dashboard sli`
- GitOps promotion PR: `chore(gitops): promote c6cfdb7`
- Source evidence:
  - `techx-corp-platform/src/product-reviews/product_reviews_server.py`
  - `techx-corp-platform/src/product-reviews/llm_observability.py`
  - `techx-corp-platform/src/product-reviews/ai_assistant.py`
