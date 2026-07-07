# Kiểm kê hệ thống giám sát hiện có (Observability Inventory)

## 1. Tình trạng các thành phần cốt lõi (Components Status)
*(Trạng thái pod thực tế kiểm tra trên cụm Kubernetes `w10`)*

* **Prometheus** (Thu thập metric): **Đang chạy** (Pod `prometheus-kube-prometheus-stack-prometheus-0` ở trạng thái Running 2/2)
* **Grafana** (Trực quan hóa dashboard): **Đang chạy** (Pod `kube-prometheus-stack-grafana-5b6465849f-v8r9j` ở trạng thái Running 3/3)
* **Jaeger** (Distributed tracing): **Không có** (Chưa triển khai trên cluster)
* **OpenSearch / Elasticsearch** (Lưu trữ log): **Không có** (Chưa triển khai trên cluster)
* **OTel Collector** (Gom log/metric/trace): **Không có** (Chưa triển khai trên cluster)
* **Alertmanager** (Cảnh báo): **Lỗi / Đang khởi tạo** (Pod `alertmanager-kube-prometheus-stack-alertmanager-0` kẹt ở trạng thái `Init:0/1`)

### Bằng chứng trạng thái Pod (Output `kubectl get pods -n monitoring`):
```text
NAME                                                        READY   STATUS     RESTARTS         AGE
alertmanager-kube-prometheus-stack-alertmanager-0           0/2     Init:0/1   0                19d
kube-prometheus-stack-grafana-5b6465849f-v8r9j              3/3     Running    15 (6m44s ago)   19d
kube-prometheus-stack-kube-state-metrics-5ff4575db7-8wcxj   1/1     Running    26 (6m6s ago)    19d
kube-prometheus-stack-operator-d69fb75b9-ppkn8              1/1     Running    26 (6m44s ago)   19d
kube-prometheus-stack-prometheus-node-exporter-hxp6h        1/1     Running    12 (6m44s ago)   19d
prometheus-kube-prometheus-stack-prometheus-0               2/2     Running    20 (6m44s ago)   19d
```

---

## 2. Kiểm kê Data Source trên Grafana
*(Kiểm tra thực tế tại cấu hình Data Sources của Grafana)*

* **Prometheus Data Source:** **Đã kết nối** (URL: `http://kube-prometheus-stack-prometheus.monitoring:9090/`. Kết quả test: *"Successfully queried the Prometheus API."*)
* **OpenSearch/Loki Data Source:** **Không có** (Chưa được cấu hình)
* **Jaeger/Tempo Data Source:** **Không có** (Chưa được cấu hình)
* **Alertmanager Data Source:** **Lỗi / Không thể kết nối** (URL: `http://kube-prometheus-stack-alertmanager.monitoring:9093/`. Kết quả test báo lỗi kết nối do pod Alertmanager chưa Ready)

---

## 3. Danh sách Dashboard hiện hành
*(Hiện tại cụm có 28 dashboards mặc định được lấy trực tiếp từ API của Grafana. Trạng thái dữ liệu được đánh giá dựa trên các namespace hiện hữu)*

### A. Nhóm Giám sát Tài nguyên Kubernetes (Compute Resources)
* **Kubernetes / Compute Resources / Cluster** (Giám sát CPU, RAM, Network toàn cụm - **Có số liệu**)
* **Kubernetes / Compute Resources / Multi-Cluster** (Giám sát đa cụm - **Có số liệu**)
* **Kubernetes / Compute Resources / Namespace (Pods)** (Tài nguyên Pods theo namespace - **Có số liệu** của `monitoring` & `demo`)
* **Kubernetes / Compute Resources / Namespace (Workloads)** (Tài nguyên Workloads theo namespace - **Có số liệu**)
* **Kubernetes / Compute Resources / Node (Pods)** (Phân bổ Pod trên từng Node - **Có số liệu**)
* **Kubernetes / Compute Resources / Pod** (Chi tiết tài nguyên của từng Pod cụ thể - **Có số liệu**)
* **Kubernetes / Compute Resources / Workload** (Tài nguyên của Deployments, DaemonSets, StatefulSets - **Có số liệu**)

