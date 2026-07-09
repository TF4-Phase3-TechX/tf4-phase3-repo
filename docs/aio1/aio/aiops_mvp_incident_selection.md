# AIOPS-03: Lựa chọn Loại Incident cho AIOps MVP

**Epic liên quan:** EPIC-AIOPS-01 — AIOps Discovery & Data Foundation  
**Chủ sở hữu đầu ra:** AIO01  
**Trạng thái:** In Review — Đã chọn xong loại incident MVP; runtime signal validation thực hiện ở Week 2

---

## 1. Phương pháp lựa chọn

Mỗi ứng viên được chấm điểm theo 4 chiều, thang 1–3 (3 = tốt nhất):

| Chiều đánh giá | Định nghĩa |
|---|---|
| **Sẵn sàng tín hiệu** | Các metric/log/trace cần thiết đã được hệ thống phát ra mà không cần thay đổi code? |
| **Chất lượng bằng chứng** | AIOps có thể chứng minh phát hiện bằng artifact cụ thể, có thể tái tạo (trace ID, dòng log, đồ thị metric)? |
| **Giá trị demo** | Loại incident có ánh xạ trực tiếp vào luồng nghiệp vụ quan trọng (SLO, doanh thu, an toàn AI)? |
| **Khả năng kích hoạt** | Có thể tái tạo incident này theo cách có kiểm soát (feature flag, load-gen, chaos) để xác thực detector? |

---

## 2. So sánh các ứng viên

### Ứng viên A — LLM Timeout / Lỗi

**Mô hình incident:** `product-reviews` gọi `llm` qua HTTP; LLM trả về 429, ném exception, hoặc treo vô thời hạn gây cạn kiệt gRPC thread.

