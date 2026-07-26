# D18-PERF-01: Đo telemetry volume, retention và metric cardinality

> Jira: [C0G-102](https://ngonguyentruongan2907.atlassian.net/browse/C0G-102)
> Evidence: Prometheus PromQL, OpenSearch API và CloudWatch Logs IncomingBytes.
> Trạng thái: **Done**

---

## 1. Measurement Contract

| Nội dung | Giá trị |
|---|---|
| Live telemetry UTC | `2026-07-22T16:03:17Z` đến `2026-07-22T16:11:32Z` |
| AWS account / Region | `511825856493` / `us-east-1` |
| Primary metric | Ingest rate, storage size, retention, cardinality |
| Context | Đo đạc trạng thái hiện tại (Baseline) của Logs, Traces và Metrics trên EKS cluster trước khi tối ưu hóa. |

---

## 2. Telemetry Baseline

| Signal | Source | Usage metric | Baseline | Retention | Top producer |
|---|---|---|---|---|---|
| **Logs** | CloudWatch Logs (Control Plane)<br>OpenSearch (Application Logs) | Ingest GB/ngày & Stored GB | Control Plane: `17.38 GB/ngày` (121.7 GB / 7 ngày)<br>App logs: `0.97 GB/ngày` (otel-logs index) | Control Plane: `90 ngày`<br>App logs: `7 ngày` | `product-catalog` (27.7%)<br>`frontend-proxy` (27.0%)<br>`load-generator` (21.0%) |
| **Traces** | OpenSearch / Jaeger | spans/giây & Storage size | ~`4,644 spans/giây` (401.3 triệu spans/ngày)<br>Dung lượng: `18.4 GB/ngày` | `7 ngày` | `frontend` (30.8%)<br>`cart` (14.0%)<br>`load-generator` (12.1%) |
| **Metrics** | Prometheus TSDB | active series & Ingestion rate | `179,044` active series<br>`3,535.45` samples/giây | `7 ngày` (1w) | `apiserver_request_duration_seconds_bucket` |

---

## 3. Chi tiết các số liệu giám sát (Telemetry Details)

### A. Logs (Nhật ký hệ thống)
* **Log Ingest GB/ngày:**
  * Control Plane (CloudWatch): **17.38 GB/ngày** (Tổng cộng `121.67 GB` trong 7 ngày).
  * Application (OpenSearch `otel-logs-*`): Khoảng **0.97 GB/ngày** (Index full ngày `otel-logs-2026-07-21` là `972.6 MB`).
* **Log Stored GB (Tổng dung lượng lưu trữ):**
  * Control Plane (CloudWatch): **10.259 GB** stored bytes.
  * Application (OpenSearch): **3.04 GB** (Lưu trữ lũy kế 3 ngày gần nhất).
* **Log Groups Retention (Thời gian lưu giữ):**
  * CloudWatch Logs: **90 ngày**.
  * OpenSearch Log Indices: **7 ngày** (Sử dụng cơ chế Index Rotation hàng ngày).
* **Top log producers (Các service ghi log nhiều nhất):**
  * `product-catalog`: **1,063,752** dòng log (chiếm ~`27.7%`).
  * `frontend-proxy`: **1,034,712** dòng log (chiếm ~`27.0%`).
  * `load-generator`: **803,666** dòng log (chiếm ~`21.0%`).
  * *Lưu ý:* Hai service `product-catalog` và `frontend-proxy` chiếm hơn **54%** tổng lượng log của app.
* **Debug logs / Duplicate logs (Ghi nhận log rác trong production):**
  * **Không phát hiện log DEBUG** trong cụm production (0 doc count).
  * Các mức log level chính được ghi nhận: `INFO` (3.1M dòng), `Information` (557k dòng), `info` (110k dòng), `WARN` (30k dòng), `ERROR` (3.3k dòng).

### B. Traces (Vết dịch vụ)
* **Traces/second & Spans/second (Tốc độ sinh trace/span):**
  * Số lượng spans trung bình mỗi giây: **~4,644 spans/s** (Tổng cộng `401,299,439` spans ghi nhận trên index `jaeger-span-2026-07-22`).
* **Sampling rate (Tỉ lệ lấy mẫu cấu hình):**
  * Hiện tại đang để mặc định **1.0** (100% sampling rate). Đây chính là nguyên nhân sinh ra lượng trace khổng lồ (hơn 400 triệu spans/ngày).
* **Trace storage (Dung lượng OpenSearch index):**
  * **18.4 GB/ngày** (Index `jaeger-span-2026-07-22`).
* **Trace retention (Thời gian lưu vết):**
  * **7 ngày** (Tự động xóa index cũ thông qua OpenSearch Index State Management).
* **Top trace/span producers (Các service sinh nhiều trace nhất):**
  * `frontend`: **3,338,670** spans (chiếm `30.8%`).
  * `cart`: **1,517,194** spans (chiếm `14.0%`).
  * `load-generator`: **1,316,297** spans (chiếm `12.1%`).
  * `product-catalog`: **1,303,050** spans (chiếm `12.0%`).
  * `frontend-proxy`: **1,173,865** spans (chiếm `10.8%`).

### C. Metrics (Chỉ số đo đạc)
* **Prometheus active series:** **179,044** active series trong TSDB Head block.
* **Samples ingested/second:** **3,535.45** samples/s.
* **Scrape interval (Chu kỳ cào metric):**
  * **30 giây** (Scrape interval cấu hình trong Helm Chart values).
* **Top cardinality metrics (Các metric có độ phức tạp cao nhất):**
  1. `apiserver_request_duration_seconds_bucket` -> **27,144** active series.
  2. `apiserver_request_sli_duration_seconds_bucket` -> **17,776** active series.
  3. `etcd_request_duration_seconds_bucket` -> **15,648** active series.
  4. `traces_span_metrics_duration_milliseconds_bucket` -> **8,857** active series.
  5. `apiserver_request_body_size_bytes_bucket` -> **8,736** active series.
* **Labels with unbounded cardinality (Nhãn có giá trị thay đổi vô hạn):**
  * Metrics của Kubernetes API-Server (`apiserver_*`): Chứa các label như `resource`, `subresource`, `request`, `verb` làm bùng nổ số lượng series.
  * Metrics trace span (`traces_span_metrics_*`): Chứa label `span_name`, `service_name` có tính duy nhất cao.
* **TSDB storage usage (Dung lượng ổ cứng Prometheus PVC):**
  * Dung lượng TSDB Block: **3,848,666,176 bytes** (~`3.85 GB`).
  * Prometheus PVC filesystem used: **17.41 GB** trên tổng số **21.40 GB** (`81%` disk usage).

---

## 4. Danh sách các tín hiệu vận hành trọng yếu (Investigation-Critical Signals)
Các metric và tín hiệu bắt buộc phải giữ lại (không được cắt giảm) để phục vụ giám sát hạ tầng và điều tra sự cố:
* **Hạ tầng (Infrastructure):** `up`, `node_cpu_utilization`, `node_memory_utilization`, `container_cpu_usage_seconds_total`, `container_memory_working_set_bytes`.
* **Ứng dụng & SLO:** `http_requests_total`, `grpc_server_handled_total`, `checkout_success_rate`, `latency_p95`.
* **Co giãn tự động:** `kube_hpa_status_current_replicas`, `karpenter_nodeclaims_created`.

---

## 5. Nhật ký các câu lệnh truy vấn (Raw Query & API Evidence)

### A. Truy vấn thông tin Log/Trace từ OpenSearch
Thực hiện truy vấn qua localhost cổng `19200` (sau khi Tunnel tới service `opensearch`):
```json
// POST http://localhost:19200/otel-logs-*/_search
{
  "size": 0,
  "aggs": {
    "top_containers": {
      "terms": {
        "field": "resource.k8s.container.name.keyword",
        "size": 10
      }
    },
    "severities": {
      "terms": {
        "field": "severity.text.keyword",
        "size": 10
      }
    }
  }
}

// POST http://localhost:19200/jaeger-span-*/_search
{
  "size": 0,
  "aggs": {
    "top_spans": {
      "terms": {
        "field": "process.serviceName",
        "size": 10
      }
    }
  }
}
```

### B. Truy vấn số liệu Metrics từ Prometheus
Thực hiện truy vấn qua localhost cổng `19090` (sau khi Tunnel tới service `prometheus`):
```bash
# 1. Đo Active Series
curl -sG http://localhost:19090/api/v1/query --data-urlencode 'query=prometheus_tsdb_head_series'

# 2. Ingest Rate
curl -sG http://localhost:19090/api/v1/query --data-urlencode 'query=rate(prometheus_tsdb_head_samples_appended_total[5m])'

# 3. Top Cardinality Metrics
curl -sG http://localhost:19090/api/v1/query --data-urlencode 'query=topk(10, count by (__name__) ({__name__=~".+"}))'
```