### B. Nhóm Giám sát Mạng Kubernetes (Networking)
* **Kubernetes / Networking / Cluster** (Traffic mạng toàn cụm - **Có số liệu**)
* **Kubernetes / Networking / Namespace (Pods)** (Traffic mạng các Pod theo namespace - **Có số liệu**)
* **Kubernetes / Networking / Namespace (Workload)** (Traffic mạng các Workloads theo namespace - **Có số liệu**)
* **Kubernetes / Networking / Pod** (Traffic chi tiết từng Pod - **Có số liệu**)
* **Kubernetes / Networking / Workload** (Traffic chi tiết từng Workload - **Có số liệu**)

### C. Nhóm Giám sát Kubernetes Control Plane & Core Services
* **Kubernetes / API server** (Hiệu năng của Kube-API-Server - **Có số liệu**)
* **Kubernetes / Controller Manager** (Trạng thái Controller Manager - **Có số liệu**)
* **Kubernetes / Kubelet** (Trạng thái và hiệu năng của các Kubelets - **Có số liệu**)
* **Kubernetes / Scheduler** (Hiệu năng lập lịch của Scheduler - **Có số liệu**)
* **Kubernetes / Proxy** (Hiệu năng định tuyến của Kube-Proxy - **Có số liệu**)
* **CoreDNS** (Hiệu năng dịch vụ phân giải DNS trong cụm - **Có số liệu**)
* **etcd** (Hiệu năng và độ trễ ghi dữ liệu của etcd - **Có số liệu**)

### D. Nhóm Giám sát Tải Hạ tầng máy chủ (Node Exporter)
* **Node Exporter / Nodes** (Thông số chi tiết CPU, RAM, Disk, IO của Node - **Có số liệu**)
* **Node Exporter / USE Method / Cluster** (Chỉ số USE cho toàn cụm - **Có số liệu**)
* **Node Exporter / USE Method / Node** (Chỉ số USE cho từng Node - **Có số liệu**)
* **Node Exporter / AIX** (Dành cho máy chủ AIX - **Trống / Không có thiết bị**)
* **Node Exporter / MacOS** (Dành cho máy chủ MacOS - **Trống / Không có thiết bị**)

### E. Nhóm Giám sát Thành phần Stack Giám sát (Self-Monitoring)
* **Grafana Overview** (Tải, RAM, Thread và API calls của Grafana - **Có số liệu**)
* **Prometheus / Overview** (Sức khỏe TSDB, ingestion rate của Prometheus - **Có số liệu**)
* **Alertmanager / Overview** (Tình trạng gửi cảnh báo của Alertmanager - **Trắng số (No data)** do Pod Alertmanager kẹt lỗi)
* **Kubernetes / Persistent Volumes** (Trạng thái và dung lượng các Storage Volumes - **Có số liệu**)

---

## 4. Khoảng trống giám sát phát hiện nhanh (Quick Gap Analysis)
*(Dựa trên những gì kiểm kê ở trên, hệ thống đang thiếu hụt các thành phần sau để giám sát luồng Checkout)*

* **Chưa có hạ tầng gom Trace và Log:** Chưa triển khai OTel Collector, Jaeger và OpenSearch nên hiện tại hệ thống hoàn toàn mù thông tin về Log tập trung và Distributed Tracing của luồng gọi chéo giữa các service (Checkout, Payment, Cart, v.v.).
* **Thiếu hụt Dashboards đo lường nghiệp vụ:** Các dashboard hiện có chỉ phục vụ cho việc kiểm kê hạ tầng Kubernetes và máy chủ Node. Hoàn toàn chưa có dashboard giám sát chỉ số RED (Rate, Errors, Duration) hoặc các chỉ số nghiệp vụ của luồng Checkout.
* **Alertmanager chưa hoạt động:** Pod Alertmanager bị kẹt ở bước Init, cần kiểm tra cấu hình hoặc log khởi tạo để khắc phục, tránh việc hệ thống không thể bắn alert khi xảy ra sự cố.