| Chiều đánh giá | Điểm | Bằng chứng |
|---|---|---|
| Sẵn sàng tín hiệu | **3** | Source đã có đường ghi exception vào span: [`product_reviews_server.py:L194-L200`](../../../techx-corp-platform/src/product-reviews/product_reviews_server.py#L194-L200). Metric `app_ai_assistant_counter` có trong code path. Week 2 cần xác minh live query qua Jaeger/OpenSearch/Prometheus trước khi claim detector chạy thật. |
| Chất lượng bằng chứng | **3** | Feature flag `llmRateLimitError` do BTC/CDO kiểm soát ([`product_reviews_server.py:L164`](../../../techx-corp-platform/src/product-reviews/product_reviews_server.py#L164)) có thể tạo luồng 429 khi được bật bởi owner của flag. AIO chỉ đọc telemetry; không tự sửa `flagd`. |
| Giá trị demo | **3** | Ánh xạ trực tiếp vào AI Safety SLO: *"không được hiển thị tóm tắt sai lệch"* ([`SLO.md`](../../requirements/onboarding/SLO.md#L13)). Cũng kích hoạt rủi ro cạn kiệt `gRPC ThreadPoolExecutor` (`max_workers=10`, [`product_reviews_server.py:L361`](../../../techx-corp-platform/src/product-reviews/product_reviews_server.py#L361)). Câu chuyện cho PM: *"AI hỏng, đây là cách chúng ta phát hiện."* |
| Khả năng kích hoạt | **3** | Có trigger kiểm soát nếu BTC/CDO bật flag trong khung test. AIO xác minh bằng request đọc và telemetry evidence; detector không thay đổi cluster/flag/service traffic. |
| **Tổng** | **12 / 12** | |

---

### Ứng viên B — Latency Spike (Đột biến độ trễ)

**Mô hình incident:** Một microservice (ví dụ `product-reviews`, `checkout`) cho thấy độ trễ p95/p99 tăng cao. Nguyên nhân phổ biến nhất: cạn kiệt connection pool DB (mô hình INC-1) hoặc downstream call bị chờ.

| Chiều đánh giá | Điểm | Bằng chứng |
|---|---|---|
| Sẵn sàng tín hiệu | **3** | Code/deploy path dùng OTel auto-instrumentation (`opentelemetry-instrument` trong [`Dockerfile`](../../../techx-corp-platform/src/product-reviews/Dockerfile#L31)) và histogram bucket đã được cấu hình trong chart ([`values.yaml:L1016-L1019`](../../../techx-corp-chart/values.yaml#L1016-L1019)). Week 2 cần xác minh metric label thực tế trong Prometheus trước khi khóa query detector. |
| Chất lượng bằng chứng | **2** | Có thể đọc từ Prometheus qua PromQL (ví dụ: `histogram_quantile(0.95, sum by (le) (rate(rpc_server_duration_milliseconds_bucket{service_name="product-reviews"}[5m])))`) và đối chiếu span trong Jaeger UI/API. `load-generator` nằm trong kiến trúc baseline ([`ARCHITECTURE.md:L32`](../../requirements/onboarding/ARCHITECTURE.md#L32)). Điểm -1 vì latency spike cần baseline window trước. |
| Giá trị demo | **3** | INC-1 ([`INCIDENT_HISTORY.md:L9-L15`](../../requirements/onboarding/INCIDENT_HISTORY.md#L9-L15)) cho thấy mô hình này đã xảy ra: latency checkout khiến success rate xuống 95% (dưới SLO 99%). SRE lead và CFO đều quan tâm: "Chúng ta có thể thấy trước khi SLO burn không?" |
| Khả năng kích hoạt | **2** | `load-generator` cung cấp tín hiệu traffic liên tục. Để tạo đột biến nhân tạo cần tạm thời tăng concurrency của load-gen hoặc chạy locust script. Cần phối hợp với CDO để tránh SLO burn ngoài ý muốn. Điểm -1 do phụ thuộc vào phối hợp. |
| **Tổng** | **10 / 12** | |

---

### Ứng viên C — Error Rate Spike (Đột biến tỷ lệ lỗi)

**Mô hình incident:** Một service trả về liên tục các HTTP 4xx/5xx hoặc gRPC status code không phải OK.

| Chiều đánh giá | Điểm | Bằng chứng |
|---|---|---|
| Sẵn sàng tín hiệu | **2** | `rpc_server_duration_milliseconds_count{rpc_grpc_status_code!="0"}` có sẵn trong Prometheus. Tuy nhiên, một số service dùng HTTP routing qua Envoy (`frontend-proxy`) nên phát hiện HTTP 5xx cũng cần `http_server_request_duration_seconds_count{http_response_status_code=~"5.."}` — cần xác minh label trong live cluster. |
| Chất lượng bằng chứng | **2** | Trong baseline ổn định với load-gen chạy, error rate gần bằng không, tín hiệu rất rõ ràng. Nhưng để *tạo ra* một error burst có kiểm soát (mà không dùng flag) cần cấu hình sai có chủ đích hoặc kill pod — gây rối hơn nhiều so với luồng LLM flag. |
| Giá trị demo | **2** | Dù quan trọng, error rate spike là *hệ quả* của latency hoặc LLM failure — không phải loại incident độc lập ở tầm MVP. Nó phần lớn trùng lặp với Ứng viên A (LLM error) và Ứng viên B (latency → timeout → error). Giá trị AIOps bổ sung thêm là nhỏ nếu đứng độc lập. |
| Khả năng kích hoạt | **1** | Tạo lỗi có kiểm soát mà không dùng BTC flag là rủi ro (có thể burn SLO budget). Dựa vào BTC để trigger error thì lại trùng lặp với Ứng viên A (luồng LLM). Không có trigger độc lập sạch nào ở phạm vi MVP mà không cần quyền truy cập flag. |
| **Tổng** | **7 / 12** | |

---

## 3. Quyết định lựa chọn MVP

| Hạng | Loại incident | Điểm | Quyết định | Lý do |
|---|---|---|---|---|
| 1 | **LLM Timeout / Lỗi** | 12/12 | **MVP — Tuần 2** | Sẵn sàng tín hiệu cao nhất theo source/config review. BTC/CDO flag cung cấp trigger có thể lặp lại nếu được owner bật trong khung test. Thể hiện trực tiếp AI Safety monitoring — câu chuyện có giá trị nhất của AIO01. |
| 2 | **Latency Spike** | 10/12 | **MVP — Tuần 2** | Bao phủ mô hình lịch sử INC-1. Candidate Prometheus histogram path đã được xác định. Gắn latency detection trực tiếp với checkout SLO (luồng critical doanh thu). Cần live baseline/load-gen verification trước khi claim detector readiness. |
| — | **Error Rate Spike** | 7/12 | **Hoãn đến Tuần 3** | Trùng lặp với cả hai loại đã chọn. Trigger mechanism rủi ro cao. Sẽ được tích hợp như một *tín hiệu đầu ra* của detector Latency Spike (high latency → timeout → 5xx), không phải detector MVP độc lập. |

---

## 4. Tín hiệu cần thiết cho từng loại incident đã chọn

### MVP-1: LLM Timeout / Lỗi

**Mục tiêu phát hiện:** Cảnh báo khi `product-reviews` không lấy được response LLM hợp lệ, do 429 (rate-limit), exception chưa xử lý, hoặc timeout trong tương lai (chưa có hôm nay — xem Risk R2/R3 trong baseline findings).

> [!NOTE]
> **Kênh dữ liệu:** Traces/spans được kiểm tra trực tiếp qua **Jaeger UI/API** (lưu trữ in-memory theo cấu hình [`values.yaml:L1095`](../../../techx-corp-chart/values.yaml#L1095)). OpenSearch (`otel-logs-*`) chỉ dùng để truy vấn có cấu trúc đối với **logs**.

| Tín hiệu | Nguồn | Query / Filter | Ngưỡng |
|---|---|---|---|
| **LLM Error Span** | Jaeger UI/API | `service.name = "product-reviews"` AND `status = "ERROR"` trong Jaeger trace search | Bất kỳ occurrence nào = ứng viên alert |
| **LLM Exception Log** | OpenSearch (`otel-logs-*`) | `body: "Caught Exception"` AND `resource.attributes.service.name: "product-reviews"` | Bất kỳ log nào trong rolling 2-min window |
| **AI Counter Rate Drop** | Prometheus | `rate(app_ai_assistant_counter[5m])` gần bằng không trong khi traffic vẫn tiếp tục (`rate(rpc_server_duration_milliseconds_count{service_name="product-reviews"}[5m]) > 0`) | Counter rate giảm > 90% so với baseline |
| **gRPC Error Rate (luồng AI)** | Prometheus | `rate(rpc_server_duration_milliseconds_count{service_name="product-reviews", rpc_grpc_status_code!="0"}[5m])` | > 0.5 errors/sec kéo dài 2 phút |
| **LLM 429 Log** | OpenSearch | `body: "Returning a rate limit error"` AND `resource.attributes.service.name: "llm"` | Bất kỳ match nào = trigger |

**Trigger có kiểm soát:** Nếu BTC/CDO bật flag `llmRateLimitError` trong khung test, 50% các lần gọi `AskProductAIAssistant` sẽ đi theo luồng 429. AIO detector chỉ đọc telemetry, không sửa `flagd`. Evidence cần thu ở Week 2: OpenSearch log `"Returning a rate limit error"` + Jaeger span status `ERROR` trên `get_ai_assistant_response`.

---

### MVP-2: Latency Spike (Đột biến độ trễ dịch vụ)

**Mục tiêu phát hiện:** Cảnh báo khi p95 latency trên service thuộc critical path vượt ngưỡng SLO (> 1s cho browse, SLO ngầm định cho checkout dẫn xuất từ mô hình INC-1 ở ~2–3s).

> [!NOTE]
> **Kênh dữ liệu:** Traces/spans với span duration bất thường được kiểm tra trực tiếp qua **Jaeger UI/API** (không phải OpenSearch). OpenSearch (`otel-logs-*`) chỉ dùng để tìm kiếm logs liên quan (timeout, connection error). Jaeger dùng `memory_backend` — dữ liệu không bền vững qua restart.

| Tín hiệu | Nguồn | Query / Filter | Ngưỡng |
|---|---|---|---|
| **p95 gRPC Latency** | Prometheus | `histogram_quantile(0.95, sum by (le, service_name) (rate(rpc_server_duration_milliseconds_bucket{service_name=~"product-reviews\|checkout\|cart"}[5m])))` | > 1000 ms kéo dài 3 phút |
| **DB Connection Wait** | OpenSearch (Logs) | `body: "timeout"` OR `body: "connection"` AND `resource.attributes.service.name: "product-reviews"` | Bất kỳ match nào tương quan với latency spike |
| **Span Duration Outlier** | Jaeger UI/API | Spans trên `get_product_reviews` hoặc `get_ai_assistant_response` với duration > 2000ms | Tương quan thủ công trong incident window |
| **gRPC Queue Buildup (ước tính)** | Prometheus | `histogram_quantile(0.95, sum by (le) (rate(rpc_client_duration_milliseconds_bucket{rpc_service="oteldemo.ProductReviewService"}[5m]))) - histogram_quantile(0.95, sum by (le) (rate(rpc_server_duration_milliseconds_bucket{rpc_service="oteldemo.ProductReviewService"}[5m])))` | > 200ms kéo dài 2 phút |
| **Load Generator Throughput Drop** | Prometheus | `rate(http_server_request_duration_seconds_count{service_name="frontend"}[5m])` | Giảm > 30% so với rolling 10m baseline |

> [!NOTE]
> **Queue Buildup — Phương pháp đo:** OTel gRPC instrumentation mặc định không phát ra `grpc_server_started_total` / `grpc_server_handled_total`. Thay vào đó, **thời gian xếp hàng chờ thread pool** được tính gián tiếp theo công thức SRE chuẩn:
>
> **Queue Time = Client Latency − Server Latency**
>
> Trong đó: Client Latency = latency đo tại phía gọi (frontend/checkout gọi đến `product-reviews`, metric `rpc_client_duration_milliseconds_bucket`); Server Latency = latency xử lý thực tế tại `product-reviews` (`rpc_server_duration_milliseconds_bucket`). Chênh lệch dương cho thấy request đang nằm trong queue trước khi được xử lý.

**Trigger có kiểm soát:** Tăng concurrency của `load-generator` tạm thời (chỉnh locust users) HOẶC mô phỏng cạn kiệt DB connection (nhiều concurrent request đến `product-reviews`). Phối hợp với CDO để tránh SLO burn. Ưu tiên test với `product-reviews` trước (tách biệt với AI path) trước khi chạm vào `checkout` (critical doanh thu).

---

## 5. Các loại incident hoãn lại

| Loại incident | Lý do hoãn | Xem xét lại khi nào |
|---|---|---|
| **Error Rate Spike (độc lập)** | Trùng lặp với kết quả của MVP-1 và MVP-2. Không có trigger độc lập sạch. Sẽ được phát hiện như tín hiệu downstream của hai loại đã chọn. | Tuần 3: sau khi validator Latency và LLM đã được xác thực; nối vào như composite rule. |
| **Pod Crash / CrashLoopBackOff** | Yêu cầu tích hợp K8s Events API (không có trong Prometheus; cần watcher riêng). Trigger yêu cầu kill pod (disruptive). | Tuần 3: thêm K8s event watcher như secondary detection channel. |
| **Kafka Consumer Lag** | Metric `otelcol_kafkametrics_consumer_offset_lag` có trong chart ([`values.yaml:L944-L951`](../../../techx-corp-chart/values.yaml#L944-L951)), nhưng Kafka path (`accounting`, `fraud-detection`) không nằm trên critical SLO path. Tác động nghiệp vụ thấp hơn ở phạm vi MVP. | Tuần 3: thêm như monitoring-only panel, không phải alerting detector. |
| **DB Saturation** | Chưa có DB metric trực tiếp trong Prometheus (PostgreSQL receiver chưa được cấu hình). Cần thêm `postgresqlreceiver` vào OTel Collector config. Scope creep cho Tuần 2. | Tuần 3: thêm PostgreSQL receiver vào OTel Collector nếu các incident DB xuất hiện. |

---

## 6. Tóm tắt

```
Phạm vi AIOps MVP — Tuần 2:

  MVP-1: LLM Timeout / Lỗi
     Trigger: BTC flagd (llmRateLimitError)
     Tín hiệu: OpenSearch error logs + Jaeger ERROR spans (qua Jaeger UI/API) + Prometheus AI counter drop

  MVP-2: Latency Spike
     Trigger: load-generator ramp + DB connection pressure
     Tín hiệu: Prometheus p95 histogram + gRPC queue time estimate + Jaeger span duration (qua Jaeger UI/API)

  Hoãn: Error Rate Spike (Tuần 3 composite rule)
  Hoãn: Pod Crash / CrashLoopBackOff (Tuần 3 K8s watcher)
  Hoãn: Kafka Consumer Lag (Tuần 3 monitoring panel)
  Hoãn: DB Saturation (Tuần 3, cần thêm OTel receiver)
```

> [!NOTE]
> Hai loại MVP đã chọn bao phủ **cả hai mặt của bề mặt độ tin cậy AI**: suy giảm tính năng AI nội bộ (MVP-1) và suy giảm cơ sở hạ tầng ảnh hưởng đến AI path (MVP-2). Kết hợp lại, chúng cho phép AIO01 chứng minh vòng lặp detect-correlate-recommend hoàn chỉnh tại Ops Review Tuần 2 mà không cần thay đổi hạ tầng hay rủi ro SLO error budget của production.

---

## 7. Ghi chú validation cho Week 2

Tài liệu này là bằng chứng chọn phạm vi MVP và thiết kế detection signal, chưa phải bằng chứng detector đã chạy production.

Week 2 cần hoàn tất các điểm sau trước khi báo cáo detector readiness:

- Xác minh Prometheus/OpenSearch/Jaeger query chạy được từ môi trường AIOps agent hoặc qua endpoint được CDO cho phép.
- Thu ít nhất một evidence thực tế cho mỗi MVP: query result, trace/log link hoặc screenshot, timestamp, service affected.
- Detector chạy nhẹ: CronJob hoặc process đọc telemetry 1–2 phút/lần, timeout ngắn, không tạo load đáng kể lên service chính.
- Detector chỉ đọc telemetry. Không sửa `flagd`, không đổi feature flag, không restart pod, không thay đổi traffic path.
- Output tối thiểu Week 2: structured log/event vào OpenSearch hoặc log stream có các field `incident_type`, `severity`, `affected_service`, `evidence_query_or_link`, `confidence`, `runbook_hint`.
- Output Week 3 nếu còn thời gian: Slack/webhook hoặc Grafana alert. Nếu chỉ detect nội bộ mà không có output để người trực thấy, chưa tính là operationally useful.
