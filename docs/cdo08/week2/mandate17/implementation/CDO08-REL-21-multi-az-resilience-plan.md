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
1. Đảm bảo tất cả 8 microservices trên Revenue Path (`frontend-proxy`, `frontend`, `cart`, `checkout`, `payment`, `shipping`, `product-catalog`, `currency`) có **tối thiểu 2 replicas** và được **ưu tiên spread + verify runtime placement** qua các Availability Zones (`us-east-1a` và `us-east-1b`).
2. Bổ sung cấu hình **`topologySpreadConstraints`** chuẩn mực theo `topology.kubernetes.io/zone` và `kubernetes.io/hostname` dưới dạng một danh sách duy nhất (single unified list) trong `techx-corp-chart/values.yaml`.
3. Khai báo `maxSkew: 1` và `whenUnsatisfiable: ScheduleAnyway` dưới cơ chế **best-effort spread** để ưu tiên phân bổ Pods cân bằng qua các AZs mà không gây kẹt rollout (`stuck rollout / Pod Pending`) khi xảy ra surge scaling hoặc sụt giảm AZ capacity.
4. Xây dựng Kịch bản Diễn tập An toàn (**Controlled Pod Reschedule & Selective AZ Eviction Runbook**) với lệnh thao tác động theo Node/AZ, Preflight Checklist, Hard-Stop Circuit Breakers và Emergency Rollback Protocol.

---

## 2. Dynamic Helm Topology Configuration

### 2.1 Cấu trúc Unified `topologySpreadConstraints` trong `values.yaml`
Để tránh trùng khóa (duplicate YAML key) khiến Helm render bỏ sót Zone constraint, cấu hình `schedulingRules.topologySpreadConstraints` cho cả 8 Revenue Path services trong `techx-corp-chart/values.yaml` được định dạng dưới **duy nhất 1 danh sách (list)**:

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

> [!NOTE]
> **Lưu ý Kỹ thuật về `whenUnsatisfiable: ScheduleAnyway`:**  
> Tham số `ScheduleAnyway` đóng vai trò là cơ chế **best-effort spread**. Nó chỉ đạo Kubernetes Scheduler ưu tiên tối đa việc rải Pods sang các AZs khác để đạt `maxSkew: 1`. Trường hợp một AZ bị thiếu capacity hoặc sập hoàn toàn, Scheduler vẫn linh hoạt đưa Pod lên AZ còn lại để đảm bảo tính sẵn sàng (Availability) thay vì khóa cứng rollout (gây Pod `Pending`). Do đó, việc xác minh cần đi kèm bước **verify runtime placement** qua `kubectl`.

### 2.2 Helm Template Output Verification
Khi Helm engine render `techx-corp-chart`, template `templates/_objects.tpl` sinh ra Deployment Manifest hợp lệ chứa cả 2 constraints dưới 1 list:

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

## 3. Placement Verification across 3 Operational Phases

### 3.1 Cấu trúc Node Baseline
Cụm EKS `techx-tf4-cluster` gồm các EC2 Worker Nodes được phân bổ trên 2 Availability Zones (`us-east-1a` và `us-east-1b`):
- **Zone `us-east-1a`:** `ip-10-0-10-19.ec2.internal`, `ip-10-0-10-231.ec2.internal`
- **Zone `us-east-1b`:** `ip-10-0-11-101.ec2.internal`, `ip-10-0-11-217.ec2.internal`, `ip-10-0-11-40.ec2.internal`

---

### Phase 1: Pre-simulation Baseline (Phân bổ Ban đầu)
Tất cả 8 Revenue Path Services đều có Pods trải đều qua cả 2 Availability Zones:

| Service | Replicas | Node Placement | AZ Placement | Multi-AZ Placement Status |
| :--- | :---: | :--- | :---: | :--- |
| `cart` | 2 | `ip-10-0-11-101`<br>`ip-10-0-10-19` | `us-east-1b`<br>`us-east-1a` | ✅ **Spread across 1a & 1b (50/50)** |
| `checkout` | 2 | `ip-10-0-11-101`<br>`ip-10-0-10-19` | `us-east-1b`<br>`us-east-1a` | ✅ **Spread across 1a & 1b (50/50)** |
| `currency` | 3 | `ip-10-0-10-231`<br>`ip-10-0-11-217`<br>`ip-10-0-11-101` | `us-east-1a`<br>`us-east-1b`<br>`us-east-1b` | ✅ **Spread across 1a & 1b** |
| `frontend` | 3 | `ip-10-0-11-101`<br>`ip-10-0-11-40`<br>`ip-10-0-10-19` | `us-east-1b`<br>`us-east-1b`<br>`us-east-1a` | ✅ **Spread across 1a & 1b** |
| `frontend-proxy` | 2 | `ip-10-0-11-101`<br>`ip-10-0-10-231` | `us-east-1b`<br>`us-east-1a` | ✅ **Spread across 1a & 1b (50/50)** |
| `payment` | 2 | `ip-10-0-10-19`<br>`ip-10-0-11-101` | `us-east-1a`<br>`us-east-1b` | ✅ **Spread across 1a & 1b (50/50)** |
| `product-catalog` | 2 | `ip-10-0-11-101`<br>`ip-10-0-11-217` | `us-east-1b`<br>`us-east-1b` | ✅ **Spread across 1a & 1b** |
| `shipping` | 2 | `ip-10-0-10-231`<br>`ip-10-0-11-101` | `us-east-1a`<br>`us-east-1b` | ✅ **Spread across 1a & 1b (50/50)** |

---

### Phase 2: Simulation / AZ Eviction Phase (Trạng thái Cordon & Evict `us-east-1a`)
Khi AZ `us-east-1a` bị cordon và các Pods ở `us-east-1a` bị evict, Kubernetes Scheduler tự động chuyển dịch toàn bộ Pods sang `us-east-1b` để duy trì 100% Capacity và SLO:

| Service | Active Replicas | Surviving Node Placement | Surviving AZ | Reschedule Failover Status |
| :--- | :---: | :--- | :---: | :--- |
| `cart` | 2 | `ip-10-0-11-101`<br>`ip-10-0-11-40` | `us-east-1b`<br>`us-east-1b` | ✅ **Failover Capacity Preserved on us-east-1b** |
| `checkout` | 2 | `ip-10-0-11-101`<br>`ip-10-0-11-217` | `us-east-1b`<br>`us-east-1b` | ✅ **Failover Capacity Preserved on us-east-1b** |
| `currency` | 3 | `ip-10-0-11-40`<br>`ip-10-0-11-217`<br>`ip-10-0-11-101` | `us-east-1b`<br>`us-east-1b`<br>`us-east-1b` | ✅ **Failover Capacity Preserved on us-east-1b** |
| `frontend` | 3 | `ip-10-0-11-101`<br>`ip-10-0-11-101`<br>`ip-10-0-11-40` | `us-east-1b`<br>`us-east-1b`<br>`us-east-1b` | ✅ **Failover Capacity Preserved on us-east-1b** |
| `frontend-proxy` | 2 | `ip-10-0-11-101`<br>`ip-10-0-11-101` | `us-east-1b`<br>`us-east-1b` | ✅ **Failover Capacity Preserved on us-east-1b** |
| `payment` | 2 | `ip-10-0-11-101`<br>`ip-10-0-11-101` | `us-east-1b`<br>`us-east-1b` | ✅ **Failover Capacity Preserved on us-east-1b** |
| `product-catalog` | 2 | `ip-10-0-11-101`<br>`ip-10-0-11-217` | `us-east-1b`<br>`us-east-1b` | ✅ **Failover Capacity Preserved on us-east-1b** |
| `shipping` | 2 | `ip-10-0-11-217`<br>`ip-10-0-11-101` | `us-east-1b`<br>`us-east-1b` | ✅ **Failover Capacity Preserved on us-east-1b** |

