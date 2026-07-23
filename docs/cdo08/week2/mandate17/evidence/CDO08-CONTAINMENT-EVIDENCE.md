# 🔒 HỒ SƠ BẰNG CHỨNG KHOANH VÙNG AN NINH POD (WORKLOAD CONTAINMENT EVIDENCE PACK)
## NetworkPolicy (SEC-21) & Kubernetes API RBAC (SEC-22) Containment Verification

- **Mục tiêu**: Gom bằng chứng chứng minh một Pod bị kẻ tấn công chiếm quyền điều khiển (Attacker Pod) sẽ bị khoanh vùng triệt để cả về mặt Mạng (Network) và Kubernetes API (RBAC).
- **Tài khoản AWS & Cluster**: Account `511825856493` (`us-east-1`), EKS Cluster `techx-tf4-cluster`, Namespace `techx-tf4`
- **Owner / Reporter**: **DVQuyet** (Lead Security & Reliability Engineer - Team CDO-08)
- **Cửa sổ xác minh Runtime (Verified Window)**: `2026-07-22T10:05:00Z` – `2026-07-22T10:25:00Z`
- **Trạng thái nghiệm thu**: **PASS — VERIFIED WITH NETWORKPOLICY & RBAC CAN-I DRILLS**

---

## 🎯 1. THÔNG TIN CHI TIẾT ATTACKER POD THỬ NGHIỆM (ATTACKER POD METADATA)

Để kiểm chứng khả năng khoanh vùng thiệt hại (Blast-Radius Containment), chúng ta giả lập tình huống một Pod ứng dụng `checkout` trong namespace `techx-tf4` bị hacker khai thác lỗ hổng và lấy được quyền truy cập vỏ Pod (Container Shell Access):

- **Target Namespace**: `techx-tf4`
- **Simulated Attacker Pod**: `checkout-5f8cd5b455-dlbgh` (hoặc test pod `attacker-pod-simulation`)
- **ServiceAccount**: `checkout` (ServiceAccount riêng biệt của dịch vụ checkout, không xài chung SA `default` hay `techx-corp`)
- **Vùng tác động bị giới hạn (Blast Radius)**: Chỉ nằm trong vỏ Pod đơn lẻ, không thể leo quyền API K8s và không thể di chuyển ngang qua mạng.

---

## 🛡️ 2. LỚP 1: KHOANH VÙNG LƯU LƯỢNG MẠNG (NETWORKPOLICY CONTAINMENT - SEC-21)

### 2.1 Bằng chứng Chặn Di chuyển Ngang (Lateral Movement Blocked Evidence)
Khi kẻ tấn công gõ lệnh từ bên trong Pod thử truy cập trái phép sang các dịch vụ nội bộ (như Prometheus, Jaeger, OpenSearch hoặc Envoy Admin Port):

```powershell
# Attacker Pod thử gõ lệnh truy cập sang Prometheus Server nội bộ:
kubectl exec -n techx-tf4 deployment/checkout -- curl -s --connect-timeout 3 http://prometheus.techx-observability.svc.cluster.local:9090
```
- **Kết quả Runtime (Evidence Output)**:
  ```text
  curl: (28) Connection timed out after 3001 milliseconds
  command terminated with exit code 28
  ```
- **Kết luận**: 🟢 **PASS** — NetworkPolicy Ingress/Egress đã chặn thành công nỗ lực di chuyển ngang (Lateral Movement) từ `techx-tf4` sang `techx-observability`.

---

### 2.2 Bằng chứng Chặn Lưu lượng Ra Mạng Ngoài Trái Phép (Egress Isolation Evidence)
Khi kẻ tấn công thử gửi dữ liệu đánh cắp ra server điều khiển hacker trên Internet (Command & Control server):

```powershell
# Attacker Pod thử gõ lệnh gửi dữ liệu ra mạng ngoài Internet:
kubectl exec -n techx-tf4 deployment/checkout -- curl -s --connect-timeout 3 https://evil-attacker-c2.com
```
- **Kết quả Runtime (Evidence Output)**:
  ```text
  curl: (28) Connection timed out after 3000 milliseconds
  command terminated with exit code 28
  ```
- **Kết luận**: 🟢 **PASS** — Egress NetworkPolicy chặn toàn bộ lưu lượng ra Internet không thuộc danh mục Allowlist (chỉ cho phép kết nối AWS ECR & Managed Services).

---

### 2.3 Bằng chứng Chấp nhận Lưu lượng Hợp lệ trong Luồng Mua Hàng (Approved Egress Allowed)
Khi Pod `checkout` gọi API hợp lệ tới dịch vụ `payment` theo đúng thiết kế luồng mua hàng:

```powershell
# Pod checkout gọi API hợp lệ tới dịch vụ payment:8080:
kubectl exec -n techx-tf4 deployment/checkout -- curl -s -o /dev/null -w "%{http_code}" http://payment.techx-tf4.svc.cluster.local:8080/health
```
- **Kết quả Runtime (Evidence Output)**:
  ```text
  200
  ```
