# [AUDIT-011] Yêu cầu bổ sung 3 Grafana dashboard theo business flow chính

**Trạng thái**: TO DO  
**Người yêu cầu (Reporter)**: Trần Minh Quang - Nhóm CDO07 (Audit)  
**Người thực hiện (Assignee)**: Nhóm CDO07 (Auditability / OBS-01 owner)  
**Nhóm phối hợp**: Nhóm CDO04 (Observability/Platform, nếu cần triển khai Grafana/Helm), Nhóm CDO08 (Reliability/SLO threshold), Nhóm AIO01 (AI signal cho review + AI flow)  
**Độ ưu tiên (Priority)**: P0 (Blocker nghiệm thu OBS-01 / SLO dashboard evidence)  
**Epic**: EPIC-01 / OBS-01 - Observability baseline

---

## 1. Bối cảnh (Context)

Theo `docs/requirements/onboarding/ARCHITECTURE.md`, hệ thống có 5 business flow chính:

- Duyệt sản phẩm: `frontend` -> `product-catalog` + `recommendation` + `ad`.
- Trang sản phẩm review + AI: `frontend` -> `product-reviews` -> `postgresql` + `llm`.
- Giỏ hàng: `frontend` -> `cart` -> `valkey-cart`.
- Đặt hàng: `frontend` -> `checkout` -> `cart` + `product-catalog` + `currency` + `shipping/quote` + `payment` + `email` -> `Kafka`.
- Sau đặt hàng async: `Kafka` -> `accounting`, `fraud-detection`.

Hiện Grafana đã có datasource và dashboard nền tảng:

- Prometheus datasource: `webstore-metrics`.
- Jaeger datasource: `webstore-traces`.
- OpenSearch datasource: `webstore-logs`.
- Dashboard hiện có chủ yếu là APM/service-level, spanmetrics, PostgreSQL, flash-sale verification và alert state.

Các dashboard hiện tại giúp xem service health tổng quát, nhưng chưa có dashboard riêng theo business flow để CDO07 nghiệm thu OBS-01 theo góc nhìn vận hành/SLO. Đặc biệt, các flow revenue-critical và AI-critical cần dashboard riêng để theo dõi sức khỏe hệ thống, phát hiện lỗi sớm và lưu evidence cho Ops Review.

## 2. Yêu cầu bổ sung dashboard (The What)

Đề nghị bổ sung 3 Grafana dashboard sau vào provisioning của repo, ưu tiên đặt dưới:

`techx-corp-chart/grafana/provisioning/dashboards/`

### 2.1 Business Flow Health Overview

**Mục đích**: Dashboard tổng quan cho 5 business flow chính, giúp CDO07/mentor nhìn nhanh flow nào đang khỏe, flow nào đang vi phạm SLO hoặc có dấu hiệu suy giảm.

Panel cần có:

- Flow status table cho 5 flow: browse, product review + AI, cart, checkout, post-checkout async.
- Success rate theo flow.
- Request rate / throughput theo flow.
- p95/p99 latency theo flow.
- Error rate theo flow.
- Active alerts liên quan SLO/OBS-01 từ Prometheus/Grafana alert state.
- Pod availability/restart/OOM của các service nằm trên critical path.
- Link/drilldown sang Jaeger trace và OpenSearch logs theo service/flow.

Gợi ý metric/query:

- Dùng `traces_span_metrics_calls_total` để tính request volume và error rate theo `service_name`, `span_name`, `status_code`.
- Dùng `traces_span_metrics_duration_milliseconds_bucket` để tính p95/p99 latency.
- Dùng `ALERTS` hoặc alert state metric tương đương để hiển thị alert đang firing.
- Dùng Kubernetes metrics cho pod readiness/restart/OOM nếu Prometheus đã scrape được.

### 2.2 Checkout Revenue Dashboard

**Mục đích**: Dashboard chuyên theo dõi revenue-critical path, vì checkout là flow trực tiếp ảnh hưởng doanh thu và SLO `checkout >= 99%`.

Panel cần có:

- Checkout success rate cho endpoint/operation checkout.
- Checkout request volume theo thời gian.
- Checkout p95/p99 latency.
- Checkout error rate theo loại lỗi nếu label available.
- Dependency latency/error breakdown cho: `cart`, `product-catalog`, `currency`, `shipping`, `quote`, `payment`, `email`, `Kafka`.
- Payment success/error/latency.
- Shipping/quote latency/error.
- Kafka publish/order event signal nếu metric available.
- Accounting/fraud consumer health hoặc lag nếu Kafka metrics available.
- Resource health của các pod revenue-critical: `frontend`, `checkout`, `cart`, `payment`, `product-catalog`, `currency`, `shipping`, `quote`, `email`, `kafka`, `accounting`, `fraud-detection`.

Gợi ý metric/query:

