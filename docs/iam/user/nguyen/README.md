# Người dùng: nguyen

Tài khoản của người dùng **nguyen** chịu trách nhiệm quản trị bảo mật hệ thống, cấu hình danh tính (SSO), quản lý chính sách phân quyền (IAM) và giám sát hạ tầng dự án TF4.

## 📋 Danh sách Permission Sets (Policies)

Người dùng này được gán các quyền hạn sau đây qua AWS IAM Identity Center:

1. **[TF4-SecReliabilityReadOnlyAudit](TF4-SecReliabilityReadOnlyAudit.md)**
   * **Mô tả**: Quyền đọc thông tin bảo mật hệ thống rộng (Security Hub, GuardDuty, ACM, KMS, WAFv2) và giám sát hạ tầng.
   * **Mục đích**: Đánh giá và kiểm toán an toàn thông tin hạ tầng thường xuyên.

2. **[TF4-SecurityIAMSSOManager](TF4-SecurityIAMSSOManager.md)**
   * **Mô tả**: Quyền quản trị toàn phần đối với IAM, SSO (IAM Identity Center), Identity Store và quản lý EKS Access Entries.
   * **Mục đích**: Cấp phát quyền hạn cho các thành viên khác, quản lý tài khoản/nhóm và điều phối quyền truy cập Kubernetes Cluster.

---
[⬅️ Quay lại trang chủ IAM Docs](../../README.md)