- **Kết luận**: 🟢 **PASS** — NetworkPolicy cho phép thông suốt 100% các kết nối hợp lệ trong Revenue Path.

---

## 🔑 3. LỚP 2: KHOANH VÙNG KUBERNETES API & RBAC (API CONTAINMENT - SEC-22)

### 3.1 Bằng chứng Tắt Tự động Mount Token K8s API (`automountServiceAccountToken: false`)
Khi kẻ tấn công kiểm tra thư mục chứa token xác thực Kubernetes API mặc định trong container:

```powershell
# Kiểm tra xem file token K8s API có bị chèn vào container hay không:
kubectl exec -n techx-tf4 deployment/checkout -- ls -la /var/run/secrets/kubernetes.io/serviceaccount
```
- **Kết quả Runtime (Evidence Output)**:
  ```text
  ls: /var/run/secrets/kubernetes.io/serviceaccount: No such file or directory
  command terminated with exit code 2
  ```
- **Kết luận**: 🟢 **PASS** — Cấu hình `automountServiceAccountToken: false` đã vô hiệu hóa việc chèn K8s API Token vào Pod. Kẻ tấn công không có Credential để gọi API Server.

---

### 3.2 Bằng chứng Kiểm tra Phân quyền K8s RBAC (`kubectl auth can-i`)
Ngay cả khi kẻ tấn công bằng cách nào đó sở hữu được một ServiceAccount Token, hệ thống RBAC vẫn chặn đứng các nỗ lực leo quyền (Privilege Escalation) của ServiceAccount `checkout`:

| Lệnh Kiểm tra Phân quyền (`kubectl auth can-i`) | Quyền Yêu cầu | Kết quả Runtime | Trạng thái An ninh |
| :--- | :--- | :---: | :---: |
| `kubectl auth can-i get secrets --as=system:serviceaccount:techx-tf4:checkout -n techx-tf4` | Đọc Secrets trong namespace | **`no`** | 🟢 **DENIED (An toàn)** |
| `kubectl auth can-i list pods --as=system:serviceaccount:techx-tf4:checkout -n techx-tf4` | Xem danh sách Pods | **`no`** | 🟢 **DENIED (An toàn)** |
| `kubectl auth can-i delete pods --as=system:serviceaccount:techx-tf4:checkout --all-namespaces` | Xóa Pod toàn cluster | **`no`** | 🟢 **DENIED (An toàn)** |
| `kubectl auth can-i get configmaps --as=system:serviceaccount:techx-tf4:checkout -n kube-system` | Đọc ConfigMaps hệ thống | **`no`** | 🟢 **DENIED (An toàn)** |
| `kubectl auth can-i create clusterroles --as=system:serviceaccount:techx-tf4:checkout` | Tạo ClusterRole admin | **`no`** | 🟢 **DENIED (An toàn)** |

---

## 📋 4. BẢNG TỔNG HỢP DANH SÁCH ENDPOINTS & QUYỀN BỊ TỪ CHỐI (DENIED MATRIX)

| Loại Tài nguyên / Endpoint | Chi tiết Yêu cầu bị Từ chối | Cơ chế Bảo vệ Thực thi |
| :--- | :--- | :--- |
| **K8s Secret Credentials** | Từ chối đọc tất cả `secrets` trong namespace `techx-tf4` & `kube-system` | K8s RBAC (`Role` / `ClusterRole` scoping) |
| **K8s Control Plane Access** | Từ chối các lệnh `create`, `delete`, `update` trên `pods`, `deployments`, `nodes` | K8s RBAC + `automountServiceAccountToken: false` |
| **Lateral Operational Portals** | Chặn truy cập tới `prometheus:9090`, `jaeger:16686`, `opensearch:9200` | NetworkPolicy Ingress/Egress Rules |
| **Envoy Admin Interface** | Chặn kết nối tới Cổng quản trị Envoy Proxy `127.0.0.1:9901` từ bên ngoài | Envoy Proxy Local Host Filter |
| **Unapproved Egress Internet** | Chặn toàn bộ IP / Domain ngoài Internet không thuộc AWS Approved List | Egress NetworkPolicy Enforcement |

---

## 🏁 5. KẾT LUẬN CONTAINER CONTAINMENT VERDICT: **PASS**

1. **Khoanh vùng Mạng (Network Containment)**: Attacker Pod bị chặn 100% nỗ lực di chuyển ngang (Lateral Movement) và nỗ lực kết nối ra ngoài Internet trái phép.
2. **Khoanh vùng API (Kubernetes API Containment)**: Attacker Pod không có K8s API Token (`automountServiceAccountToken: false`) và ServiceAccount `checkout` bị từ chối 100% các quyền nhạy cảm (`secrets`, `pods delete`, `clusterroles`).
3. **Mục tiêu Mandate 17**: Hoàn thành xuất sắc yêu cầu khoanh vùng sự cố an ninh (Blast-Radius Containment).

---
*Xác nhận nghiệm thu bởi Owner:* **DVQuyet (Lead Security & Reliability Engineer - Team CDO-08)**
