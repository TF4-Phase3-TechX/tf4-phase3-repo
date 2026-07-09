# Nhóm TF4-CDO07-Auditability

Nhóm này chịu trách nhiệm thực hiện các công tác kiểm tra cấu hình, theo dõi audit logs (nhật ký hoạt động hệ thống), đảm bảo tính tuân thủ (compliance) và lưu trữ bằng chứng kiểm toán cho dự án TF4.

## 📋 Danh sách Permission Sets (Policies)

Nhóm này được gán các quyền hạn sau đây qua AWS IAM Identity Center:

1. **[TF4-BaseReadOnly](../../TF4-BaseReadOnly.md)**
   * **Mô tả**: Quyền chỉ đọc cơ bản đối với các hạ tầng lõi của AWS (EKS, EC2, CloudWatch, ECR, v.v.).
   * **Mục đích**: Cung cấp khả năng hiển thị cơ bản trạng thái hệ thống.

2. **[TF4-AuditReadOnlyAndAnalyze](TF4-AuditReadOnlyAndAnalyze.md)**
   * **Mô tả**: Quyền truy cập nhật ký audit (CloudTrail), lịch sử cấu hình (AWS Config), phân tích chính sách IAM (Access Analyzer), dữ liệu mã hóa (KMS Decrypt) và đọc S3 Evidence bucket.
   * **Mục đích**: Thực thi quy trình kiểm toán độc lập, điều tra bảo mật và đảm bảo tính tuân thủ mà không có quyền thay đổi hạ tầng.

---
[⬅️ Quay lại trang chủ IAM Docs](../../README.md)
