# Người dùng: nguyen

Tài khoản của người dùng **nguyen** chịu trách nhiệm quản trị bảo mật hệ thống, cấu hình danh tính (SSO), quản lý chính sách phân quyền (IAM) và giám sát hạ tầng dự án TF4.

## 📋 Danh sách Permission Sets (Policies)

Người dùng này được gán các quyền hạn sau đây qua AWS IAM Identity Center:

1. **[TF4-SecReliabilityReadOnlyAudit](TF4-SecReliabilityReadOnlyAudit.md)**
   * **Mô tả**: Quyền đọc cấu hình hạ tầng mở rộng và các công cụ bảo mật (Security Hub, GuardDuty, WAFv2, Secrets Manager, KMS, ACM), đồng thời tích hợp thêm quyền quản trị toàn phần đối với IAM, AWS SSO (Identity Center), Identity Store, và quản lý EKS Access Entries được gom từ `TF4-SecurityIAMSSOManager`.
   * **Mục đích**: Giám sát lỗ hổng bảo mật, theo dõi các cảnh báo đe dọa trực tuyến, quản trị định danh/phân quyền người dùng và quản lý quyền truy cập Kubernetes Cluster.

2. **[TF4-SecurityIAMSSOManager](TF4-SecurityIAMSSOManager.md)**
   * **Mô tả**: Quyền quản trị toàn phần đối với IAM, SSO (IAM Identity Center), Identity Store và quản lý EKS Access Entries.
   * **Mục đích**: Cấp phát quyền hạn cho các thành viên khác, quản lý tài khoản/nhóm và điều phối quyền truy cập Kubernetes Cluster.

---
[⬅️ Quay lại trang chủ IAM Docs](../../README.md)
