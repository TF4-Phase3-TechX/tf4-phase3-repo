# Nhóm TF4-CDO04-CostPerformance

Nhóm này chịu trách nhiệm giám sát, phân tích chi phí và tối ưu hóa hiệu năng hệ thống của dự án TF4.

## 📋 Danh sách Permission Sets (Policies)

Nhóm này được gán các quyền hạn sau đây qua AWS IAM Identity Center:

1. **[TF4-BaseReadOnly](../../TF4-BaseReadOnly.md)**
   * **Mô tả**: Quyền chỉ đọc cơ bản đối với các hạ tầng lõi của AWS (EKS, EC2, CloudWatch, ECR, v.v.).
   * **Mục đích**: Cung cấp khả năng hiển thị cơ bản trạng thái hệ thống.

2. **[TF4-CostPerfReadOnlyAlerting](TF4-CostPerfReadOnlyAlerting.md)**
   * **Mô tả**: Quyền truy cập các công cụ phân tích chi phí, quản lý ngân sách và tối ưu hóa hiệu năng (Trusted Advisor, Compute Optimizer).
   * **Mục đích**: Theo dõi ngân sách, lập hóa đơn, phát hiện bất thường chi phí và đề xuất tối ưu hóa cấu hình tài nguyên.

---
[⬅️ Quay lại trang chủ IAM Docs](../../README.md)
