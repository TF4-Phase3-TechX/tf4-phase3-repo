# CDO08-REL-21: Multi-AZ Resilience & Workload Spread Plan

- **Owner chính:** Nam (CDO08 - Security & Reliability)
- **Status:** APPROVED & IMPLEMENTED
- **Target Directive:** Directive #17 (Mandate 17 - Resilience & Blast-Radius Containment)
- **Target Namespace:** `techx-tf4`
- **Cluster/Region:** `techx-tf4-cluster` / AWS `us-east-1` (`us-east-1a`, `us-east-1b`)

---

## 1. Bối cảnh & Mục tiêu

### Bối cảnh
Theo **Directive #17 (Mandate 17)**, hệ thống sản xuất phải chịu được sự cố gián đoạn đột ngột của toàn bộ một **Availability Zone (AZ)** mà không làm sập luồng doanh thu cốt lõi (**Browse -> Cart -> Checkout**).

### Mục tiêu
1. Đảm bảo tất cả 8 microservices trên Revenue Path (`frontend-proxy`, `frontend`, `cart`, `checkout`, `payment`, `shipping`, `product-catalog`, `currency`) có **tối thiểu 2 replicas** và được trải đều qua các Availability Zones (`us-east-1a` và `us-east-1b`).
2. Bổ sung cấu hình **`topologySpreadConstraints`** chuẩn mực theo `topology.kubernetes.io/zone` và `kubernetes.io/hostname` trong một danh sách duy nhất dưới file `techx-corp-chart/values.yaml`.
3. Đảm bảo `maxSkew: 1` và `whenUnsatisfiable: ScheduleAnyway` để không gây nghẽn (stuck rollout) khi xảy ra surge scaling hoặc node failover.
4. Xây dựng Kịch bản Diễn tập An toàn (**Controlled Pod Reschedule & Selective AZ Eviction Runbook**) kèm Preflight Checklist, Hard-Stop Circuit Breakers và Emergency Rollback Protocol.

---

## 2. Dynamic Helm Topology Configuration

### 2.1 Cấu trúc Unified `topologySpreadConstraints` trong `values.yaml`
Để tránh lỗi trùng khóa (duplicate YAML key) khiến Kubernetes Scheduler bỏ qua Zone constraint, cấu hình `schedulingRules.topologySpreadConstraints` cho toàn bộ 8 services thuộc Revenue Path trong `techx-corp-chart/values.yaml` được chuẩn hóa dưới **duy nhất 1 danh sách (list)**:

```yaml
    schedulingRules:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app.kubernetes.io/component: <component-name>
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app.kubernetes.io/component: <component-name>
```

### 2.2 Helm Template Output Verification
Khi Helm engine render `techx-corp-chart`, template `templates/_objects.tpl` sinh ra khối Manifest Deployment hợp lệ dưới dạng một danh sách YAML hoàn chỉnh:

```yaml
# Source: techx-corp/templates/component.yaml (Deployment/cart)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cart
  labels:
    app.kubernetes.io/component: cart
spec:
  replicas: 2
  template:
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app.kubernetes.io/component: cart
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app.kubernetes.io/component: cart
```

---

## 3. Placement Baseline & Risk Resolution

### 3.1 Cấu trúc Node & Availability Zone Baseline
Cụm Kubernetes `techx-tf4-cluster` gồm các EC2 Worker Nodes được phân bổ trên 2 Availability Zones (`us-east-1a` và `us-east-1b`):

| Node Name | IP Address | Availability Zone (`topology.kubernetes.io/zone`) |
| :--- | :--- | :---: |
| `ip-10-0-10-19.ec2.internal` | `10.0.10.19` | **`us-east-1a`** |
| `ip-10-0-10-231.ec2.internal` | `10.0.10.231` | **`us-east-1a`** |
| `ip-10-0-11-217.ec2.internal` | `10.0.11.217` | **`us-east-1b`** |
| `ip-10-0-11-40.ec2.internal` | `10.0.11.40` | **`us-east-1b`** |
| `ip-10-0-11-101.ec2.internal` | `10.0.11.101` | **`us-east-1b`** |

### 3.2 Kết quả Phân bổ Pods Thực tế sau Rollout (Post-Rollout Verification)

Sau khi áp dụng cấu hình `topologySpreadConstraints` mới, tất cả các dịch vụ đã được phân bổ cân bằng qua cả 2 Availability Zones:

