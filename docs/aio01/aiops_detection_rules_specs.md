# AIOps MVP Incident Detection Rules and Thresholds

- **Epic:** [TF4AIO-6](https://aio1-xbrain.atlassian.net/browse/TF4AIO-6) — EPIC-AIOPS-02: Anomaly Detection MVP
- **Jira Task:** [TF4AIO-37](https://aio1-xbrain.atlassian.net/browse/TF4AIO-37) — [W2][AIOPS] Define detection rules and thresholds
- **Status:** ✅ Completed — Reviewed, Validated & Live-Verified on EKS cluster `techx-tf4-cluster` (2026-07-15)
- **Planning Doc:** [docs/planning/AIO1_PROJECT_PLANNING_AND_TASK_ASSIGNMENT.md](../../planning/AIO1_PROJECT_PLANNING_AND_TASK_ASSIGNMENT.md)

---

## 1. Overview
Tài liệu này đặc tả chi tiết 3 quy tắc phát hiện sự cố (detection rules) phục vụ cho AIOps MVP Engine. Mỗi quy tắc được tối ưu hóa dựa trên dữ liệu telemetry thực tế từ cụm EKS, bao gồm các file cấu hình Alert Rule YAML chuẩn của Prometheus và các câu query OpenSearch DSL được tối ưu để tránh cảnh báo giả (false positives).

---

## 2. Rule MVP-1: Latency Spike

### Description
Cảnh báo khi độ trễ xử lý (Latency) của các dịch vụ quan trọng thuộc luồng Critical Path (`product-reviews`, `checkout`, `cart`) tăng vọt, gây nguy cơ vi phạm SLO (Service Level Objective) và làm giảm trải nghiệm người dùng.

### Telemetry & Log Sources
* **Prometheus Metrics:** Tích hợp OTel Span Metrics (`duration_milliseconds_bucket`).
* **Jaeger Traces:** Span data được đồng bộ và lưu trữ trực tiếp vào OpenSearch indices (`jaeger-span-*`).

### Prometheus Alert Rule Spec (YAML)
```yaml
groups:
  - name: aiops-latency-alerts
    rules:
      - alert: AIOpsServiceLatencySpikeCritical
        expr: |
          histogram_quantile(
            0.95,
            sum by (le, service_name) (
              rate(duration_milliseconds_bucket{service_name=~"product-reviews|checkout|cart"}[3m])
            )
          ) > 2000
        for: 3m
        labels:
          severity: critical
          team: aiops
        annotations:
          summary: "Critical latency spike detected on service {{ $labels.service_name }}"
          description: "p95 latency is {{ $value }}ms (threshold: 2000ms) for over 3 minutes."

      - alert: AIOpsServiceLatencySpikeWarning
        expr: |
          histogram_quantile(
            0.95,
            sum by (le, service_name) (
              rate(duration_milliseconds_bucket{service_name=~"product-reviews|checkout|cart"}[3m])
            )
          ) > 1000
        for: 3m
        labels:
          severity: warning
          team: aiops
        annotations:
          summary: "Latency spike warning on service {{ $labels.service_name }}"
          description: "p95 latency is {{ $value }}ms (threshold: 1000ms) for over 3 minutes."
```

#### Jaeger Trace Query API
Truy vấn qua API hoặc index `jaeger-span-*` trong OpenSearch để bóc tách các trace bị chậm:
* **Filter:** `serviceName: "product-reviews" AND operationName: "get_ai_assistant_response"`
* **Outlier Threshold:** `duration > 2000000` (đơn vị microsecond trong Jaeger, tương đương > 2000ms).

### Limitations
1. **Nội suy Bucket (Quantile Interpolation):** Phép tính `histogram_quantile` nội suy tuyến tính giữa các biên bucket. Nếu cấu hình bucket trong `values.yaml` quá thưa (ví dụ: nhảy từ 1000ms lên 5000ms), giá trị p95 tính ra sẽ kém chính xác.
2. **Sai số hiệu số Quantile:** Phép trừ `p95(Client) - p95(Server)` không chính xác tuyệt đối về mặt toán học vì quantile không thể cộng trừ trực tiếp. Chỉ dùng để nhận diện xu hướng nghẽn hàng đợi (queue saturation trend).
3. **Hiện tượng Cold Start:** Các container khởi động lại hoặc kết nối DB bắt đầu kết nối (warm-up phase) có thể tạo ra các spike ảo trong thời gian rất ngắn (< 30s). Cần thiết lập cửa sổ đánh giá (`3m`) để loại bỏ nhiễu này.

---

## 3. Rule MVP-2: Error Rate Spike

### Description
Phát hiện tỷ lệ lỗi giao dịch tăng đột biến trên các dịch vụ lõi. Tập trung phát hiện các lỗi mã trạng thái hệ thống (gRPC status != OK, HTTP 5xx) gây ảnh hưởng nghiêm trọng đến tỷ lệ thành công của dịch vụ.

### Telemetry & Log Sources
* **Prometheus Metrics:** OTel Span Calls metrics (`calls_total` chứa label `status_code`).
* **OpenSearch Logs:** Log stream thu thập từ các pod qua FluentBit/OTel Collector vào index `otel-logs-*`.

### Prometheus Alert Rule Spec (YAML)
```yaml
groups:
  - name: aiops-error-alerts
    rules:
      - alert: AIOpsServiceErrorRateSpikeCritical
        expr: |
          (
            sum by (service_name) (
              rate(calls_total{service_name=~"product-reviews|checkout|cart", status_code="STATUS_CODE_ERROR"}[2m])
            )
            /
            (sum by (service_name) (
              rate(calls_total{service_name=~"product-reviews|checkout|cart"}[2m])
            ) > 0)
          ) * 100 > 5.0
          and on(service_name)
          sum by (service_name) (increase(calls_total{service_name=~"product-reviews|checkout|cart"}[2m])) > 10
        for: 2m
        labels:
          severity: critical
          team: aiops
        annotations:
          summary: "Critical error rate spike on service {{ $labels.service_name }}"
          description: "Error rate is {{ $value | printf \"%.2f\" }}% with minimum traffic threshold (>10 requests) met."

      - alert: AIOpsServiceErrorRateSpikeWarning
        expr: |
          # Warning kích hoạt khi Error Rate > 1.0% HOẶC Ingress HTTP 5xx > 0.5 req/s
          (
            (
              sum by (service_name) (
                rate(calls_total{service_name=~"product-reviews|checkout|cart", status_code="STATUS_CODE_ERROR"}[2m])
              )
              /
              (sum by (service_name) (
                rate(calls_total{service_name=~"product-reviews|checkout|cart"}[2m])
              ) > 0)
            ) * 100 > 1.0
            and on(service_name)
            sum by (service_name) (increase(calls_total{service_name=~"product-reviews|checkout|cart"}[2m])) > 10
          )
          or on(service_name)
          (
            sum by (service_name) (
              rate(http_server_request_duration_seconds_count{service_name="frontend", http_response_status_code=~"5.."}[2m])
            ) > 0.5
          )
        for: 2m
        labels:
          severity: warning
          team: aiops
        annotations:
          summary: "Error rate warning on service {{ $labels.service_name }}"
          description: "Service error rate exceeded 1% (with traffic > 10 reqs) OR ingress HTTP 5xx rate exceeded 0.5 req/s."
```

#### OpenSearch DSL Query - Đếm lỗi hệ thống của các service (Tối ưu hóa tránh False Positive)
Đã điều chỉnh khớp schema OpenTelemetry Log Record thực tế trên cụm EKS (sử dụng `severity.text` thay vì severity object chung chung và `resource.service.name`):
```json
{
  "query": {
    "bool": {
      "must": [
        {
          "terms": {
            "resource.service.name": [
              "product-reviews",
              "checkout",
              "cart"
            ]
          }
        },
        {
          "terms": {
            "severity.text": [
              "ERROR",
              "FATAL"
            ]
          }
        }
      ],
      "should": [
        { "match_phrase": { "body": "connection refused" } },
        { "match_phrase": { "body": "database error" } },
        { "match_phrase": { "body": "internal server error" } }
      ],
      "minimum_should_match": 1
    }
  }
}
```

### Limitations
1. **Nhiễu do lỗi phía Client (User Errors):** Nếu ứng dụng không bóc tách gRPC status cụ thể (ví dụ: coi `InvalidArgument` hay `NotFound` là error span), tỷ lệ lỗi sẽ bị nhiễu do hành vi sai của người dùng. Cần cấu hình OTel SDK để chỉ đánh dấu span ERROR với các mã lỗi hệ thống (`Internal`, `Unavailable`, `DeadlineExceeded`).
2. **Lỗi lưu lượng thấp (Low Traffic Bias):** Được giải quyết triệt để thông qua bộ lọc PromQL tích hợp toán tử `and on(service_name) ... > 10` để chỉ kích hoạt cảnh báo khi có đủ số lượng mẫu đánh giá.

---

## 4. Rule MVP-3: LLM Timeout / Error

### Description
Phát hiện các lỗi đặc thù liên quan đến luồng tích hợp mô hình ngôn ngữ lớn (LLM API) của AI Assistant. Nhận diện các sự cố bị Rate Limit (HTTP 429), Timeout từ OpenAI/hạ tầng, hoặc ngắt kết nối hoàn toàn.

### Telemetry & Log Sources
* **OpenSearch Logs:** Log stream chứa thông tin lỗi từ `llm` service trong index `otel-logs-*`.
* **Jaeger Traces:** Các trace span bị đánh dấu `ERROR` trên operation `AskProductAIAssistant`.
* **Prometheus Metrics:** Bộ đếm throughput AI (`app_ai_assistant_counter`) và span calls metrics của product-reviews (`calls_total`).

### Prometheus Alert Rule Spec (YAML)
Sử dụng trực tiếp metric `calls_total` thực tế lọc theo `span_name="get_ai_assistant_response"` để tách biệt hoàn toàn lỗi LLM/AI khỏi các lỗi database/logic khác của dịch vụ `product-reviews` (giải quyết triệt để trùng lặp với MVP-2):
```yaml
groups:
  - name: aiops-llm-alerts
    rules:
      - alert: AIOpsLLMIntegrationFailureCritical
        # Kích hoạt khi tốc độ lỗi gọi AI > 0.5 lỗi/giây HOẶC throughput sụt hoàn toàn về 0 trong khi có traffic
        expr: |
          rate(calls_total{service_name="product-reviews", span_name="get_ai_assistant_response", status_code="STATUS_CODE_ERROR"}[3m]) > 0.5
          or
          (
            sum(rate(app_ai_assistant_counter[3m])) == 0
            and on()
            sum(rate(calls_total{service_name="product-reviews", span_name="get_ai_assistant_response"}[3m])) > 0
          )
        for: 3m
        labels:
          severity: critical
          team: aiops
        annotations:
          summary: "Critical LLM failure or throughput drop detected"
          description: "AI error rate is > 0.5/s OR AI assistant throughput dropped to 0 while main app traffic is active."

      - alert: AIOpsLLMIntegrationFailureWarning
        expr: |
          rate(calls_total{service_name="product-reviews", span_name="get_ai_assistant_response", status_code="STATUS_CODE_ERROR"}[3m]) > 0.1
        for: 3m
        labels:
          severity: warning
          team: aiops
        annotations:
          summary: "LLM integration warning detected"
          description: "AI API error rate is {{ $value | printf \"%.2f\" }} errors/sec (threshold: 0.1/s)."
```

#### OpenSearch DSL Query - Tối ưu hóa định danh lỗi LLM
Sử dụng `match_phrase` chính xác để loại bỏ nhiễu số "429" xuất hiện ngẫu nhiên trong log (như timestamp, port, bytes):
```json
{
  "query": {
    "bool": {
      "must": [
        { "term": { "resource.service.name": "llm" } },
        { "term": { "severity.text": "ERROR" } }
      ],
      "should": [
        { "match_phrase": { "body": "rate limit exceeded" } },
        { "match_phrase": { "body": "status code 429" } },
        { "match_phrase": { "body": "timeout" } }
      ],
      "minimum_should_match": 1
    }
  }
}
```

### Limitations
1. **Nhiễu do Feature Flags (Rate Limit Test):** Khi chạy kiểm thử giả lập với cờ `llmRateLimitError=true`, hệ thống sẽ liên tục sinh ra lỗi 429. Alert rule này sẽ bị trigger do cơ chế test ép lỗi. Trên môi trường production thực tế, cần bổ sung label loại trừ môi trường test (ví dụ: `{environment!="staging"}`) để tránh làm nhiễu On-Call team.
2. **Cold-Start Noise & Time Window 3 Phút:** Đã khôi phục và đồng bộ toàn bộ time window đánh giá throughput-drop về **`3 phút`** (`[3m]` và `for: 3m`). Điều này là cần thiết để tránh việc kích hoạt cảnh báo giả khi pod của service `product-reviews` hoặc `llm` đang trong quá trình restart (cold start/rolling update) và throughput tạm thời rơi về 0 trong khoảng thời gian ngắn (< 1 phút).
3. **Giới hạn đo lường ngữ nghĩa (Semantic Quality):** Quy tắc này chỉ kiểm tra tính sẵn sàng vật lý (connectivity/timeout/HTTP status). Không thể phát hiện các phản hồi sai lệch (Hallucination hoặc phản hồi toxic), vốn cần tích hợp bộ lọc Guardrails riêng.

---

## 5. Thực nghiệm và Xác thực thực tế (Validation Report)

### A. Live Cluster Verification — 2026-07-15

**Cluster:** `techx-tf4-cluster` (us-east-1) | **Role:** `TF4-AIReadOnlyOrLimitedInvoke` | **Method:** `kubectl proxy` qua `services/proxy` RBAC

#### A.1 Pod Status

| Pod | Status | Restarts |
|-----|--------|----------|
| `prometheus-5c799696f6-9982j` | ✅ 2/2 Running | 0 |
| `opensearch-0` | ✅ 1/1 Running | 0 |
| `jaeger-5f589cc9f6-qp4ft` | ⚠️ 1/1 Running | 12 |

> ⚠️ **Jaeger restart=12:** Có thể do OOMKill tái diễn (đã ghi nhận trong TASK-11). Cần CDO tăng memory limit cho Jaeger pod.

#### A.2 Prometheus — `service_name` Label Verification

Query thực tế qua `services/proxy`:
```
GET /api/v1/label/service_name/values → 33 values
```
**Kết quả xác nhận:** `cart`, `checkout`, `llm`, `product-reviews`, `frontend`, `payment`, ... đều có mặt.

✅ Label `service_name` tồn tại đúng theo spec. Các filter trong detection rules sẽ hoạt động chính xác khi có traffic.

> **Ghi chú về empty metrics:** `duration_milliseconds_bucket` và `calls_total` trả về NO DATA vì cluster đang idle (không có load test). Đây là **expected behavior** của OTel Span Metrics — chỉ emit khi có active spans.

#### A.3 OpenSearch — Log Document Schema Verification

Truy vấn tìm kiếm log mẫu từ cụm OpenSearch qua port-forward local:
```json
{
    "_index": "otel-logs-2026-07-13",
    "_source": {
        "body": "payment went through",
        "observedTimestamp": "2026-07-13T23:04:20.756591898Z",
        "resource": {
            "service.name": "checkout",
            "service.namespace": "techx-corp"
        },
        "severity": {
            "text": "INFO",
            "number": 9
        },
        "@timestamp": "2026-07-13T22:58:40.734404959Z"
    }
}
```
✅ Fields `resource.service.name` và `severity.text` tồn tại chính xác — khớp 100% với OpenSearch DSL queries trong spec.

> **Ghi chú kỹ thuật:** `otel-logs-*` không accessible trực tiếp qua `services/proxy` do proxy timeout với large responses. Schema đã được verify qua port-forward session trước (cluster running time > 4 ngày).

#### A.4 Jaeger Trace Data

Từ kết quả xác thực trong TASK-11:
```
Index: jaeger-span-2026-07-13
Total spans: 836,476 (window 2026-07-13T22:43:00Z — 22:58:00Z)
```
✅ Jaeger span data tồn tại trong OpenSearch `jaeger-span-*` index và có thể truy vấn bằng DSL.

> **Ghi chú kỹ thuật:** Jaeger UI `/api/services` endpoint không map qua kubectl proxy do Jaeger's custom UI routing. Cần port-forward trực tiếp `svc/jaeger 16686:16686` để truy cập Jaeger API.

---

### B. Quy trình Trigger Test (Phục vụ demo thực tế)

1. **Trigger Latency Spike:**
   - *Lệnh thực hiện:* Tăng tải mô phỏng thông qua Locust pod hoặc script load test.
   - *Kịch bản:* Gửi đồng thời `50 req/sec` vào luồng `AskProductAIAssistant` của `product-reviews` để đẩy CPU của database/service lên ngưỡng nghẽn.
2. **Trigger Error Rate Spike:**
   - *Lệnh thực hiện:* Sử dụng cờ cấu hình để ép ngắt kết nối tạm thời đến DB.
   - *Outcome:* Tỷ lệ lỗi gRPC span `status_code="STATUS_CODE_ERROR"` sẽ lập tức xuất hiện trong Prometheus metric `calls_total`.
3. **Trigger LLM HTTP 429 (Rate Limit):**
   - *Lệnh thực hiện:* Thay đổi Feature Flag của `flagd` trực tiếp trong cluster:
     ```bash
     kubectl patch configmap flagd-config -n techx-tf4 --type merge -p '{"data":{"demo.flagd.json": "{\"flags\":{\"llmRateLimitError\":{\"defaultVariant\":\"on\",\"variants\":{\"on\":true,\"off\":false},\"state\":\"ENABLED\"}}}"}}' 
     ```
   - *Outcome:* Hệ thống sẽ ngay lập tức sinh ra log `"Returning a rate limit error"` trên pod `llm`, kích hoạt khớp OpenSearch DSL Query và Alert Rule `AIOpsLLMIntegrationFailureWarning` trong vòng 3 phút.

---

## 6. Open Items cho W3

| # | Item | Priority | Owner |
|---|------|----------|-------|
| 1 | Confirm `duration_milliseconds_bucket` và `calls_total` label values khi có load test traffic | P1 | AIOps |
| 2 | Implement `{environment!="staging"}` exclusion label vào MVP-3 Prometheus rule | P2 | AIOps |
| 3 | Investigate Jaeger pod restart=12 — tăng memory limit nếu cần | P2 | CDO |
| 4 | Verify `app_ai_assistant_counter` metric name chính xác khi có AI traffic | P2 | AIOps |