- Ưu tiên span/metric của `checkout` service và frontend operation `POST /api/checkout` nếu label có sẵn.
- Dùng spanmetrics để tách latency/error theo downstream service.
- Nếu Kafka lag/publish metric chưa available, dashboard phải ghi rõ panel `No data` và tạo note gap để xử lý ở ticket/PR khác.

### 2.3 Product Review + AI Dashboard

**Mục đích**: Dashboard theo dõi flow AI trọng tâm của sản phẩm, bảo vệ yêu cầu "AI summary best-effort nhưng không được hiển thị tóm tắt sai lệch".

Panel cần có:

- Request volume của `product-reviews`.
- Error rate của các operation review và AI, ví dụ `GetProductReviews`, `GetAverageProductReviewScore`, `AskProductAIAssistant` nếu label available.
- p95/p99 latency của `product-reviews`.
- LLM request volume, latency, error/rate-limit nếu metric available.
- AI fallback/timeout/error count nếu app đã emit metric hoặc có log tương ứng.
- PostgreSQL latency/error liên quan review query.
- OpenSearch log panel lọc theo `product-reviews` và `llm` cho các keyword: `error`, `timeout`, `fallback`, `rate limit`, `inaccurate`.
- Link/drilldown sang Jaeger trace cho flow review + AI.

Gợi ý metric/query:

- Dùng `traces_span_metrics_*` cho `product-reviews` và `llm`.
- Dùng OpenSearch datasource `webstore-logs` cho log evidence khi metric AI-specific chưa đủ.
- Nếu các metric AI-specific như fallback/rate-limit/token/cost chưa tồn tại, dashboard phải ghi chú rõ đây là instrumentation gap để AIO01 xác nhận hướng bổ sung.

## 3. Ranh giới trách nhiệm

- CDO07 owns OBS-01 measurement/evidence: xác nhận dashboard tồn tại, query hoạt động, evidence đủ phục vụ Ops Review và nghiệm thu.
- CDO04 owns phần Observability/Platform implementation nếu cần sửa Helm/Grafana provisioning, ConfigMap hoặc datasource linkage.
- CDO08 provides input cho reliability threshold, đặc biệt checkout/payment/Kafka/DB và các panel SLO.
- AIO01 provides input cho AI-specific signals: fallback, timeout, rate-limit, token/cost, quality/eval signal nếu có.

Ticket này chỉ yêu cầu dashboard/query/evidence. Việc bổ sung alert rule hoặc instrumentation mới có thể tách thành ticket/PR riêng nếu phát hiện metric chưa tồn tại.

## 4. Tiêu chí nghiệm thu (Acceptance Criteria / Evidence)

- [ ] Có 3 dashboard JSON được provision trong Grafana:
  - `Business Flow Health Overview`
  - `Checkout Revenue Dashboard`
  - `Product Review + AI Dashboard`
- [ ] Dashboard dùng datasource UID hiện có: `webstore-metrics`, `webstore-traces`, `webstore-logs`.
- [ ] Dashboard được render qua Helm/Grafana provisioning hiện tại, không cần build lại application image.
- [ ] Mỗi dashboard có panel success rate, request rate, p95/p99 latency và error rate phù hợp với flow.
- [ ] Checkout dashboard thể hiện được dependency path của checkout và các tín hiệu payment/Kafka/DB quan trọng, hoặc ghi rõ metric gap nếu chưa có data.
- [ ] Product Review + AI dashboard thể hiện được health của `product-reviews`, `llm`, PostgreSQL review query và log/trace evidence cho lỗi AI, hoặc ghi rõ metric gap nếu chưa có data.
- [ ] Business Flow Health Overview cho phép nhìn nhanh trạng thái 5 flow chính từ một màn hình.
- [ ] Có screenshot hoặc link dashboard sau deploy để CDO07 lưu evidence vào `006-obs-01-slo-alert-dashboard-baseline.md`.
- [ ] Nếu panel nào `No data`, phải có ghi chú rõ do hệ thống không phát sinh traffic hay do thiếu instrumentation/metric.

## 5. Ghi chú implementation

- Ưu tiên tái sử dụng PromQL/spanmetrics đang có trong các dashboard hiện tại để tránh tạo query style mới không cần thiết.
- Không dùng dashboard thay thế alerting. Dashboard phục vụ quan sát và evidence; cảnh báo sự cố vẫn cần Prometheus/Grafana alert rules và receiver riêng.
- Nếu chỉ thay đổi dashboard JSON/Helm config, không cần build lại image. Chỉ cần render/apply Helm chart hoặc apply ConfigMap tương ứng theo quy trình deploy của team.
- Tránh hardcode namespace nếu dashboard hiện tại đã có biến namespace/service; nếu cần hardcode tạm `techx-tf4`, phải ghi rõ trong dashboard variable hoặc mô tả panel.

*(Sau khi hoàn thành, vui lòng tag CDO07 để nghiệm thu dashboard và lưu evidence OBS-01.)*
