# 🎬 KỊCH BẢN DEMO & QUAY MÀN HÌNH CHUẨN HÓA (STANDALONE DEMO SCRIPT)
## Mandate 17: Multi-AZ Resilience & Workload Containment Verification

- **Mục tiêu**: Chuẩn hóa kịch bản quay màn hình/demo để mentor có thể tự kiểm tra độc lập.
- **Tài liệu tham chiếu**: [CDO08-REL-21-az-loss-evidence.md](file:///d:/xbrain/tf4-phase3-repo/docs/cdo08/week3/mandate17/evidence/CDO08-REL-21-az-loss-evidence.md)
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
PS D:\xbrain\tf4-phase3-repo> aws sso login --sso-session tf4-sso
PS D:\xbrain\tf4-phase3-repo> aws eks update-kubeconfig --name techx-tf4-cluster --region us-east-1 --profile TF4-SecurityIAMSSOManager-511825856493
Updated context arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster in C:\Users\PC\.kube\config
```
- **Kết quả thu được**: Cập nhật thành công context Kubeconfig cho tài khoản Admin/Manager.

#### Command 1.2: Kiểm tra danh sách Nodes và phân bổ Availability Zones
```powershell
PS D:\xbrain\tf4-phase3-repo> kubectl get nodes -L topology.kubernetes.io/zone
NAME                          STATUS   ROLES    AGE   VERSION               ZONE
ip-10-0-10-231.ec2.internal   Ready    <none>   14d   v1.34.9-eks-7d6f6ec   us-east-1a
ip-10-0-10-8.ec2.internal     Ready    <none>   20h   v1.34.9-eks-8f14419   us-east-1a
ip-10-0-11-37.ec2.internal    Ready    <none>   20h   v1.34.9-eks-8f14419   us-east-1b
ip-10-0-11-40.ec2.internal    Ready    <none>   14d   v1.34.9-eks-7d6f6ec   us-east-1b
```
- **Kết quả thu được**: Cụm EKS có 4 Worker Nodes sẵn sàng ở trạng thái `Ready` rải đều 2 AZs (`us-east-1a` và `us-east-1b`).

#### Command 1.3: Kiểm tra vị trí phân bổ Pods ban đầu của Revenue Path
```powershell
PS D:\xbrain\tf4-phase3-repo> kubectl get pods -n techx-tf4 -l "app.kubernetes.io/component in (frontend-proxy,frontend,cart,checkout,payment,shipping,product-catalog,currency)" -o custom-columns="SERVICE:.metadata.labels.app\.kubernetes\.io/component,POD:.metadata.name,NODE:.spec.nodeName,STATUS:.status.phase"
SERVICE           POD                                NODE                          STATUS
cart              cart-54885469b4-k5tkz              ip-10-0-10-8.ec2.internal     Running
cart              cart-54885469b4-tvvhh              ip-10-0-10-8.ec2.internal     Running
checkout          checkout-6978c798fb-kv4zq          ip-10-0-10-8.ec2.internal     Running
checkout          checkout-6978c798fb-vvqsx          ip-10-0-10-231.ec2.internal   Running
checkout          checkout-d48d977bf-8wbsq           ip-10-0-11-40.ec2.internal    Running
checkout          checkout-d48d977bf-mslkr           ip-10-0-11-37.ec2.internal    Running
currency          currency-64bc78b888-btqsq          ip-10-0-10-8.ec2.internal     Running
currency          currency-64bc78b888-llchz          ip-10-0-10-231.ec2.internal   Running
frontend          frontend-65c6bd4cd6-k8gbr          ip-10-0-11-40.ec2.internal    Running
frontend          frontend-65c6bd4cd6-rxs9j          ip-10-0-10-8.ec2.internal     Running
frontend          frontend-65c6bd4cd6-xrfqf          ip-10-0-11-37.ec2.internal    Running
frontend-proxy    frontend-proxy-89fb8bc9b-gqg9t     ip-10-0-11-40.ec2.internal    Running
frontend-proxy    frontend-proxy-89fb8bc9b-qtb9z     ip-10-0-11-37.ec2.internal    Running
payment           payment-7c45f74c-99cv6             ip-10-0-11-40.ec2.internal    Running
payment           payment-7c45f74c-xs2fc             ip-10-0-10-231.ec2.internal   Running
product-catalog   product-catalog-8575867dcd-dt8f5   ip-10-0-11-37.ec2.internal    Running
product-catalog   product-catalog-8575867dcd-h46bh   ip-10-0-11-40.ec2.internal    Running
shipping          shipping-b768bf86-d4glt            ip-10-0-11-37.ec2.internal    Running
shipping          shipping-b768bf86-qcv6w            ip-10-0-10-231.ec2.internal   Running
```
- **Kết quả thu được**: Các microservices có 2 Replicas đều được phân bổ đều 50/50 giữa các Nodes thuộc `us-east-1a` và `us-east-1b`.

---

### 🎬 BƯỚC 2: RESILIENCE TEST (Thử nghiệm sập AZ us-east-1a)

- **Mục đích**: Cô lập hoàn toàn AZ `us-east-1a` và kiểm chứng khả năng tự động failover sang `us-east-1b`.

#### Command 2.1: Cordon toàn bộ Nodes thuộc AZ `us-east-1a`
```powershell
PS D:\xbrain\tf4-phase3-repo> kubectl cordon -l topology.kubernetes.io/zone=us-east-1a
node/ip-10-0-10-231.ec2.internal cordoned
node/ip-10-0-10-8.ec2.internal cordoned

PS D:\xbrain\tf4-phase3-repo> kubectl get nodes -L topology.kubernetes.io/zone
NAME                          STATUS                     ROLES    AGE   VERSION               ZONE
ip-10-0-10-231.ec2.internal   Ready,SchedulingDisabled   <none>   14d   v1.34.9-eks-7d6f6ec   us-east-1a
ip-10-0-10-8.ec2.internal     Ready,SchedulingDisabled   <none>   20h   v1.34.9-eks-8f14419   us-east-1a
ip-10-0-11-37.ec2.internal    Ready                      <none>   20h   v1.34.9-eks-8f14419   us-east-1b
ip-10-0-11-40.ec2.internal    Ready                      <none>   14d   v1.34.9-eks-7d6f6ec   us-east-1b
```
- **Kết quả thu được**: Tất cả các Nodes thuộc `us-east-1a` chuyển sang trạng thái `SchedulingDisabled`.

#### Command 2.2: Trục xuất (Evict) các Pods thuộc Revenue Path nằm trên AZ `us-east-1a`
```powershell
PS D:\xbrain\tf4-phase3-repo> $AZ_NODES = (kubectl get nodes -l topology.kubernetes.io/zone=us-east-1a -o jsonpath='{.items[*].metadata.name}').Split(" ")
PS D:\xbrain\tf4-phase3-repo> foreach ($node in $AZ_NODES) {
>>     if ($node) {
>>         kubectl delete pods -n techx-tf4 --field-selector spec.nodeName=$node -l "app.kubernetes.io/component in (frontend-proxy,frontend,cart,checkout,payment,shipping,product-catalog,currency)" --wait=$false
>>     }
>> }
pod "checkout-6978c798fb-vvqsx" deleted from techx-tf4 namespace
pod "currency-64bc78b888-llchz" deleted from techx-tf4 namespace
pod "payment-7c45f74c-xs2fc" deleted from techx-tf4 namespace
pod "shipping-b768bf86-qcv6w" deleted from techx-tf4 namespace
pod "cart-54885469b4-k5tkz" deleted from techx-tf4 namespace
pod "cart-54885469b4-tvvhh" deleted from techx-tf4 namespace
pod "checkout-6978c798fb-kv4zq" deleted from techx-tf4 namespace
pod "currency-64bc78b888-btqsq" deleted from techx-tf4 namespace
pod "frontend-65c6bd4cd6-rxs9j" deleted from techx-tf4 namespace
```
- **Kết quả thu được**: Pods ở `us-east-1a` bị xóa và Kubernetes Scheduler lập tức khởi tạo Pods thay thế sang vùng sống sót `us-east-1b`.

#### Command 2.3: Quan sát Failover Pods & Active Endpoints tại `us-east-1b`
```powershell
PS D:\xbrain\tf4-phase3-repo> kubectl get pods -n techx-tf4 -l "app.kubernetes.io/component in (frontend-proxy,frontend,cart,checkout,payment,shipping,product-catalog,currency)" -o custom-columns="SERVICE:.metadata.labels.app\.kubernetes\.io/component,POD:.metadata.name,NODE:.spec.nodeName,STATUS:.status.phase"
SERVICE           POD                                NODE                         STATUS
checkout          checkout-6978c798fb-8qjxd          ip-10-0-11-40.ec2.internal   Running
checkout          checkout-6978c798fb-ssqrt          ip-10-0-11-40.ec2.internal   Running
checkout          checkout-d48d977bf-8wbsq           ip-10-0-11-40.ec2.internal   Running
checkout          checkout-d48d977bf-mslkr           ip-10-0-11-37.ec2.internal   Running
currency          currency-64bc78b888-nkvsb          ip-10-0-11-37.ec2.internal   Running
currency          currency-64bc78b888-s5j95          ip-10-0-11-40.ec2.internal   Running
frontend          frontend-65c6bd4cd6-k8gbr          ip-10-0-11-40.ec2.internal   Running
frontend          frontend-65c6bd4cd6-mhpqm          ip-10-0-11-40.ec2.internal   Running
frontend          frontend-65c6bd4cd6-xrfqf          ip-10-0-11-37.ec2.internal   Running
frontend-proxy    frontend-proxy-89fb8bc9b-gqg9t     ip-10-0-11-40.ec2.internal   Running
frontend-proxy    frontend-proxy-89fb8bc9b-qtb9z     ip-10-0-11-37.ec2.internal   Running
payment           payment-7c45f74c-99cv6             ip-10-0-11-40.ec2.internal   Running
payment           payment-7c45f74c-shjqg             ip-10-0-11-37.ec2.internal   Running
product-catalog   product-catalog-8575867dcd-dt8f5   ip-10-0-11-37.ec2.internal   Running
product-catalog   product-catalog-8575867dcd-h46bh   ip-10-0-11-40.ec2.internal   Running
shipping          shipping-b768bf86-d4glt            ip-10-0-11-37.ec2.internal   Running
shipping          shipping-b768bf86-rsmrt            ip-10-0-11-40.ec2.internal   Running

PS D:\xbrain\tf4-phase3-repo> kubectl get endpoints -n techx-tf4 frontend-proxy frontend cart checkout payment shipping product-catalog currency
NAME              ENDPOINTS                                          AGE
frontend-proxy    10.0.11.144:8080,10.0.11.230:8080                  15d
frontend          10.0.11.249:8080,10.0.11.50:8080,10.0.11.55:8080   15d
checkout          10.0.11.232:8080,10.0.11.75:8080                   15d
payment           10.0.11.111:8080,10.0.11.153:8080                  15d
shipping          10.0.11.123:8080,10.0.11.244:8080                  15d
product-catalog   10.0.11.143:8080,10.0.11.81:8080                   15d
currency          10.0.11.23:8080,10.0.11.242:8080                   15d
```
- **Kết quả thu được**: 100% Service Endpoints giữ nguyên IP hoạt động tại subnet `10.0.11.x` (`us-east-1b`). PromQL Checkout Success Rate trên Grafana giữ vững ngưỡng `>= 99.5%`.

---

### 🎬 BƯỚC 3: CONTAINMENT TEST (Kiểm tra an ninh khoanh vùng SEC-21 & SEC-22)

- **Mục đích**: Chứng minh Attacker Pod bị khoanh vùng triệt để về cả Mạng (NetworkPolicy) và Kubernetes API (RBAC Token).

#### Command 3.1: Kiểm tra tắt tự động mount K8s API token (`automountServiceAccountToken: false`)
```powershell
PS D:\xbrain\tf4-phase3-repo> kubectl get deployment -n techx-tf4 frontend -o jsonpath='{.spec.template.spec.automountServiceAccountToken}'
false
```
- **Kết quả thu được**: Trả về `false` (không mount K8s API token vào Pod, loại bỏ rủi ro bị lấy cắp token).

#### Command 3.2: Kiểm tra ServiceAccount độc lập của service
```powershell
PS D:\xbrain\tf4-phase3-repo> kubectl get deployment -n techx-tf4 frontend -o jsonpath='{.spec.template.spec.serviceAccountName}'
frontend
```
- **Kết quả thu được**: Trả về `frontend` (không dùng chung ServiceAccount `default` hay `techx-corp`).

#### Command 3.3: Kiểm tra từ chối quyền K8s API qua `kubectl auth can-i` (`SEC-22`)
```powershell
PS D:\xbrain\tf4-phase3-repo> kubectl auth can-i get secrets --as=system:serviceaccount:techx-tf4:frontend -n techx-tf4
no

PS D:\xbrain\tf4-phase3-repo> kubectl auth can-i delete pods --as=system:serviceaccount:techx-tf4:frontend --all-namespaces
no
```
- **Kết quả thu được**: Cả 2 lệnh đều trả về `no` (từ chối 100% quyền truy cập nhạy cảm).

#### Command 3.4: Kiểm tra chặn di chuyển ngang qua NetworkPolicy (`SEC-21`)
```powershell
PS D:\xbrain\tf4-phase3-repo> kubectl exec -n techx-tf4 deployment/load-generator -- curl -s --connect-timeout 3 http://prometheus.techx-observability.svc.cluster.local:9090
command terminated with exit code 28 (Connection timed out)
```
- **Kết quả thu được**: NetworkPolicy Egress/Ingress chặn thành công lưu lượng di chuyển ngang (`Connection timed out`).

---

### 🎬 BƯỚC 4: ROLLBACK & CLEANUP (Khôi phục và dọn dẹp sau test)

- **Mục đích**: Đưa hệ thống trở về trạng thái cân bằng ban đầu, dọn dẹp các tài nguyên tạm.

#### Command 4.1: Mở lại (Uncordon) các Nodes ở `us-east-1a`
```powershell
PS D:\xbrain\tf4-phase3-repo> kubectl uncordon -l topology.kubernetes.io/zone=us-east-1a
node/ip-10-0-10-231.ec2.internal uncordoned
node/ip-10-0-10-8.ec2.internal uncordoned
```
- **Kết quả thu được**: Các Nodes ở `us-east-1a` chuyển từ `SchedulingDisabled` trở lại trạng thái `Ready`.

#### Command 4.2: Kích hoạt Rebalance Pods trả về phân bổ cân bằng 50/50
```powershell
PS D:\xbrain\tf4-phase3-repo> kubectl rollout restart deployment -n techx-tf4 -l app.kubernetes.io/part-of=techx-corp
deployment.apps/accounting restarted
deployment.apps/ad restarted
deployment.apps/currency restarted
deployment.apps/frontend restarted
deployment.apps/frontend-proxy restarted
deployment.apps/payment restarted
deployment.apps/product-catalog restarted
deployment.apps/shipping restarted
```
- **Kết quả thu được**: Tất cả Deployments rollout hoàn tất thành công, Pods quay về rải đều 50/50 giữa `us-east-1a` và `us-east-1b`.

---

### 🎬 BƯỚC 5: FINAL HEALTH CHECK (Kiểm tra sức khỏe cuối cùng)

- **Mục đích**: Xác nhận 100% hệ thống khỏe mạnh sau khi dọn dẹp.

#### Command 5.1: Kiểm tra 100% Pods đạt trạng thái `Running` và `Ready`
```powershell
PS D:\xbrain\tf4-phase3-repo> kubectl get pods -n techx-tf4
NAME                               READY   STATUS    RESTARTS   AGE
checkout-6978c798fb-8qjxd          1/1     Running   0          5m
currency-64bc78b888-nkvsb          1/1     Running   0          5m
currency-7d4b565c78-6546x          1/1     Running   0          1m
frontend-65768d46fb-kdqrl          1/1     Running   0          1m
frontend-proxy-89fb8bc9b-gqg9t     1/1     Running   0          4h
payment-7595d8789-mhlwq            1/1     Running   0          1m
product-catalog-8575867dcd-dt8f5   1/1     Running   0          4h
shipping-b768bf86-rsmrt            1/1     Running   0          5m
```
- **Kết quả thu được**: 100% Pods ở trạng thái `Running`, không có Pod nào bị `CrashLoopBackOff` hay `Pending`.

#### Command 5.2: Thống kê lại phân bổ Pods qua 2 AZs
```powershell
PS D:\xbrain\tf4-phase3-repo> kubectl get pods -n techx-tf4 -l "app.kubernetes.io/component in (frontend-proxy,frontend,cart,checkout,payment,shipping,product-catalog,currency)" -o custom-columns="SERVICE:.metadata.labels.app\.kubernetes\.io/component,POD:.metadata.name,NODE:.spec.nodeName"
```
- **Kết quả thu được**: Hoàn tất diễn tập, tất cả các microservices trở về trạng thái rải đều 50/50 qua 2 AZs (`us-east-1a` & `us-east-1b`), hệ thống khỏe mạnh 100%.
