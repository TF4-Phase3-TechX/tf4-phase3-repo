# Nhóm TF4-CDO08-SecurityReliability

Nhóm này chịu trách nhiệm giám sát bảo mật hạ tầng và đảm bảo tính tin cậy, tính liên tục của hệ thống (SRE - Site Reliability Engineering) trong dự án TF4.

## 📋 Danh sách Permission Sets (Policies)

Nhóm này được gán các quyền hạn sau đây qua AWS IAM Identity Center:

1. **[TF4-BaseReadOnly](../../TF4-BaseReadOnly.md)**
   * **Mô tả**: Quyền chỉ đọc cơ bản đối với các hạ tầng lõi của AWS (EKS, EC2, CloudWatch, ECR, v.v.).
   * **Mục đích**: Cung cấp khả năng hiển thị cơ bản trạng thái hệ thống.

2. **[TF4-SecReliabilityReadOnlyAudit](TF4-SecReliabilityReadOnlyAudit.md)**
   * **Mô tả**: Quyền đọc cấu hình hạ tầng mở rộng (EC2, EKS, ELB, AutoScaling, ECR) kết hợp quyền kiểm tra cấu hình các công cụ bảo mật hàng đầu (Security Hub, GuardDuty, WAFv2, Secrets Manager, KMS, ACM). Đồng thời đã tích hợp thêm quyền quản trị toàn phần đối với IAM, AWS SSO (Identity Center), Identity Store, và quản lý EKS Access Entries được gom từ `TF4-SecurityIAMSSOManager`.
   * **Mục đích**: Giám sát lỗ hổng bảo mật, theo dõi các cảnh báo đe dọa trực tuyến, quản trị định danh/phân quyền người dùng và quản lý quyền truy cập Kubernetes Cluster.

---
[⬅️ Quay lại trang chủ IAM Docs](../../README.md)
