# [Security/Compliance] Báo cáo các Finding Quan Trọng chưa đạt chuẩn (AUDIT-007)

## 1. Tóm tắt vấn đề
Trong quá trình Audit các cấu hình hạ tầng hiện hành, nhóm CDO07 đã phát hiện các khoảng trống (gap) quan trọng về mặt bảo mật và tuân thủ cần được team DevOps khắc phục gấp.

## 2. Chi tiết các Finding (Findings)

### 2.1. AWS CloudTrail
CloudTrail hiện đã được bật, nhưng chưa tuân thủ tiêu chuẩn Audit:
- `LogFileValidationEnabled = false`: Cần set thành `true` để đảm bảo tính toàn vẹn (integrity) của log.
- Chưa tích hợp CloudWatch Logs: Gây khó khăn cho việc query log real-time và tạo alert.
- Không có KMS key riêng: Cần dùng Customer Managed Key (CMK) để mã hóa log thay vì SSE-S3.
- Chỉ ghi *management events*: Đang thiếu cấu hình ghi *data events* (vd: đọc/ghi S3 object quan trọng).

### 2.2. AWS Config
- Dịch vụ AWS Config **chưa bật Configuration Recorder**. Hạ tầng không được theo dõi biến động cấu hình, vi phạm baseline tuân thủ.

### 2.3. IAM Access Analyzer
- Chưa tạo `analyzer` cho region đang dùng. (Lưu ý: Audit team đã chuẩn bị code `iam.tf` ở ticket AUDIT-005, DevOps chỉ cần apply).

## 3. Yêu cầu hành động cho DevOps (CDO08)
1. Cập nhật mã nguồn Terraform (đặc biệt là `cloudtrail.tf` và `config.tf`) để vá các lỗ hổng trên.
2. Cấu hình lại CloudTrail có đủ `kms_key_id`, bật `enable_log_file_validation` và `cloud_watch_logs_group_arn`.

## 4. Tiêu chí nghiệm thu (DoD)
- Terraform apply thành công.
- Nhóm Audit xác minh lại trên AWS Config và CloudTrail đáp ứng đầy đủ các tiêu chuẩn bảo mật.