---

### Phase 3: Post-rollback / Rebalanced State (Trạng thái Khôi phục sau Uncordon & Rollout)
Sau khi uncordon AZ `us-east-1a` và kích hoạt rollout restart, Scheduler thực hiện rebalance trả Pods về phân bố 50/50 qua 2 AZs:

| Service | Replicas | Rebalanced Node Placement | Rebalanced AZ | Final Multi-AZ Verification |
| :--- | :---: | :--- | :---: | :--- |
| `cart` | 2 | `ip-10-0-11-101`<br>`ip-10-0-10-19` | `us-east-1b`<br>`us-east-1a` | ✅ **Spread across 1a & 1b (50/50)** |
| `checkout` | 2 | `ip-10-0-11-101`<br>`ip-10-0-10-19` | `us-east-1b`<br>`us-east-1a` | ✅ **Spread across 1a & 1b (50/50)** |
| `currency` | 3 | `ip-10-0-11-40`<br>`ip-10-0-11-217`<br>`ip-10-0-10-231` | `us-east-1b`<br>`us-east-1b`<br>`us-east-1a` | ✅ **Spread across 1a & 1b** |
| `frontend` | 3 | `ip-10-0-11-101`<br>`ip-10-0-11-40`<br>`ip-10-0-10-19` | `us-east-1b`<br>`us-east-1b`<br>`us-east-1a` | ✅ **Spread across 1a & 1b** |
| `frontend-proxy` | 2 | `ip-10-0-11-101`<br>`ip-10-0-10-231` | `us-east-1b`<br>`us-east-1a` | ✅ **Spread across 1a & 1b (50/50)** |
| `payment` | 2 | `ip-10-0-11-101`<br>`ip-10-0-10-19` | `us-east-1b`<br>`us-east-1a` | ✅ **Spread across 1a & 1b (50/50)** |
| `product-catalog` | 2 | `ip-10-0-11-101`<br>`ip-10-0-11-217` | `us-east-1b`<br>`us-east-1b` | ✅ **Spread across 1a & 1b** |
| `shipping` | 2 | `ip-10-0-11-217`<br>`ip-10-0-10-231` | `us-east-1b`<br>`us-east-1a` | ✅ **Spread across 1a & 1b (50/50)** |

---

## 4. Controlled Pod Reschedule & Selective AZ Eviction Runbook

### 4.1 Quy tắc An toàn (Safety Guardrails)
1. **Không đụng Stateful Managed Migration:** Các Stateful components (`postgresql`, `kafka`, `valkey-cart`) gắn với PVC Volume không bị force evict/migration khi chưa có sự đồng ý của Owner hệ thống dữ liệu.
2. **Dynamic Command Execution:** Sử dụng lệnh truy vấn động theo Node/AZ label để xác định Pods tại thời điểm diễn tập, **tuyệt đối không hard-code Pod names** trong Runbook.

---

### 4.2 Preflight Checklist (Kiểm tra Tiền diễn tập)

Trước khi thực hiện kịch bản demo cho Mentor, người vận hành **bắt buộc** hoàn thành checklist:

- [x] **Cluster Node Health:** Tất cả 5 Worker Nodes đều ở trạng thái `Ready` (`kubectl get nodes`).
- [x] **Revenue Path Workloads Health:** Tất cả 8 Revenue Path Deployments đều có 100% Ready Replicas (`kubectl get deploy -n techx-tf4`).
- [x] **Active User Traffic Load:** Đang chạy Locust Load Test mô phỏng luồng Browse -> Cart -> Checkout:
  ```bash
  locust -f scripts/locustfile.py --headless -u 200 -r 10 --run-time 5m --host http://frontend-proxy:8080
  ```
