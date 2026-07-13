# Nhóm TF4-AIO01-AI

Nhóm này chịu trách nhiệm nghiên cứu, tích hợp và phát triển các mô hình AI/LLM, kiểm tra và đánh giá mô hình cũng như xử lý dữ liệu AI trong dự án TF4.

## 📋 Danh sách Permission Sets (Policies)

Nhóm này được gán các quyền hạn sau đây qua AWS IAM Identity Center:

1. **[TF4-BaseReadOnly](../../TF4-BaseReadOnly.md)**
   * **Mô tả**: Quyền chỉ đọc cơ bản đối với các hạ tầng lõi của AWS (EKS, EC2, CloudWatch, ECR, v.v.).
   * **Mục đích**: Cung cấp khả năng hiển thị cơ bản trạng thái hệ thống.

2. **[TF4-AIReadOnlyOrLimitedInvoke](TF4-AIReadOnlyOrLimitedInvoke.md)**
   * **Mô tả**: Quyền sử dụng mô hình Bedrock giới hạn (Claude 3.5 Sonnet và Llama 3), truy cập dữ liệu S3 Eval bucket, lấy cấu hình AI Secrets, và theo dõi log/metric liên quan đến dịch vụ AI.
   * **Mục đích**: Cho phép phát triển, đánh giá mô hình và chạy ứng dụng AI một cách an toàn mà vẫn giới hạn chi phí/tài nguyên sử dụng.

---
[⬅️ Quay lại trang chủ IAM Docs](../../README.md)
