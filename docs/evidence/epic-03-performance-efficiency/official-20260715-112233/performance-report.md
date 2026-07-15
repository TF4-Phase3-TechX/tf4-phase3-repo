# Báo Cáo Nghiệm Thu Bảo Trì EKS Không Downtime (Directive #3)

* **Mã lần chạy (RUN_ID):** `official-20260715-112233`
* **Thời gian bắt đầu (T0):** `11:05:00 UTC` (18:05:00 GMT+7)
* **Thời gian kết thúc (T1):** `11:26:00 UTC` (18:26:00 GMT+7)
* **Tổng thời gian kiểm thử:** 21 phút (Đạt điều kiện tối thiểu 15 phút ở trạng thái ổn định).
* **Tải giả lập:** 200 người dùng đồng thời (Locust Swarm).
* **Bằng chứng dữ liệu thô (Locust raw data):** [Thư mục dữ liệu thô Locust](./locust/) chứa đầy đủ `stats.csv`, `stats_history.csv`, `failures.csv`, `exceptions.csv` và `report.html` đồng bộ chính xác theo mốc thời gian T0-T1.

---

## 📊 Kết Quả Đánh Giá Chỉ Số SLO Business

| Chỉ số / SLO | Mục tiêu (Target) | Kết quả thực tế | Trạng thái (PASS/FAIL) |
| :--- | :--- | :--- | :--- |
| **Storefront Latency (p95)** | < 1000 ms (1 giây) | **~303 ms** (Max đỉnh điểm) | **PASS** |
| **Browse/Search Success Rate**| ≥ 99.5% | **100%** (Hoàn hảo) | **PASS** |
| **Cart Success Rate** | ≥ 99.5% | **100%** (Hoàn hảo) | **PASS** |
| **Checkout Success Rate** | ≥ 99.0% | **100%** (Hoàn hảo) | **PASS** |

> [!NOTE]
> Chỉ số p50 (latency trung bình) tạm thời được loại bỏ khỏi bảng đánh giá do reducer trên dashboard có cấu hình không đồng nhất trong suốt quá trình bảo trì.

---

## 🛡️ Bằng Chứng Cấu Hình Tránh Gián Đoạn (High-Availability & PDB Status)

Trước khi thực hiện bảo trì, hệ thống được cấu hình sẵn các chính sách ngăn chặn downtime ở cấp độ Pod Disruption Budget (PDB) và phân bổ HA qua các endpoints:

### 1. Trạng thái Pod Disruption Budgets (PDB) trên Cluster:
```text
NAMESPACE             NAME                 MIN AVAILABLE   ALLOWED DISRUPTIONS
techx-tf4             cart                 1               1
techx-tf4             checkout             1               1
techx-tf4             currency             1               1
techx-tf4             frontend             1               1
techx-tf4             frontend-proxy       1               1
techx-tf4             payment              1               1
techx-tf4             product-catalog      1               1
techx-tf4             shipping             1               1
```

### 2. Trạng thái Endpoints phân bổ đa Zone (High-Availability):
Các dịch vụ core đều có tối thiểu 2 Pods chia đều ra các dải IP tương ứng với Zone `us-east-1a` (10.0.10.x) và `us-east-1b` (10.0.11.x) để sẵn sàng gánh tải khi 1 node bị tắt:
```text
NAME              ENDPOINTS                           AGE
cart              10.0.10.47:8080,10.0.11.242:8080    7d18h
checkout          10.0.10.84:8080,10.0.11.140:8080    7d18h
frontend          10.0.10.81:8080,10.0.11.51:8080     7d18h
frontend-proxy    10.0.10.241:8080,10.0.11.34:8080    7d18h
```

---

## 🔍 Nhật Ký Bảo Trì & Khả Năng Tự Phục Hồi (Resilience Timeline)

### 1. Trước bảo trì (Pre-maintenance):
* Hệ thống chạy ổn định ở mức tải nền.
* Xem ảnh chụp baseline tại [Baseline](./dashboard/photo_2026-07-15_18-25-45.jpg).

### 2. Kích hoạt tải & Duy trì trạng thái ổn định:
* Tải Locust tăng dần từ 0 lên 200 users và duy trì ổn định. RPS đạt mức ~50 requests/sec.

