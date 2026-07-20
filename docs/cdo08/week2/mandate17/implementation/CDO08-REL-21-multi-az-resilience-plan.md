# CDO08-REL-21: Multi-AZ Resilience & Workload Spread Plan

- **Owner chính:** Nam (CDO08 - Security & Reliability)
- **Status:** VERIFIED & COMPLETED
- **Target Directive:** Directive #17 (Mandate 17 - Resilience & Blast-Radius Containment)
- **Target Namespace:** `techx-tf4`
- **Cluster/Region:** `techx-tf4-cluster` / AWS `us-east-1` (`us-east-1a`, `us-east-1b`)

---

## 1. Bối cảnh & Mục tiêu

### Bối cảnh
Theo **Directive #17 (Mandate 17)**, hệ thống sản xuất phải chịu được sự cố gián đoạn đột ngột của toàn bộ một **Availability Zone (AZ)** mà không làm sập luồng doanh thu cốt lõi (**Browse -> Cart -> Checkout**).

### Mục tiêu
1. Đảm bảo tất cả 8 microservices trên Revenue Path (`frontend-proxy`, `frontend`, `cart`, `checkout`, `payment`, `shipping`, `product-catalog`, `currency`) có **tối thiểu 2 replicas** và được trải đều qua cả 2 Availability Zones (`us-east-1a` và `us-east-1b`).
2. Bổ sung cấu hình **`topologySpreadConstraints`** chuẩn mực theo label `topology.kubernetes.io/zone` vào Helm Chart `techx-corp-chart` và manifests `techx-corp-app.yaml`.
3. Đảm bảo `maxSkew: 1` và `whenUnsatisfiable: ScheduleAnyway` để không gây nghẽn (stuck rollout) khi xảy ra surge scaling hoặc node failover.
4. Xây dựng Kịch bản Diễn tập Mất AZ An toàn (**AZ-Loss Demo Runbook**) với Preflight Checklist, Hard-Stop Circuit Breakers và Emergency Rollback Protocol.

---

## 2. Placement Baseline & Risk Resolution

### 2.1 Cấu trúc Node & Availability Zone Baseline
Cụm Kubernetes `techx-tf4-cluster` gồm các EC2 Worker Nodes được phân bổ trên 2 Availability Zones (`us-east-1a` và `us-east-1b`):

| Node Name | IP Address | Availability Zone (`topology.kubernetes.io/zone`) |
| :--- | :--- | :---: |
| `ip-10-0-10-19.ec2.internal` | `10.0.10.19` | **`us-east-1a`** |
| `ip-10-0-10-231.ec2.internal` | `10.0.10.231` | **`us-east-1a`** |
| `ip-10-0-11-217.ec2.internal` | `10.0.11.217` | **`us-east-1b`** |
| `ip-10-0-11-40.ec2.internal` | `10.0.11.40` | **`us-east-1b`** |
| `ip-10-0-11-101.ec2.internal` | `10.0.11.101` | **`us-east-1b`** |

### 2.2 Kết quả Phân bổ Pods Thực tế sau Rollout (Post-Rollout Verification)

Sau khi áp dụng `topologySpreadConstraints` theo `topology.kubernetes.io/zone`, tất cả các dịch vụ đã được phân bổ cân bằng qua cả 2 Availability Zones mà không hề bị Pending:

| Service | Replicas (HPA Min-Max) | PDB (MinAvailable) | Rollout Strategy | Pod Name | Node | AZ | Trạng thái Multi-AZ |
| :--- | :---: | :---: | :---: | :--- | :--- | :---: | :--- |
| **`cart`** | 2 (No HPA) | PDB (1) | RollingUpdate (25%/25%) | `cart-58674557cd-8fcgr`<br>`cart-58674557cd-mt2rz` | `ip-10-0-11-101`<br>`ip-10-0-10-19` | **`us-east-1b`**<br>**`us-east-1a`** | ✅ **RESOLVED (50% in 1a, 50% in 1b)** |
| **`checkout`** | 2 (HPA: 2-3) | PDB (1) | RollingUpdate (25%/25%) | `checkout-74fcb977c-cvzhk`<br>`checkout-74fcb977c-hhfn9` | `ip-10-0-11-101`<br>`ip-10-0-10-19` | **`us-east-1b`**<br>**`us-east-1a`** | ✅ **RESOLVED (50% in 1a, 50% in 1b)** |
| `currency` | 3 (HPA: 2-3) | PDB (1) | RollingUpdate (25%/25%) | `currency-764c5c7c55-gsjdm`<br>`currency-764c5c7c55-whl8h`<br>`currency-764c5c7c55-zszkw` | `ip-10-0-10-231`<br>`ip-10-0-10-19`<br>`ip-10-0-11-40` | `us-east-1a`<br>`us-east-1a`<br>`us-east-1b` | ✅ **RESOLVED (Spread across 1a & 1b)** |
| `frontend` | 3 (HPA: 2-3) | PDB (1) | RollingUpdate (25%/25%) | `frontend-5b896844f8-4mrfm`<br>`frontend-5b896844f8-7x7jx`<br>`frontend-5b896844f8-zhkld` | `ip-10-0-11-40`<br>`ip-10-0-10-19`<br>`ip-10-0-11-217` | `us-east-1b`<br>`us-east-1a`<br>`us-east-1b` | ✅ **RESOLVED (Spread across 1a & 1b)** |
| `frontend-proxy` | 2 (No HPA) | PDB (1) | RollingUpdate (25%/25%) | `frontend-proxy-79658b874b-dsjhj`<br>`frontend-proxy-79658b874b-s6r82` | `ip-10-0-10-231`<br>`ip-10-0-11-217` | `us-east-1a`<br>`us-east-1b` | ✅ **RESOLVED (50% in 1a, 50% in 1b)** |
| `payment` | 2 (No HPA) | PDB (1) | RollingUpdate (25%/25%) | `payment-6d47766ff6-6srvt`<br>`payment-6d47766ff6-fb5rb` | `ip-10-0-10-19`<br>`ip-10-0-11-217` | `us-east-1a`<br>`us-east-1b` | ✅ **RESOLVED (50% in 1a, 50% in 1b)** |
| `product-catalog` | 2 (No HPA) | PDB (1) | RollingUpdate (25%/25%) | `product-catalog-78b9958b94-fpbpf`<br>`product-catalog-78b9958b94-zrdr5` | `ip-10-0-10-19`<br>`ip-10-0-11-40` | `us-east-1a`<br>`us-east-1b` | ✅ **RESOLVED (50% in 1a, 50% in 1b)** |
| `shipping` | 2 (No HPA) | PDB (1) | RollingUpdate (25%/25%) | `shipping-7dbd9d698d-w2wh2`<br>`shipping-7dbd9d698d-x7lws` | `ip-10-0-11-217`<br>`ip-10-0-10-231` | `us-east-1b`<br>`us-east-1a` | ✅ **RESOLVED (50% in 1a, 50% in 1b)** |

---

## 3. AZ-Loss Demo Runbook (Kịch bản Diễn tập Mất AZ An toàn)

### 3.1 Quy tắc An toàn Tuyệt đối (Safety Guardrails)
1. **Không đụng Stateful Managed Migration:** Các Stateful components (`postgresql`, `kafka`, `valkey-cart`) gắn với PVC Volume không bị force evict/migration khi chưa có sự đồng ý của Owner hệ thống dữ liệu.
2. **Khoanh vùng tác động:** Diễn tập AZ Failure được thực hiện bằng phương pháp **AZ Cordon & Controlled Eviction** trên các Node thuộc AZ `us-east-1a`, đảm bảo không làm sập cụm EC2 thật hoặc gián đoạn mạng vật lý.

---

### 3.2 Preflight Checklist (Kiểm tra Tiền diễn tập)

Trước khi thực hiện kịch bản demo cho Mentor, người vận hành **bắt buộc** hoàn thành checklist:

- [ ] **Cluster Node Health:** Tất cả 4 Worker Nodes đều ở trạng thái `Ready` (`kubectl get nodes`).
- [ ] **Revenue Path Workloads Health:** Tất cả 8 Revenue Path Deployments đều có 100% Ready Replicas (`kubectl get deploy -n techx-tf4`).
- [ ] **Active User Traffic Load:** Đang chạy Locust Load Test (tối thiểu 50-200 concurrent users) mô phỏng luồng Browse -> Cart -> Checkout.
- [ ] **Observability Readiness:** Mở Grafana SLO Dashboard để quan sát các chỉ số real-time:
  - Success Rate (Mục tiêu SLO >= 99.5%)
  - Latency p95 / p99 của luồng mua hàng.
- [ ] **Xác định AZ Mục tiêu Diễn tập:** Chọn **`us-east-1a`** (`ip-10-0-10-19.ec2.internal` & `ip-10-0-10-231.ec2.internal`).

---

### 3.3 Các bước Thực thi Demo (AZ Loss Simulation Steps)

#### Bước 1: Khóa Scheduling vào AZ `us-east-1a` (AZ Cordon)
Thực hiện cordon tất cả các Worker Nodes thuộc `us-east-1a` để ngăn Scheduler đưa Pods mới vào AZ này:

```bash
kubectl cordon ip-10-0-10-19.ec2.internal ip-10-0-10-231.ec2.internal
```

#### Bước 2: Di chuyển Workloads khỏi AZ `us-east-1a` (Controlled Eviction/Drain)
Rút các Pods đang chạy ở `us-east-1a` để mô phỏng AZ sập hoàn toàn:

```bash
kubectl drain ip-10-0-10-19.ec2.internal ip-10-0-10-231.ec2.internal \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --grace-period=30 \
  --force
```

