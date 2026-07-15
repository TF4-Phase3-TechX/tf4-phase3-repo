# AUDIT-012 — Justification for SSM & Kubernetes RBAC Hotfix

**Jira/Ticket:** AUDIT-012  
**Date:** 2026-07-14  
**Author:** CDO08 (Security/SSO/IAM Owner)  
**Status:** Approved & Implemented

---

## 1. Bối cảnh Khẩn cấp (Incident Context)

Vào khoảng **14:15 - 14:30 ICT ngày 14/07/2026**, hệ thống phát sinh sự cố liên quan đến luồng thanh toán gRPC call `/oteldemo.PaymentService/Charge`. Người dùng báo lỗi không thanh toán được.
*   Nhóm kiểm toán (CDO07) cần truy xuất bằng chứng (forensic logs, traces, metrics) ngay lập tức để làm rõ nguyên nhân.
*   Tuy nhiên, profile kiểm toán `TF4-AuditReadOnlyAndAnalyze` bị chặn hoàn toàn ở cả 2 tầng:
    1.  **AWS IAM (SSM):** Không có quyền `ssm:StartSession` để kết nối vào Bastion.
    2.  **Kubernetes RBAC:** Không có quyền đọc logs và pods trong namespace `techx-tf4`.

---

## 2. Quyết định Phương án Cấu hình (Implementation Decisions)

Để giải quyết tình huống khẩn cấp (P0 Blocker) mà vẫn đảm bảo tính an toàn bảo mật, CDO08 đã đưa ra quyết định thực thi như sau:

### Quyết định 1: Cấu hình trực tiếp AWS IAM SSO trên Console
*   **Thực thi:** Cập nhật trực tiếp Inline Policy của Permission Set `TF4-AuditReadOnlyAndAnalyze` trong AWS IAM Identity Center và chạy lệnh provisioning ngay lập tức.
*   **Lý do:** 
    *   Quyền SSM và Read-Only là quyền cấp từ tầng AWS Cloud, không cần thay đổi code hay chạy Terraform của hạ tầng.
    *   Đảm bảo CDO07 có thể mở kết nối SSM tunnel ngay mà không bị trễ thời gian điều tra sự cố.

### Quyết định 2: Áp dụng trực tiếp Kubernetes RBAC (kubectl apply) thay vì sửa Helm Chart
*   **Thực thi:** Chạy lệnh `kubectl apply` trực tiếp trên cluster bằng tài khoản Admin để tạo `Role` và `RoleBinding` trong namespace `techx-tf4`.
*   **Lý do:**
    *   **Tốc độ (Speed):** Nếu sửa đổi Helm template và đẩy qua luồng GitOps thông thường (commit, push, code review, CI/CD pipeline), thời gian chờ đợi có thể kéo dài hàng chục phút, làm gián đoạn nghiêm trọng thời gian vàng để điều tra sự cố runtime logs.
    *   **Bảo mật & Không ảnh hưởng (Safety & Zero Impact):** Quyền được cấp hoàn toàn là **Read-Only** (chỉ có `get`, `list`, `watch` đối với pods, configmaps, deployments và quan trọng nhất là `pods/log`). Không có quyền chỉnh sửa, xóa, hay exec (chạy lệnh tùy ý) trên pods. Hoàn toàn không ảnh hưởng đến traffic hay tính ổn định của ứng dụng.
    *   **Khắc phục Drift sau này:** Sau khi sự cố được khắc phục xong và có báo cáo forensic, các cấu hình RBAC này sẽ được đồng bộ chính thức vào file template Helm (`team-rbac.yaml`) để đảm bảo tính bền vững lâu dài.

---

## 3. Lịch sử Thay đổi (Change Log)

### A. AWS IAM Policy (TF4-AuditReadOnlyAndAnalyze)
Đã bổ sung 4 Statements SSM và mở rộng quyền `ExtendedAuditReadOnly` sang EC2 Target Group, EKS Node Group và CloudWatch Metrics.

### B. Kubernetes RBAC (techx-tf4 namespace)
Tạo Role `audit-namespace-readonly` và map vào group `audit-readonly-analyzers` (nhóm được gán trực tiếp cho vai trò kiểm toán từ EKS Access Entry).

---
[⬅️ Quay lại trang chủ IAM Docs](../README.md)