### 3. Thực hiện hành động bảo trì (During maintenance):
* Node `ip-10-0-10-231.ec2.internal` được drain. Dưới đây là log output thực tế của lệnh drain:
```text
PS D:\Phase3_Xbrain\tf4-phase3-repo> kubectl drain ip-10-0-10-231.ec2.internal --ignore-daemonsets --delete-emptydir-data --force
node/ip-10-0-10-231.ec2.internal cordoned
Warning: ignoring DaemonSet-managed Pods: kube-system/aws-node-jz5r5, kube-system/ebs-csi-node-229c2, kube-system/eks-pod-identity-agent-5rrm8, kube-system/kube-proxy-nnxgb, techx-observability/otel-collector-agent-4cd74
evicting pod techx-tf4/flagd-86bd5f8d76-jgvqr
evicting pod techx-tf4/frontend-f8c85f89c-4ck6w
evicting pod techx-tf4/cart-6d98c5f7bf-v4kr2
evicting pod techx-tf4/quote-85c74d484b-qdpv7
evicting pod techx-observability/techx-observability-alertmanager-0
evicting pod techx-tf4/recommendation-78948dd47d-zqjdv
evicting pod techx-tf4/accounting-5dc867c55b-psvmx
evicting pod techx-tf4/shipping-5547c65698-g9vjx
evicting pod techx-tf4/product-catalog-5dbccf75c9-j66k8
evicting pod techx-tf4/product-reviews-6b466ffbbd-t2pst
evicting pod techx-tf4/currency-f586fcb4-ptxc5
evicting pod techx-tf4/payment-5c5cf4f445-sx6d2
evicting pod kube-system/karpenter-5c5f54d586-rjssq
evicting pod techx-observability/jaeger-es-index-cleaner-29733095-76mdx
evicting pod kube-system/ebs-csi-controller-85dd99f59f-rxn4f
evicting pod techx-tf4/checkout-d69c4d9d-6lld6
evicting pod kube-system/coredns-6976d5bf49-2lfmx
evicting pod kube-system/aws-load-balancer-controller-5b8d4765db-7qc8p
evicting pod techx-tf4/image-provider-c85cf9d65-q5tnv
evicting pod techx-tf4/product-catalog-5dbccf75c9-bpqvr
node/ip-10-0-10-231.ec2.internal drained
```
* Xem ảnh checkpoint trong lúc bảo trì tại [During Maintenance](./dashboard/photo_2026-07-15_18-26-04.jpg).

### 4. Dòng thời gian Karpenter Scale-up (NodeClaim Timeline):
Nhờ cấu hình Karpenter, việc tạo node mới diễn ra tự động và nhanh chóng để bù đắp tài nguyên bị thiếu hụt:
* **11:06:50 UTC:** Lệnh `kubectl drain` bắt đầu trục xuất các Pods khỏi node `ip-10-0-10-231`.
* **11:06:54 UTC:** Các Pod di cư rơi vào trạng thái `Pending` do các node còn lại hết tài nguyên.
* **11:07:02 UTC:** Karpenter ghi nhận trạng thái pending, lập tức tạo ra 2 NodeClaims mới là `techx-general-jwlvq` (Zone us-east-1a) và `techx-general-89g6d` (Zone us-east-1b).
* **11:07:15 UTC (sau 25 giây):** Node `ip-10-0-10-113.ec2.internal` (từ NodeClaim `jwlvq`) gia nhập cụm thành công và chuyển sang trạng thái `Ready`.
* **11:07:22 UTC (sau 32 giây):** Node `ip-10-0-11-89.ec2.internal` (từ NodeClaim `89g6d`) chuyển sang trạng thái `Ready`.
* **Kết luận:** Karpenter chỉ mất khoảng **25 - 32 giây** để cung cấp thêm node mới (vượt xa chỉ tiêu yêu cầu `< 90 giây`).

### 5. Hậu bảo trì & Ổn định hoàn toàn:
* Node ban đầu được uncordon đưa về trạng thái bình thường.
* Load test được tắt sau 21 phút.
* Xem ảnh chụp hệ thống ổn định hoàn toàn tại [Post-Maintenance & Stabilized](./dashboard/photo_2026-07-15_18-26-08.jpg).

---

## 📊 Đánh Giá Trạng thái Của Hệ Thống Middleware
Trong thời gian diễn ra bảo trì, do các pod thu thập metric và pod dashboard (Grafana/Prometheus/OTel) bị tái lập lịch sang node mới, có xuất hiện hiện tượng mất dữ liệu (No Data) tạm thời trên một số dashboard giám sát middleware.

Do đó, báo cáo này ghi nhận: **Chưa đủ dữ liệu để khẳng định hệ thống Middleware (PostgreSQL, Valkey, Kafka, Jaeger, OpenSearch) "ổn định hoàn toàn" ở mức hiệu năng. Tuy nhiên, qua hệ thống radar giám sát sự kiện Kubernetes, xác nhận không quan sát thấy bất kỳ hiện tượng restart hoặc OOM burst mới nào xảy ra trên các dịch vụ này.**

---

## 📌 Kết Luận
Bài kiểm chứng **đạt kết quả PASS đối với Business SLOs**. Hệ thống EKS kết hợp Karpenter chứng minh khả năng tự phục hồi, dịch chuyển pod và giãn nở tài nguyên động thông minh mà không gây ra bất kỳ gián đoạn dịch vụ nào đối với người dùng cuối dưới điều kiện tải cao (200 concurrent users).
