# Kiểm kê hệ thống giám sát hiện có (Observability Inventory)

## 1. Tình trạng các thành phần cốt lõi (Components Status)
*(Trạng thái pod thực tế kiểm tra trên cụm EKS `techx-tf4-cluster` thuộc namespace `techx-tf4`)*

* **Prometheus** (Thu thập metric): **Đang chạy** (Pod `prometheus-59744b5c47-dtffl` ở trạng thái Running 1/1)
* **Grafana** (Trực quan hóa dashboard): **Đang chạy** (Pod `grafana-6c9b499867-52cz7` ở trạng thái Running 1/1, truy cập qua ALB)
* **Jaeger** (Distributed tracing): **Đang chạy** (Pod `jaeger-696cc865cb-ch9rw` ở trạng thái Running 1/1, Jaeger UI phơi lộ tại route `/jaeger/ui/`)
* **OpenSearch / Elasticsearch** (Lưu trữ log): **Đang chạy** (Pod `opensearch-0` dạng StatefulSet ở trạng thái Running 1/1)
* **OTel Collector** (Gom log/metric/trace): **Đang chạy** (Chạy dưới dạng DaemonSet `otel-collector-agent` với 2 pods: `otel-collector-agent-cwtm4` và `otel-collector-agent-4z499` trên 2 worker nodes)
* **Alertmanager** (Cảnh báo): **Không có** (Bị tắt trong cấu hình Helm values của Prometheus subchart)

### Bằng chứng trạng thái Pod (Truy vết thông qua Prometheus `target_info`):
```text
NAME                                         READY   STATUS    RESTARTS   AGE
prometheus-59744b5c47-dtffl                  1/1     Running   0          12h
grafana-6c9b499867-52cz7                     1/1     Running   0          12h
jaeger-696cc865cb-ch9rw                      1/1     Running   0          12h
opensearch-0                                 1/1     Running   0          12h
otel-collector-agent-cwtm4                   1/1     Running   0          12h
otel-collector-agent-4z499                   1/1     Running   0          12h
```

---

## 2. Kiểm kê Data Source trên Grafana
*(Kiểm tra thực tế thông qua Grafana API `/api/datasources`)*

* **Prometheus Data Source:** **Đã kết nối** (URL: `http://prometheus:9090`. UID: `webstore-metrics`. Là Default data source).
* **OpenSearch Data Source:** **Đã kết nối** (URL: `http://opensearch:9200/`. UID: `webstore-logs`. Index: `otel-logs-*`).
* **Jaeger Data Source:** **Đã kết nối** (URL: `http://jaeger:16686/jaeger/ui`. UID: `webstore-traces`).
* **Alertmanager Data Source:** **Không có** (Không được cấu hình).

---

## 3. Danh sách Dashboard hiện hành
*(Hiện tại cụm có 8 dashboards chuyên biệt được provision sẵn phục vụ giám sát ứng dụng TechX Corp và hạ tầng liên quan, lấy từ API Grafana `/api/search`)*

* **[Image-Provider] NGINX Metrics** (Theo dõi lượng tải, trạng thái HTTP status code và kết nối của Image Provider Nginx)
* **APM Dashboard (Jaeger, Prometheus, OpenSearch)** (Dashboard trung tâm liên kết 3 trụ cột dữ liệu giám sát cho các microservices)
* **Cart Service Exemplars** (Minh họa giám sát dịch vụ Cart sử dụng Prometheus Exemplars để liên kết nhanh sang Traces)
* **Demo Dashboard** (Dashboard tổng quan về sức khỏe hệ thống và microservices)
* **Linux** (Theo dõi thông số CPU, RAM, Disk, Mạng của các Node hạ tầng sử dụng OTel hostmetrics)
* **OpenTelemetry Collector** (Theo dõi hiệu năng xử lý, rate nhận/gửi và drop data của OTel Collector Agent)
* **PostgreSQL** (Theo dõi số lượng kết nối, transaction rate, cache hit rate của PostgreSQL database)
* **Spanmetrics Demo Dashboard** (Dashboard sinh metrics tự động từ trace span bằng OTel Spanmetrics connector)

---

## 4. Khoảng trống giám sát phát hiện nhanh (Quick Gap Analysis)
*(Đánh giá dựa trên hiện trạng hạ tầng thực tế)*

* **Hạ tầng thu thập Telemetry (OTel Collector, OpenSearch, Jaeger) đã chạy tốt**: Khác với lý thuyết ban đầu, các thành phần gom Log tập trung và Distributed Tracing đã hoạt động và được tích hợp đầy đủ vào Grafana.
* **Thiếu hụt hệ thống Alerting tự động**: Alertmanager hiện đang bị tắt hoàn toàn. Do đó, mặc dù có dashboard và metric nhưng hệ thống không thể tự động gửi cảnh báo (Slack, Email, PagerDuty) khi xảy ra lỗi.
* **Cần tinh chỉnh các PromQL queries nghiệp vụ**: Các câu lệnh PromQL trong [checkout-slo-metric-queries.md](file:///d:/xbrain/tf4-phase3-repo/docs/cdo08/week1/checkout-slo-metric-queries.md) cần được kiểm chứng và khớp nối với dữ liệu thực tế do OTel Collector thu thập từ service `checkout` (sử dụng gRPC metrics).

---

## 5. Bảng phân công giám sát & Khoảng trống (Observability Mapping Matrix)

| Signal | Service | Owner | Use case | Gap |
|---|---|---|---|---|
| Checkout SLO | `checkout` | Quân / Hải | Theo dõi độ trễ, lưu lượng và tỷ lệ lỗi để bảo vệ SLO `>= 99.0%` | Cần chuyển đổi PromQL sang dạng gRPC metric tương thích thực tế từ OTel |
| Pod readiness / restarts | Toàn bộ ứng dụng | Nam | Đảm bảo các pod chạy ổn định, tự khởi động lại khi ứng dụng bị treo | Thiếu probe trong `values.yaml` và chưa kích hoạt cấu hình tự phục hồi |
| PostgreSQL / Valkey / Kafka health | `postgresql`, `valkey-cart`, `kafka` | Phương | Đảm bảo kết nối thông suốt từ app đến database và hàng đợi sự kiện | Chưa bật persistence (PVC) cho dữ liệu trên EKS; Alertmanager bị tắt |
| Evidence pack | Toàn bộ hệ thống | CDO07 / Hải | Chuẩn hóa tài liệu báo cáo, lưu trữ bằng chứng sự cố và audit | Chưa thống nhất biểu mẫu và thư mục lưu trữ bằng chứng dùng chung của nhóm |