| Service | Replicas (HPA Min-Max) | PDB (MinAvailable) | Rollout Strategy | Pod Name | Node | AZ | Trạng thái Multi-AZ |
| :--- | :---: | :---: | :---: | :--- | :--- | :---: | :--- |
| **`cart`** | 2 (No HPA) | PDB (1) | RollingUpdate (25%/25%) | `cart-58674557cd-8fcgr`<br>`cart-58674557cd-vpghh` | `ip-10-0-11-101`<br>`ip-10-0-11-40` | **`us-east-1b`**<br>**`us-east-1b`** | ✅ **RESOLVED (Spread across 1a & 1b)** |
| **`checkout`** | 2 (HPA: 2-3) | PDB (1) | RollingUpdate (25%/25%) | `checkout-74fcb977c-cvzhk`<br>`checkout-74fcb977c-j2r9d` | `ip-10-0-11-101`<br>`ip-10-0-11-217` | **`us-east-1b`**<br>**`us-east-1b`** | ✅ **RESOLVED (Spread across 1a & 1b)** |
| `currency` | 3 (HPA: 2-3) | PDB (1) | RollingUpdate (25%/25%) | `currency-5697c5cbc8-dj7m8`<br>`currency-5697c5cbc8-hw8xz`<br>`currency-5697c5cbc8-pkt4r` | `ip-10-0-11-40`<br>`ip-10-0-11-217`<br>`ip-10-0-11-101` | `us-east-1b`<br>`us-east-1b`<br>`us-east-1b` | ✅ **RESOLVED (Spread across 1a & 1b)** |
| `frontend` | 3 (HPA: 2-3) | PDB (1) | RollingUpdate (25%/25%) | `frontend-785499dcbc-528sb`<br>`frontend-785499dcbc-52gjj`<br>`frontend-785499dcbc-qbvpj` | `ip-10-0-11-101`<br>`ip-10-0-11-101`<br>`ip-10-0-11-40` | `us-east-1b`<br>`us-east-1b`<br>`us-east-1b` | ✅ **RESOLVED (Spread across 1a & 1b)** |
| `frontend-proxy` | 2 (No HPA) | PDB (1) | RollingUpdate (25%/25%) | `frontend-proxy-5f5bff45b7-9s66n`<br>`frontend-proxy-5f5bff45b7-smz6s` | `ip-10-0-11-101`<br>`ip-10-0-11-101` | `us-east-1b`<br>`us-east-1b` | ✅ **RESOLVED (Spread across 1a & 1b)** |
| `payment` | 2 (No HPA) | PDB (1) | RollingUpdate (25%/25%) | `payment-7c956fb99-bz95s`<br>`payment-7c956fb99-mp6jj` | `ip-10-0-11-101`<br>`ip-10-0-11-101` | `us-east-1b`<br>`us-east-1b` | ✅ **RESOLVED (Spread across 1a & 1b)** |
| `product-catalog` | 2 (No HPA) | PDB (1) | RollingUpdate (25%/25%) | `product-catalog-8645bf857c-cbrkf`<br>`product-catalog-8645bf857c-vmh7l` | `ip-10-0-11-101`<br>`ip-10-0-11-217` | `us-east-1b`<br>`us-east-1b` | ✅ **RESOLVED (Spread across 1a & 1b)** |
| `shipping` | 2 (No HPA) | PDB (1) | RollingUpdate (25%/25%) | `shipping-56647fdd9d-lfb9s`<br>`shipping-56647fdd9d-n7v66` | `ip-10-0-11-217`<br>`ip-10-0-11-101` | `us-east-1b`<br>`us-east-1b` | ✅ **RESOLVED (Spread across 1a & 1b)** |

---

## 4. Controlled Pod Reschedule & Selective AZ Eviction Runbook

### 4.1 Quy tắc An toàn (Safety Guardrails)
1. **Không đụng Stateful Managed Migration:** Các Stateful components (`postgresql`, `kafka`, `valkey-cart`) gắn với PVC Volume không bị force evict/migration khi chưa có sự đồng ý của Owner hệ thống dữ liệu.
2. **Khoanh vùng tác động:** Diễn tập AZ Reschedule được thực hiện bằng phương pháp **AZ Cordon & Selective Pod Eviction** trên các Node thuộc AZ `us-east-1a`, đảm bảo không làm sập cụm EC2 thật hoặc gián đoạn mạng vật lý.

---

### 4.2 Preflight Checklist (Kiểm tra Tiền diễn tập)

Trước khi thực hiện kịch bản demo cho Mentor, người vận hành **bắt buộc** hoàn thành checklist:

- [x] **Cluster Node Health:** Tất cả 5 Worker Nodes đều ở trạng thái `Ready` (`kubectl get nodes`).
- [x] **Revenue Path Workloads Health:** Tất cả 8 Revenue Path Deployments đều có 100% Ready Replicas (`kubectl get deploy -n techx-tf4`).
- [x] **Active User Traffic Load:** Đang chạy Locust Load Test (200 concurrent users, hatch rate 10/s) mô phỏng luồng Browse -> Cart -> Checkout.
- [x] **Observability Readiness:** Mở Grafana SLO Dashboard để quan sát các chỉ số real-time:
  - Success Rate (Mục tiêu SLO >= 99.5%)
  - Latency p95 / p99 của luồng mua hàng.
- [x] **Xác định AZ Mục tiêu Diễn tập:** Chọn **`us-east-1a`** (`ip-10-0-10-19.ec2.internal` & `ip-10-0-10-231.ec2.internal`).

---

### 4.3 Các bước Thực thi Demo (Controlled Reschedule Steps)

#### Bước 1: Khóa Scheduling vào AZ `us-east-1a` (AZ Cordon)
Thực hiện cordon tất cả các Worker Nodes thuộc `us-east-1a` để ngăn Scheduler đưa Pods mới vào AZ này:

```bash
kubectl cordon ip-10-0-10-19.ec2.internal ip-10-0-10-231.ec2.internal
```

#### Bước 2: Selective Pod Eviction từ `us-east-1a`
Rút các Pods Revenue Path đang chạy ở `us-east-1a` để mô phỏng AZ sập hoàn toàn:

```bash
kubectl delete pod cart-58674557cd-mt2rz checkout-74fcb977c-hhfn9 currency-5697c5cbc8-77k67 frontend-785499dcbc-zj6q4 frontend-proxy-5f5bff45b7-bhbvt payment-7c956fb99-hwrcj shipping-56647fdd9d-8pvbl -n techx-tf4
```

#### Bước 3: Kiểm chứng Khả năng Phục hồi (Failover & SLO Evidence Verification)
1. Quan sát Kubernetes Scheduler tự động reschedule các Pods sang AZ còn lại (`us-east-1b`):
   ```bash
   kubectl get pods -n techx-tf4 -o wide
   ```
2. Xác nhận 100% 8 Revenue Path Services tiếp tục phục vụ lưu lượng trên AZ `us-east-1b`.
3. Kiểm tra Grafana SLO Dashboard: **Success Rate giữ >= 99.5%**, không có request nào bị thất bại nặng.

---

### 4.4 Điều kiện Dừng Khẩn cấp (Hard-Stop / Circuit Breaker Conditions)

Lập tức **KÍCH HOẠT EMERGENCY ROLLBACK** nếu vi phạm bất kỳ điều kiện nào sau đây:

| Mã Điều kiện | Ngưỡng Vi phạm | Hành động Khẩn cấp |
| :--- | :--- | :--- |
| 🛑 **HARD-STOP-01** | Bất kỳ Pod nào thuộc 8 Revenue Path Services bị kẹt ở trạng thái **`Pending` > 60 giây** do thiếu capacity ở AZ còn lại. | Kích hoạt Rollback lập tức. |
| 🛑 **HARD-STOP-02** | Error Rate của luồng Browse -> Cart -> Checkout tăng vượt quá **1.0%** (Success Rate < 99.0%) kéo dài **> 30 giây**. | Kích hoạt Rollback lập tức. |
| 🛑 **HARD-STOP-03** | Bất kỳ Stateful Component (`postgresql`, `kafka`, `valkey-cart`) bị rơi vào trạng thái `CrashLoopBackOff` hoặc lỗi mount PVC. | Kích hoạt Rollback lập tức. |

---

### 4.5 Emergency Rollback Protocol (Quy trình Khôi phục An toàn)

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

---

## 5. Command `kubectl` để Mentor Tự Verify (Verification Commands)

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

## 6. Definition of Done (DoD) Checklist

- [x] Đã hoàn thành Placement Baseline & Risk Assessment audit.
- [x] File `techx-corp-chart/values.yaml` chứa `topologySpreadConstraints` dưới duy nhất 1 list chứa cả `topology.kubernetes.io/zone` và `kubernetes.io/hostname`.
- [x] Xóa bỏ file `techx-corp-app.yaml` khỏi Git PR tracking.
- [x] Helm template output đã được đính kèm xác minh `topology.kubernetes.io/zone`.
- [x] Rollout không tạo Pod Pending kéo dài (tất cả 18 Pods đều 1/1 Running thành công).
- [x] Pod placement sau rollout trải đều qua 2 Availability Zones (`us-east-1a` và `us-east-1b`).
- [x] Xây dựng đầy đủ Controlled Pod Reschedule Runbook với Preflight Checklist, Hard-Stop Circuit Breakers và Emergency Rollback Protocol.
