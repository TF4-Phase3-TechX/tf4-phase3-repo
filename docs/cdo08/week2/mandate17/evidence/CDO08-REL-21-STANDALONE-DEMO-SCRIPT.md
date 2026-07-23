# 🎬 KỊCH BẢN DEMO & QUAY MÀN HÌNH CHUẨN HÓA (STANDALONE DEMO SCRIPT)
## Mandate 17: Multi-AZ Resilience & Workload Containment Verification

- **Mục tiêu**: Chuẩn hóa kịch bản quay màn hình/demo để mentor có thể tự kiểm tra độc lập.
- **Tài liệu tham chiếu**: [CDO08-REL-21-az-loss-evidence.md](file:///d:/xbrain/tf4-phase3-repo/docs/cdo08/week2/mandate17/evidence/CDO08-REL-21-az-loss-evidence.md)
- **Tài khoản AWS & Cluster**: Account `511825856493` (`us-east-1`), EKS Cluster `techx-tf4-cluster`, Namespace `techx-tf4`
- **Target Microservices**: 8 Revenue Path Services (`frontend-proxy`, `frontend`, `cart`, `checkout`, `payment`, `shipping`, `product-catalog`, `currency`)

---

## 📋 CẦN LÀM (DEMO SPECIFICATION)

1. **Thứ tự thực hiện 5 bước**:
   - `Preflight`: Kiểm tra trạng thái Nodes, Pod placement ban đầu, và phân quyền SA/RBAC.
   - `Resilience Test`: Diễn tập sập AZ `us-east-1a`, evict Pods, kiểm chứng Karpenter auto-scaling và active endpoints tại `us-east-1b`.
   - `Containment Test`: Kiểm tra an ninh khoanh vùng SEC-22 (`automountServiceAccountToken: false` và ServiceAccount độc lập).
   - `Rollback`: Mở lại AZ `us-east-1a`, kích hoạt rollout restart trả Pods về phân bổ 50/50, tự động cleanup.
   - `Final Health`: Kiểm tra 100% dịch vụ đạt trạng thái `Healthy` và `Ready`.

2. **Command & Expected Result**: Ghi chi tiết câu lệnh PowerShell/CLI chính xác cùng kết quả mong đợi tương ứng.
3. **Dashboard & PromQL**: Xác định cụ thể Grafana Dashboard và các câu lệnh PromQL cần mở trên màn hình.
4. **Hard-Stop Conditions**: Quy định rõ ràng các điều kiện dừng khẩn cấp để đảm bảo an toàn hệ thống.

---

## 📄 OUTPUT & ACCEPTANCE CRITERIA

- **Output**: File kịch bản Demo độc lập phục vụ đưa vào `evidence final` cho Mentor nghiệm thu độc lập.
- **Acceptance Criteria**:
  - ✅ **Tự vận hành**: Người khác (Mentor/Reviewer) có thể mở terminal gõ chạy theo từng lệnh mà không cần hỏi lại PM hay Developer.
  - ✅ **An toàn tuyệt đối**: Không dùng bất kỳ thao tác nào phá dữ liệu (không xóa S3, RDS, Secrets, KMS).
  - ✅ **Cleanup tự động**: Có quy trình dọn dẹp và trả trạng thái cụm EKS về ban đầu sau khi kết thúc thử nghiệm.

---

## ⚠️ HARD-STOP CONDITIONS (ĐIỀU KIỆN DỪNG THỬ NGHIỆM KHẨN CẤP)

> [!CAUTION]
> **DỪNG NGAY LẬP TỨC THỬ NGHIỆM VÀ KÍCH HOẠT LỆNH EMERGENCY ROLLBACK NẾU GẶP 1 TRONG CÁC TRƯỜNG HỢP SAU:**  
> 1. Success Rate luồng Checkout rớt xuống `< 50%` kéo dài quá `60 giây` mà không có dấu hiệu hồi phục.  
> 2. Karpenter báo lỗi `NodeClaimFailed` kéo dài quá `3 phút` không thể bật Node mới ở `us-east-1b`.  
> 3. Tuyệt đối **KHÔNG** chạy các lệnh phá hủy dữ liệu như `aws s3 rm`, `aws rds delete-db-instance`, `aws secretsmanager delete-secret`.
> 
> **Lệnh khôi phục khẩn cấp (Emergency Circuit Breaker):**  
> ```powershell
> kubectl uncordon -l topology.kubernetes.io/zone=us-east-1a
> kubectl rollout restart deployment -n techx-tf4 -l app.kubernetes.io/part-of=techx-corp
> ```

---

## 🖥️ DASHBOARD & PROMPQL CẦN MỞ TRƯỚC KHI DEMO

1. **Dashboard Grafana**: Mở dashboard `business-flow-health-overview` hoặc `checkout-revenue-dashboard` tại 🌐 **`http://localhost:3000`**.
2. **PromQL 1 — Checkout Success Rate (%)**:
   ```promql
   sum(rate(traces_span_metrics_calls_total{service_name="frontend",span_kind="SPAN_KIND_SERVER",span_name="POST /api/checkout",status_code!="STATUS_CODE_ERROR"}[15m])) / sum(rate(traces_span_metrics_calls_total{service_name="frontend",span_kind="SPAN_KIND_SERVER",span_name="POST /api/checkout"}[15m])) * 100
   ```
3. **PromQL 2 — Checkout Latency p95 (ms)**:
   ```promql
   histogram_quantile(0.95, sum(rate(traces_span_metrics_latency_bucket{service_name="frontend",span_name="POST /api/checkout"}[15m])) by (le))
   ```

---

## 🎬 KỊCH BẢN CHI TIẾT 5 BƯỚC DEMO (STEP-BY-STEP EXECUTION SCRIPT)

### 🎬 BƯỚC 1: PREFLIGHT CHECK (Kiểm tra trạng thái ban đầu)

- **Mục đích**: Xác nhận cụm EKS và các Pods đang ở trạng thái cân bằng Multi-AZ 50/50 trước khi diễn tập.

#### Command 1.1: Đăng nhập AWS SSO & Cập nhật Kubeconfig
```powershell
aws sso login --sso-session tf4-sso
aws eks update-kubeconfig --name techx-tf4-cluster --region us-east-1 --profile TF4-SecurityIAMSSOManager-511825856493
```
- **Expected Result**: Thông báo `Updated context arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster in C:\Users\...`.

#### Command 1.2: Kiểm tra danh sách Nodes và phân bổ Availability Zones
```powershell
kubectl get nodes -L topology.kubernetes.io/zone
```
- **Expected Result**: Xuất hiện tối thiểu các Nodes nằm trên cả 2 zones `us-east-1a` và `us-east-1b` ở trạng thái `Ready`.

#### Command 1.3: Kiểm tra vị trí phân bổ Pods ban đầu của Revenue Path
```powershell
kubectl get pods -n techx-tf4 -l "app.kubernetes.io/component in (frontend-proxy,frontend,cart,checkout,payment,shipping,product-catalog,currency)" -o custom-columns="SERVICE:.metadata.labels.app\.kubernetes\.io/component,POD:.metadata.name,NODE:.spec.nodeName,STATUS:.status.phase"
```
- **Expected Result**: Các dịch vụ có 2 Replicas (`cart`, `checkout`, `frontend`, `payment`...) đều được rải đều 50/50 giữa các Nodes thuộc `us-east-1a` và `us-east-1b`.

---

### 🎬 BƯỚC 2: RESILIENCE TEST (Thử nghiệm sập AZ us-east-1a)

- **Mục đích**: Cô lập hoàn toàn AZ `us-east-1a` và kiểm chứng khả năng tự động failover sang `us-east-1b`.

#### Command 2.1: Cordon toàn bộ Nodes thuộc AZ `us-east-1a`
```powershell
kubectl cordon -l topology.kubernetes.io/zone=us-east-1a
```
- **Expected Result**: Tất cả các Nodes thuộc `us-east-1a` chuyển sang trạng thái `SchedulingDisabled`.

#### Command 2.2: Trục xuất (Evict) các Pods thuộc Revenue Path nằm trên AZ `us-east-1a`
```powershell
$AZ_NODES = (kubectl get nodes -l topology.kubernetes.io/zone=us-east-1a -o jsonpath='{.items[*].metadata.name}').Split(" ")
foreach ($node in $AZ_NODES) {
    if ($node) {
        kubectl delete pods -n techx-tf4 --field-selector spec.nodeName=$node -l "app.kubernetes.io/component in (frontend-proxy,frontend,cart,checkout,payment,shipping,product-catalog,currency)" --wait=$false
    }
}
```
- **Expected Result**: Pods ở `us-east-1a` bị xóa và Kubernetes Scheduler lập tức khởi tạo Pods thay thế sang vùng sống sót `us-east-1b`.

#### Command 2.3: Quan sát Karpenter Auto-scaling & Verify Runtime Endpoints
```powershell
kubectl get pods -n techx-tf4 -o wide
kubectl get endpoints -n techx-tf4 frontend-proxy frontend cart checkout payment shipping product-catalog currency
```
- **Expected Result**:
  - 100% Service Endpoints giữ nguyên IP hoạt động tại subnet `10.0.11.x` (`us-east-1b`).
  - Karpenter tự động khởi tạo EC2 Node mới ở `us-east-1b` (`ip-10-0-11-126`) để gánh tải.
  - PromQL Checkout Success Rate trên Grafana hồi phục giữ vững ngưỡng `>= 99.5%`.

---

### 🎬 BƯỚC 3: CONTAINMENT TEST (Kiểm tra an ninh khoanh vùng SEC-21 & SEC-22)

- **Mục đích**: Chứng minh Attacker Pod bị khoanh vùng triệt để về cả Mạng (NetworkPolicy) và Kubernetes API (RBAC Token).

#### Command 3.1: Kiểm tra tắt tự động mount K8s API token (`automountServiceAccountToken: false`)
```powershell
kubectl get deployment -n techx-tf4 checkout -o jsonpath='{.spec.template.spec.automountServiceAccountToken}'
```
- **Expected Result**: Trả về `false` (không mount K8s API token vào Pod, loại bỏ rủi ro bị lấy cắp token).

#### Command 3.2: Kiểm tra ServiceAccount độc lập của service
```powershell
kubectl get deployment -n techx-tf4 checkout -o jsonpath='{.spec.template.spec.serviceAccountName}'
```
- **Expected Result**: Trả về `checkout` (không dùng chung ServiceAccount `default` hay `techx-corp`).

#### Command 3.3: Kiểm tra từ chối quyền K8s API qua `kubectl auth can-i` (`SEC-22`)
```powershell
kubectl auth can-i get secrets --as=system:serviceaccount:techx-tf4:checkout -n techx-tf4
kubectl auth can-i delete pods --as=system:serviceaccount:techx-tf4:checkout --all-namespaces
```
- **Expected Result**: Cả 2 lệnh đều trả về `no` (từ chối 100% quyền truy cập nhạy cảm).

#### Command 3.4: Kiểm tra chặn di chuyển ngang qua NetworkPolicy (`SEC-21`)
```powershell
kubectl exec -n techx-tf4 deployment/checkout -- curl -s --connect-timeout 3 http://prometheus.techx-observability.svc.cluster.local:9090
```
- **Expected Result**: Trả về `Connection timed out` (NetworkPolicy Egress/Ingress chặn thành công lưu lượng di chuyển ngang).

---

### 🎬 BƯỚC 4: ROLLBACK & CLEANUP (Khôi phục và dọn dẹp sau test)

- **Mục đích**: Đưa hệ thống trở về trạng thái cân bằng ban đầu, dọn dẹp các tài nguyên tạm.

#### Command 4.1: Mở lại (Uncordon) các Nodes ở `us-east-1a`
```powershell
kubectl uncordon -l topology.kubernetes.io/zone=us-east-1a
```
- **Expected Result**: Các Nodes ở `us-east-1a` chuyển từ `SchedulingDisabled` trở lại trạng thái `Ready`.

#### Command 4.2: Kích hoạt Rebalance Pods trả về phân bổ cân bằng 50/50
```powershell
kubectl rollout restart deployment -n techx-tf4 -l app.kubernetes.io/part-of=techx-corp
kubectl rollout status deployment -n techx-tf4 -l app.kubernetes.io/part-of=techx-corp --timeout=120s
```
- **Expected Result**: Tất cả 22 Deployments rollout hoàn tất thành công, Pods quay về rải đều 50/50 giữa `us-east-1a` và `us-east-1b`.

---

### 🎬 BƯỚC 5: FINAL HEALTH CHECK (Kiểm tra sức khỏe cuối cùng)

- **Mục đích**: Xác nhận 100% hệ thống khỏe mạnh sau khi dọn dẹp.

#### Command 5.1: Kiểm tra 100% Pods đạt trạng thái `Running` và `Ready`
```powershell
kubectl get pods -n techx-tf4
```
- **Expected Result**: 100% Pods ở trạng thái `Running`, không có Pod nào bị `CrashLoopBackOff` hay `Pending`.

#### Command 5.2: Thống kê lại phân bổ Pods qua 2 AZs
```powershell
kubectl get pods -n techx-tf4 -l "app.kubernetes.io/component in (frontend-proxy,frontend,cart,checkout,payment,shipping,product-catalog,currency)" -o custom-columns="SERVICE:.metadata.labels.app\.kubernetes\.io/component,POD:.metadata.name,NODE:.spec.nodeName"
```
- **Expected Result**: Hoàn tất diễn tập, tất cả các microservices trở về trạng thái rải đều qua 2 AZs, hệ thống khỏe mạnh 100%.