#### Bước 3: Kiểm chứng Khả năng Phục hồi (Failover & SLO Evidence Verification)
1. Quan sát Kubernetes Scheduler tự động reschedule các Pods sang AZ còn lại (`us-east-1b`):
   ```bash
   kubectl get pods -n techx-tf4 -o wide
   ```
2. Xác nhận 100% 8 Revenue Path Services tiếp tục phục vụ lưu lượng trên AZ `us-east-1b`.
3. Kiểm tra Grafana SLO Dashboard: **Success Rate giữ >= 99.5%**, không có request nào bị thất bại nặng.

---

### 3.4 Điều kiện Dừng Khẩn cấp (Hard-Stop / Circuit Breaker Conditions)

Lập tức **KÍCH HOẠT EMERGENCY ROLLBACK** nếu vi phạm bất kỳ điều kiện nào sau đây:

| Mã Điều kiện | Ngưỡng Vi phạm | Hành động Khẩn cấp |
| :--- | :--- | :--- |
| 🛑 **HARD-STOP-01** | Bất kỳ Pod nào thuộc 8 Revenue Path Services bị kẹt ở trạng thái **`Pending` > 60 giây** do thiếu capacity ở AZ còn lại. | Kích hoạt Rollback lập tức. |
| 🛑 **HARD-STOP-02** | Error Rate của luồng Browse -> Cart -> Checkout tăng vượt quá **1.0%** (Success Rate < 99.0%) kéo dài **> 30 giây**. | Kích hoạt Rollback lập tức. |
| 🛑 **HARD-STOP-03** | Bất kỳ Stateful Component (`postgresql`, `kafka`, `valkey-cart`) bị rơi vào trạng thái `CrashLoopBackOff` hoặc lỗi mount PVC. | Kích hoạt Rollback lập tức. |

---

### 3.5 Emergency Rollback Runbook (Quy trình Khôi phục An toàn)

Khi buổi diễn tập hoàn tất hoặc khi vi phạm Hard-Stop condition, thực hiện quy trình rollback khôi phục trạng thái ban đầu:

#### Lệnh 1: Mở lại Scheduling cho Nodes ở `us-east-1a` (Uncordon)
```bash
kubectl uncordon ip-10-0-10-19.ec2.internal ip-10-0-10-231.ec2.internal
```

#### Lệnh 2: Kích hoạt Rebalance Rollout cho Revenue Path Services
Khôi phục phân bố cân bằng 50/50 qua cả 2 AZs:
```bash
kubectl rollout restart deployment cart checkout currency frontend frontend-proxy payment product-catalog shipping -n techx-tf4
```

#### Lệnh 3: Xác minh Trạng thái Phục hồi & Sync GitOps
```bash
# Kiểm tra lại Pod Placement 50/50 qua 2 AZs
kubectl get pods -n techx-tf4 \
  -l "app.kubernetes.io/component in (frontend-proxy,frontend,cart,checkout,payment,shipping,product-catalog,currency)" \
  -o custom-columns="SERVICE:.metadata.labels.app\.kubernetes\.io/component,POD:.metadata.name,NODE:.spec.nodeName,STATUS:.status.phase"
```

---

## 4. Command `kubectl` để Mentor Tự Verify (Verification Commands)

Mentor hoặc Tech Lead có thể tự chạy các lệnh `kubectl` sau để kiểm chứng:

```bash
# 1. Kiểm tra danh sách Node và Availability Zone tương ứng
kubectl get nodes -L topology.kubernetes.io/zone

# 2. Kiểm tra chi tiết Placement (Service -> Pod -> Node) cho 8 Revenue Path Services
kubectl get pods -n techx-tf4 \
  -l "app.kubernetes.io/component in (frontend-proxy,frontend,cart,checkout,payment,shipping,product-catalog,currency)" \
  -o custom-columns="SERVICE:.metadata.labels.app\.kubernetes\.io/component,POD:.metadata.name,NODE:.spec.nodeName,STATUS:.status.phase"

# 3. Kiểm tra Replicas, HPA và PodDisruptionBudget (PDB)
kubectl get deploy,hpa,pdb -n techx-tf4
```

---

## 5. Definition of Done (DoD) Checklist

- [x] Đã hoàn thành Placement Baseline & Risk Assessment audit.
- [x] Rendered manifest chứa `topologySpreadConstraints` theo đúng label selector cho 8 Revenue Path services.
- [x] Rollout không tạo Pod Pending kéo dài (tất cả 18 Pods đều 1/1 Running thành công).
- [x] Pod placement sau rollout trải đều qua 2 Availability Zones (`us-east-1a` và `us-east-1b`).
- [x] Gỡ bỏ 100% Single-AZ Critical Risk cho `cart` và `checkout`.
- [x] Xây dựng đầy đủ AZ-Loss Demo Runbook với Preflight Checklist, Hard-Stop Circuit Breakers và Emergency Rollback Protocol.