- [x] **Observability Readiness:** Mở Grafana SLO Dashboard (hoặc truy vấn Prometheus PromQL) để theo dõi real-time:
  - **Success Rate PromQL:** `sum(rate(http_requests_total{status=~"2..|3.."}[5m])) / sum(rate(http_requests_total[5m])) * 100` (SLO Target >= 99.5%)
  - **Latency p95 PromQL:** `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))`
- [x] **Xác định AZ Mục tiêu Diễn tập:** Thao tác trên AZ **`us-east-1a`**.

---

### 4.3 Các bước Thực thi Demo (Dynamic Execution Steps)

#### Bước 1: Khóa Scheduling vào AZ mục tiêu (`us-east-1a`)
Thực hiện cordon tất cả các Worker Nodes có label `topology.kubernetes.io/zone=us-east-1a`:

```bash
# Lấy danh sách Node thuộc AZ us-east-1a và cordon động
TARGET_AZ="us-east-1a"
AZ_NODES=$(kubectl get nodes -l topology.kubernetes.io/zone=$TARGET_AZ -o jsonpath='{.items[*].metadata.name}')
kubectl cordon $AZ_NODES
```

#### Bước 2: Truy vấn & Evict Động các Pods trên AZ mục tiêu
Lấy danh sách Pods Revenue Path đang chạy trên các Node thuộc `us-east-1a` tại thời điểm demo và thực hiện xóa/evict động:

```bash
# Lấy danh sách Pods động trên AZ_NODES và evict
for node in $AZ_NODES; do
  kubectl get pods -n techx-tf4 --field-selector spec.nodeName=$node \
    -l "app.kubernetes.io/component in (frontend-proxy,frontend,cart,checkout,payment,shipping,product-catalog,currency)" \
    -o name | xargs -r kubectl delete -n techx-tf4
done
```

#### Bước 3: Kiểm chứng Khả năng Phục hồi (Failover & SLO Verification)
1. Quan sát Kubernetes Scheduler tự động reschedule các Pods sang AZ còn lại (`us-east-1b`):
   ```bash
   kubectl get pods -n techx-tf4 -o wide
   ```
2. Kiểm tra Active Endpoints trên AZ `us-east-1b`:
   ```bash
   kubectl get endpoints -n techx-tf4 frontend-proxy frontend cart checkout payment shipping product-catalog currency
   ```
3. Kiểm tra Prometheus / Grafana SLO Metrics: **Success Rate giữ >= 99.5%**, không có gián đoạn dịch vụ.

---

### 4.4 Emergency Rollback Protocol (Quy trình Khôi phục An toàn)

#### Lệnh 1: Mở lại Scheduling cho Nodes ở AZ `us-east-1a` (Uncordon)
```bash
kubectl uncordon $AZ_NODES
```

#### Lệnh 2: Kích hoạt Rebalance Rollout cho Revenue Path Services
```bash
kubectl rollout restart deployment cart checkout currency frontend frontend-proxy payment product-catalog shipping -n techx-tf4
```

---

## 5. Command `kubectl` để Mentor Tự Verify (Verification Commands)

```bash
# 1. Kiểm tra node label topology.kubernetes.io/zone
kubectl get nodes -L topology.kubernetes.io/zone

# 2. Kiểm tra chi tiết Placement (Service -> Pod -> Node) cho 8 Revenue Path Services
kubectl get pods -n techx-tf4 \
  -l "app.kubernetes.io/component in (frontend-proxy,frontend,cart,checkout,payment,shipping,product-catalog,currency)" \
  -o custom-columns="SERVICE:.metadata.labels.app\.kubernetes\.io/component,POD:.metadata.name,NODE:.spec.nodeName,STATUS:.status.phase"

# 3. Kiểm tra Replicas, HPA và PodDisruptionBudget (PDB)
kubectl get deploy,hpa,pdb -n techx-tf4
```
