# C0G-29 — Thiết kế Grafana Dashboard cho đợt kiểm thử 200 concurrent users

**Jira:** [C0G-29](https://ngonguyentruongan2907.atlassian.net/browse/C0G-29)  
**Scope:** `techx-tf4` Grafana Dashboard & Prometheus queries  
**Phân công trách nhiệm:**
- **Ninh (CDO-04):** Tạo/Chỉnh Grafana Panels và soạn thảo Prometheus queries.
- **Hoàng (CDO-04):** Kiểm tra dữ liệu và chụp screenshot làm bằng chứng (evidence).
- **An (CDO-04):** Kiểm duyệt Dashboard để đảm bảo đầy đủ thông số nghiệm thu.

---

## 1. Mục tiêu thiết kế
Dashboard này được thiết kế chuyên biệt để phục vụ đợt chạy test tải nghiệm thu 200 users trong 15 phút. Dashboard tập trung hoàn toàn vào việc hiển thị các chỉ số cam kết chất lượng dịch vụ (SLO) của Directive #2, tình trạng tài nguyên hệ thống (Pod/Node) và các lỗi vận hành liên quan đến OOM/Restart.

Tất cả các truy vấn đo lường SLO nghiệp vụ đều sử dụng **Customer-facing Frontend Server Spans** (`service_name="frontend"` và `span_kind="SPAN_KIND_SERVER"`) để phản ánh đúng trải nghiệm của người dùng thực tế và thống nhất với cấu hình cảnh báo (`flash-sale-alerts.yaml`).

---

## 2. Bố cục Panels & Prometheus Queries bắt buộc

Dưới đây là danh sách các panel, công thức PromQL tương ứng, đơn vị hiển thị và các ngưỡng cảnh báo (threshold) được thiết lập:

### 2.1. Nhóm chỉ số SLO Nghiệp vụ (Directive #2 SLOs & Boundary)

#### 1. Storefront (Browse) Latency (p50, p95, p99)
- **Tên Panel:** Storefront Latency Percentiles
- **Loại Panel:** Time Series (Đơn vị: `ms`)
- **Query (p50):**
  ```promql
  histogram_quantile(0.50, sum by (le) (rate(traces_span_metrics_duration_milliseconds_bucket{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name=~"GET /|GET /product.*|GET /api/products.*|GET /api/data.*"}[$__rate_interval])))
  ```
- **Query (p95):**
  ```promql
  histogram_quantile(0.95, sum by (le) (rate(traces_span_metrics_duration_milliseconds_bucket{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name=~"GET /|GET /product.*|GET /api/products.*|GET /api/data.*"}[$__rate_interval])))
  ```
- **Query (p99):**
  ```promql
  histogram_quantile(0.99, sum by (le) (rate(traces_span_metrics_duration_milliseconds_bucket{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name=~"GET /|GET /product.*|GET /api/products.*|GET /api/data.*"}[$__rate_interval])))
  ```
- **Ngưỡng cảnh báo (Threshold):** p95 Latency > **`1000ms` (1s)** (Vẽ đường đứt nét màu đỏ làm vạch giới hạn SLO).

#### 2. Browse/Search Success Rate & Volume
- **Tên Panel 1:** Browse/Search Success Rate
- **Loại Panel:** Gauge (Đơn vị: `Percent 0-100`)
- **Query Success Rate:**
  ```promql
  100 * sum(rate(traces_span_metrics_calls_total{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name=~"GET /|GET /product.*|GET /api/products.*|GET /api/data.*", status_code!="STATUS_CODE_ERROR"}[$__rate_interval])) / sum(rate(traces_span_metrics_calls_total{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name=~"GET /|GET /product.*|GET /api/products.*|GET /api/data.*"}[$__rate_interval]))
  ```
- **Tên Panel 2:** Browse/Search Inbound Volume
- **Loại Panel:** Stat (Đơn vị: `short`)
- **Query Volume:**
  ```promql
  sum(increase(traces_span_metrics_calls_total{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name=~"GET /|GET /product.*|GET /api/products.*|GET /api/data.*"}[$__rate_interval]))
  ```
- **Ngưỡng cảnh báo & Lọc nhiễu:** Success Rate < **`99.5%`** (Cảnh báo đỏ). SLO chỉ được thẩm định khi Volume đạt tối thiểu 20 requests trong cửa sổ đánh giá (low-traffic guard).

#### 3. Cart Success Rate & Volume
- **Tên Panel 1:** Cart Success Rate
- **Loại Panel:** Gauge (Đơn vị: `Percent 0-100`)
- **Query Success Rate:**
  ```promql
  100 * sum(rate(traces_span_metrics_calls_total{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name=~"(GET|POST|DELETE) /api/cart", status_code!="STATUS_CODE_ERROR"}[$__rate_interval])) / sum(rate(traces_span_metrics_calls_total{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name=~"(GET|POST|DELETE) /api/cart"}[$__rate_interval]))
  ```
- **Tên Panel 2:** Cart Inbound Volume
- **Loại Panel:** Stat (Đơn vị: `short`)
- **Query Volume:**
  ```promql
  sum(increase(traces_span_metrics_calls_total{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name=~"(GET|POST|DELETE) /api/cart"}[$__rate_interval]))
  ```
- **Ngưỡng cảnh báo & Lọc nhiễu:** Success Rate < **`99.5%`** (Cảnh báo đỏ). SLO chỉ thẩm định khi Volume đạt tối thiểu 20 requests.

#### 4. Checkout Success Rate & Volume
- **Tên Panel 1:** Checkout Success Rate
- **Loại Panel:** Gauge (Đơn vị: `Percent 0-100`)
- **Query Success Rate:**
  ```promql
  100 * sum(rate(traces_span_metrics_calls_total{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name="POST /api/checkout", status_code!="STATUS_CODE_ERROR"}[$__rate_interval])) / sum(rate(traces_span_metrics_calls_total{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name="POST /api/checkout"}[$__rate_interval]))
  ```
- **Tên Panel 2:** Checkout Inbound Volume
- **Loại Panel:** Stat (Đơn vị: `short`)
- **Query Volume:**
  ```promql
  sum(increase(traces_span_metrics_calls_total{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name="POST /api/checkout"}[$__rate_interval]))
  ```
- **Ngưỡng cảnh báo & Lọc nhiễu:** Success Rate < **`99.0%`** (Cảnh báo đỏ). SLO chỉ thẩm định khi Volume đạt tối thiểu 20 requests.

---

### 2.2. Nhóm chỉ số Tải & Trạng thái Hệ thống (Traffic & Cluster State)

#### 5. Load-generator traffic activity (spans/s)
- **Tên Panel:** Load-generator traffic activity (spans/s)
- **Loại Panel:** Stat (Đơn vị: `short`)
- **Query:**
  ```promql
  sum(rate(traces_span_metrics_calls_total{service_name="load-generator"}[5m])) or vector(0)
  ```
- *Mô tả:* Panel này dùng để xác nhận công cụ tạo tải (Locust) đang phát sinh traffic. Việc chứng minh 200 concurrent users sẽ dựa trên báo cáo xuất ra từ Locust UI/API.

#### 6. Request Rate (Tổng số Request/giây của các Dịch vụ)
- **Tên Panel:** Total Request Rate (RPS)
- **Loại Panel:** Table (Đơn vị: `reqps`)
- **Query:**
  ```promql
  sum by (service_name) (rate(traces_span_metrics_calls_total{span_kind="SPAN_KIND_SERVER"}[$__rate_interval]))
  ```

#### 7. HTTP/gRPC Error Rate (Tỷ lệ lỗi của Frontend)
- **Tên Panel:** Frontend Error Rate
- **Loại Panel:** Time Series (Đơn vị: `Percent 0-100`)
- **Query:**
  ```promql
  100 * sum(rate(traces_span_metrics_calls_total{service_name="frontend", span_kind="SPAN_KIND_SERVER", status_code="STATUS_CODE_ERROR"}[$__rate_interval])) / sum(rate(traces_span_metrics_calls_total{service_name="frontend", span_kind="SPAN_KIND_SERVER"}[$__rate_interval]))
  ```

---

### 2.3. Nhóm chỉ số Tài nguyên & Vận hành (Scraped EKS Metrics)

#### 8. CPU/Memory theo Critical Service
- **Tên Panel:** Critical Pods CPU Usage
- **Query:**
  ```promql
  sum(rate(container_cpu_usage_seconds_total{namespace="techx-tf4", container=~"frontend|cart|checkout|payment|accounting|product-catalog"}[$__rate_interval])) by (container) * 1000
  ```
  *(Đơn vị: `mili-cores`)*
- **Tên Panel:** Critical Pods Memory Usage
- **Query:**
  ```promql
  sum(container_memory_working_set_bytes{namespace="techx-tf4", container=~"frontend|cart|checkout|payment|accounting|product-catalog"}) by (container) / 1024 / 1024
  ```
  *(Đơn vị: `MiB` - so sánh trực tiếp với limits 256Mi/768Mi)*

#### 9. CPU/Memory của EKS Nodes
- **Tên Panel:** Node CPU Usage
- **Query:**
  ```promql
  (max by (k8s_node_name) (k8s_node_cpu_usage) / on (k8s_node_name) label_replace(max by (instance) (machine_cpu_cores{job="kubernetes-nodes-cadvisor"}), "k8s_node_name", "$1", "instance", "(.*)")) * 100
  ```
  *(Đơn vị: `Percent 0-100`, vạch cảnh báo tại 85%)*
- **Tên Panel:** Node Memory Usage
- **Query:**
  ```promql
  max by (k8s_node_name) (k8s_node_memory_usage_bytes / (k8s_node_memory_usage_bytes + k8s_node_memory_available_bytes)) * 100
  ```
  *(Đơn vị: `Percent 0-100`, vạch cảnh báo tại 85%)*

#### 10. Pod Restart và OOMKilled
- **Tên Panel:** Pod Restarts (10m Delta)
- **Query:**
  ```promql
  sum(max_over_time(k8s_container_restarts{k8s_namespace_name=~"techx-tf4|techx-observability"}[10m]) - min_over_time(k8s_container_restarts{k8s_namespace_name=~"techx-tf4|techx-observability"}[10m])) by (k8s_pod_name, k8s_container_name)
  ```
- **Tên Panel:** Pod OOMKilled events
- **Query:**
  ```promql
  sum by (namespace, pod, container) (increase(container_oom_events_total{namespace=~"techx-tf4|techx-observability", container!=""}[10m]))
  ```

#### 11. Replica Count (Theo dõi Autoscaling Co giãn)
- **Tên Panel:** Pod Replica Count
- **Query:**
  ```promql
  k8s_deployment_available{k8s_namespace_name="techx-tf4", k8s_deployment_name=~"frontend|cart|checkout|payment|accounting|product-catalog"}
  ```

#### 12. Node Count (Theo dõi EKS Node Group Autoscaling)
- **Tên Panel:** Active Worker Nodes Count
- **Query:**
  ```promql
  sum(k8s_node_condition{condition="Ready"})
  ```

---

### 2.4. Khảo sát chỉ số Phụ trợ (PostgreSQL / Valkey)

- **PostgreSQL Connections:**
  - *Query:* `postgresql_backends` (Được nạp tự động qua exporter của CDO-08).
- **Valkey/Redis Clients:**
  - *Query:* `redis_connected_clients`
- *Ghi chú:* Nếu các panel này hiển thị `No Data`, đó là bằng chứng hệ thống platform chưa kích hoạt Prometheus Exporter tương ứng, không giả định sẵn.

---

## 3. Quy trình nghiệm thu (Acceptance Process)

1. **Pre-test Screenshot:** Hoàng chụp lại toàn bộ màn hình Dashboard ở trạng thái tĩnh (trước khi chạy test) làm baseline.
2. **Smoke Test Verification:** Chạy Locust với tải nhẹ 2-3 users trong 1 phút để verify tất cả các panel trên Dashboard đều hiển thị dữ liệu động (dynamic charts).
3. **Time Range setup:** Khi chạy bài test 15 phút, chỉnh Time Range của Grafana ở góc trên bên phải về chế độ **`Last 30 minutes`** hoặc **`Custom: Start/End time`** của đợt chạy để bao phủ trọn vẹn toàn bộ timeline bài test.
