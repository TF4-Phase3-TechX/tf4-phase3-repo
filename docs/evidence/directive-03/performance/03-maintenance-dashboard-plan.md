# D3-PERF-03 — Kế hoạch Giám sát Dashboard & Khung thời gian Bảo trì (MANDATE-03)

*   **Jira Ticket:** [D3-PERF-03](https://ngonguyentruongan2907.atlassian.net/browse/D3-PERF-03)
*   **Nhóm thực hiện (CDO-04):** Huy (Chính - Chuẩn bị danh sách panel, chụp ảnh, bắt timestamp), Ninh (Hỗ trợ - Kiểm tra ảnh, lập bảng mục lục index, đối soát timestamp).
*   **Trạng thái:** Sẵn sàng kiểm chứng (Ready for Evidence).

---

## 1. Danh sách các Grafana Panels & Cấu hình Truy vấn (Dashboard Panel List)

Hệ thống sử dụng Dashboard **`Flash Sale Verification Dashboard`** đã được cấu hình nạp tự động (provisioned) lên Grafana để kiểm chứng. Dưới đây là danh sách chi tiết các panel và câu lệnh PromQL được cấu hình:

### 1.1. Nhóm Traffic & Load-Generator Activity (Hàng số 1)
1.  **Panel: Load-generator traffic activity (spans/s) (Stat)**
    *   *Query:* `sum(rate(traces_span_metrics_calls_total{service_name="load-generator"}[5m])) or vector(0)`
    *   *Mô tả:* Xác nhận bộ sinh tải đang hoạt động phát sinh traffic.
2.  **Panel: Frontend Inbound RPS (Time Series)**
    *   *Query:* `sum(rate(traces_span_metrics_calls_total{service_name="frontend", span_kind="SPAN_KIND_SERVER"}[$__rate_interval]))`
    *   *Mô tả:* Đo lượng RPS đi vào cổng chính.
3.  **Panel: Services RPS & Error Rate (Table)**
    *   *Query RPS:* `sum by (service_name) (rate(traces_span_metrics_calls_total{span_kind="SPAN_KIND_SERVER"}[$__rate_interval]))`
    *   *Query Error %:* `sum by (service_name) (rate(traces_span_metrics_calls_total{span_kind="SPAN_KIND_SERVER", status_code="STATUS_CODE_ERROR"}[$__rate_interval])) / sum by (service_name) (rate(traces_span_metrics_calls_total{span_kind="SPAN_KIND_SERVER"}[$__rate_interval])) * 100`

### 1.2. Nhóm SLO Nghiệp vụ (Hàng số 2 - Cổng Frontend Server Spans)
4.  **Panel: Storefront (Browse) Latency Percentiles (Time Series)**
    *   *Query (p95):* `histogram_quantile(0.95, sum by (le) (rate(traces_span_metrics_duration_milliseconds_bucket{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name=~"GET /|GET /product.*|GET /api/products.*|GET /api/data.*"}[$__rate_interval])))`
    *   *Threshold:* Đường đứt nét đỏ cố định ở mức **`1000ms`**.
5.  **Panel: Browse/Search Success Rate (Gauge)**
    *   *Query:* `100 * sum(rate(traces_span_metrics_calls_total{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name=~"GET /|GET /product.*|GET /api/products.*|GET /api/data.*", status_code!="STATUS_CODE_ERROR"}[$__rate_interval])) / sum(rate(traces_span_metrics_calls_total{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name=~"GET /|GET /product.*|GET /api/products.*|GET /api/data.*"}[$__rate_interval]))`
    *   *Threshold:* Chuyển đỏ nếu dưới **`99.5%`**.
6.  **Panel: Browse Request Volume (Stat - Lọc nhiễu)**
    *   *Query:* `sum(increase(traces_span_metrics_calls_total{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name=~"GET /|GET /product.*|GET /api/products.*|GET /api/data.*"}[$__rate_interval]))`
7.  **Panel: Cart Success Rate (Gauge)**
    *   *Query:* `100 * sum(rate(traces_span_metrics_calls_total{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name=~"(GET|POST|DELETE) /api/cart", status_code!="STATUS_CODE_ERROR"}[$__rate_interval])) / sum(rate(traces_span_metrics_calls_total{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name=~"(GET|POST|DELETE) /api/cart"}[$__rate_interval]))`
    *   *Threshold:* Chuyển đỏ nếu dưới **`99.5%`**.
8.  **Panel: Cart Request Volume (Stat)**
    *   *Query:* `sum(increase(traces_span_metrics_calls_total{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name=~"(GET|POST|DELETE) /api/cart"}[$__rate_interval]))`
9.  **Panel: Checkout Success Rate (Gauge)**
    *   *Query:* `100 * sum(rate(traces_span_metrics_calls_total{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name="POST /api/checkout", status_code!="STATUS_CODE_ERROR"}[$__rate_interval])) / sum(rate(traces_span_metrics_calls_total{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name="POST /api/checkout"}[$__rate_interval]))`
    *   *Threshold:* Chuyển đỏ nếu dưới **`99.0%`**.
10. **Panel: Checkout Request Volume (Stat)**
    *   *Query:* `sum(increase(traces_span_metrics_calls_total{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name="POST /api/checkout"}[$__rate_interval]))`

### 1.3. Nhóm Sức khỏe Tài nguyên (Hàng số 3)
11. **Panel: Critical Pods CPU Usage (Time Series)**
    *   *Query:* `sum(rate(container_cpu_usage_seconds_total{namespace="techx-tf4", container=~"frontend|cart|checkout|payment|accounting|product-catalog"}[$__rate_interval])) by (container) * 1000` (Đơn vị: `m`)
12. **Panel: Critical Pods Memory Usage (Time Series)**
    *   *Query:* `sum(container_memory_working_set_bytes{namespace="techx-tf4", container=~"frontend|cart|checkout|payment|accounting|product-catalog"}) by (container) / 1024 / 1024` (Đơn vị: `MiB`)
13. **Panel: Node CPU Usage % (Time Series)**
    *   *Query:* `(max by (k8s_node_name) (k8s_node_cpu_usage) / on (k8s_node_name) label_replace(max by (instance) (machine_cpu_cores{job="kubernetes-nodes-cadvisor"}), "k8s_node_name", "$1", "instance", "(.*)")) * 100` (Threshold: 85%)
14. **Panel: Node Memory Usage % (Time Series)**
    *   *Query:* `max by (k8s_node_name) (k8s_node_memory_usage_bytes / (k8s_node_memory_usage_bytes + k8s_node_memory_available_bytes)) * 100` (Threshold: 85%)

### 1.4. Nhóm Cảnh báo, Co giãn & Khởi động lại (Hàng số 4)
15. **Panel: Pod Restarts (10m Delta) (Stat)**
    *   *Query:* `sum(max_over_time(k8s_container_restarts{k8s_namespace_name=~"techx-tf4|techx-observability"}[10m]) - min_over_time(k8s_container_restarts{k8s_namespace_name=~"techx-tf4|techx-observability"}[10m])) by (k8s_pod_name, k8s_container_name)`
16. **Panel: Pod OOMKilled Events (10m) (Stat)**
    *   *Query:* `sum by (namespace, pod, container) (increase(container_oom_events_total{namespace=~"techx-tf4|techx-observability", container!=""}[10m]))`
17. **Panel: Pending Pods Count (Stat)**
    *   *Query:* `sum(k8s_pod_phase{k8s_namespace_name=~"techx-tf4|techx-observability"} == 1) or vector(0)` (Chuyển đỏ nếu > 0)
18. **Panel: Active Prometheus Alerts (Stat)**
    *   *Query:* `sum(ALERTS{alertstate="firing"}) or vector(0)` (Theo dõi các alert đang kích hoạt)
19. **Panel: Pod Replica Count (HPA) (Time Series)**
    *   *Query:* `k8s_deployment_available{k8s_namespace_name="techx-tf4", k8s_deployment_name=~"frontend|cart|checkout|payment|accounting|product-catalog"}`
20. **Panel: Active Worker Nodes Count (Time Series)**
    *   *Query:* `sum(k8s_node_condition{condition="Ready"})`

---

## 2. Xác định Khung thời gian UTC & Các Checkpoint Bảo trì

Để đảm bảo tính nhất quán, toàn bộ bằng chứng hình ảnh sẽ sử dụng **cùng một khung thời gian tuyệt đối (Absolute UTC window)** trong bộ chọn thời gian (time picker) của Grafana. Khung giờ này được xác định từ log chạy bài test tải thực tế (khoảng 30 phút bao phủ toàn bộ quá trình).

### Cấu hình 4 Checkpoint quan trọng:

```text
[   T0: Pre-maint   ] ──► [   T1: During-maint   ] ──► [   T2: Post-maint   ] ──► [   T3: Stabilized   ]
(Trước bảo trì - 2 Nodes) (Đang chạy Drain Node)      (Pods chuyển nhà xong)   (Hệ thống tự co xuống)
```

1.  **Checkpoint T0 — Trước bảo trì (Pre-maintenance Baseline):**
    *   *Thời điểm:* Khoảng 5 phút sau khi bài test tải 200 users bắt đầu chạy ổn định.
    *   *Mục tiêu:* Chụp lại trạng thái cân bằng bình thường. Hệ thống có đủ 2 Nodes, tải phân phối đều, không có alert nào firing.
2.  **Checkpoint T1 — Trong bảo trì (During-maintenance Action):**
    *   *Thời điểm:* Ngay sau khi thực hiện lệnh `kubectl drain` rút cạn Node vật lý hoặc khi Pods đang rolling restart.
    *   *Mục tiêu:* Kiểm chứng độ trễ storefront p95 có vượt 1s không, và có xuất hiện Pod bị kẹt `Pending` do thiếu tài nguyên dự phòng (headroom) không.
3.  **Checkpoint T2 — Ngay sau bảo trì (Post-maintenance Completion):**
    *   *Thời điểm:* Ngay khi lệnh drain hoàn tất, toàn bộ Pod đã được chuyển nhà sang Node còn lại ổn định.
    *   *Mục tiêu:* Xác nhận tỷ lệ thành công (Success Rate) của Browse/Cart/Checkout vẫn giữ vững trên ngưỡng SLO và số lượng replica khả dụng đã ổn định.
4.  **Checkpoint T3 — Sau khi hệ thống ổn định (Stabilized and Scale-down):**
    *   *Thời điểm:* Sau khi kết thúc bài test tải (Locust dừng gửi request).
    *   *Mục tiêu:* Xác nhận HPA đã tự động scale-down các Pod về mức baseline ban đầu (1 pod) để tiết kiệm chi phí.

---

## 3. Quy trình Phối hợp Kiểm duyệt & Mục lục Ảnh (Evidence Index)

Huy và Ninh sẽ phối hợp chặt chẽ theo quy trình kiểm duyệt chất lượng hình ảnh nghiêm ngặt của dự án:

### 3.1. Ràng buộc chất lượng ảnh chụp (Huy thực hiện chính):
*   Ảnh chụp phải giữ nguyên **khung giờ UTC tuyệt đối (Time Picker)** ở góc trên bên phải Grafana.
*   Không được cắt (crop) mất chú thích đồ thị (legend) và đường giới hạn đỏ (threshold lines).
*   Tuyệt đối không dùng ảnh chụp màn hình terminal (Terminal logs) làm bằng chứng chính để chứng minh SLO.

### 3.2. Đối soát và lập mục lục (Ninh hỗ trợ):
Ninh sẽ kiểm tra chéo timestamp của từng ảnh và đặt tên ảnh thống nhất theo cấu trúc để lưu vào thư mục `docs/evidence/directive-03/performance/screenshots/`:

| Checkpoint | Tên file ảnh (Image File Name) | Metric chứng minh (Observed Metric) | Trạng thái (Status) |
| :--- | :--- | :--- | :--- |
| **T0 (Pre-maint)** | `01-pre-maint-slo-baseline.png` | Latency, Success Rate và Trạng thái Tải ban đầu | Sẵn sàng |
| **T0 (Pre-maint)** | `02-pre-maint-resource-baseline.png` | CPU/Memory Node & Pod, Active Nodes = 2 | Sẵn sàng |
| **T1 (During)** | `03-during-maint-latency-pending.png` | Storefront Latency p95, Đếm số Pending Pods | Sẵn sàng |
| **T1 (During)** | `04-during-maint-alert-state.png` | Trạng thái Alerts firing/pending lúc chịu tải | Sẵn sàng |
| **T2 (Post-maint)** | `05-post-maint-slo-verification.png` | Thẩm định Checkout >= 99%, Browse/Cart >= 99.5% | Sẵn sàng |
| **T2 (Post-maint)** | `06-post-maint-resource-state.png` | CPU/Memory Node còn lại dưới 85%, Restarts | Sẵn sàng |
| **T3 (Stabilized)** | `07-stabilized-scale-down.png` | Replica co về 1, Node co về baseline, Tải về 0 | Sẵn sàng |

---

## 4. Known Limitations & Ghi nhận thiếu sót (No Data Logs)

*   **PostgreSQL Connections (`postgresql_backends`):** Nếu hiển thị `No Data`, CDO-04 ghi nhận đây là giới hạn nền tảng (Platform Limitation) do Prometheus Exporter của Database chưa được kích hoạt, không tự ý suy diễn hay giả thiết số liệu.
*   **Valkey/Redis Clients (`redis_connected_clients`):** Nếu hiển thị `No Data`, ghi nhận tương tự.
