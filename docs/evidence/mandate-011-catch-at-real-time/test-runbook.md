# Test Runbook (Dành cho Mentor)

Chào Mentor, dưới đây là các bước để tự kiểm chứng Mandate 11: Bắt tại trận. Hệ thống đã được thiết lập để bắt các hành vi nguy hiểm, đo lường time-to-detect và định tuyến cảnh báo về Slack.

> [!WARNING]
> Vui lòng chỉ thực thi các lệnh dưới đây. Không chạy lệnh bằng `root` account trên Production thực tế nếu không cần thiết.

## Kịch bản 1: Cố gắng tạo một IAM Access Key (Identity Threat)
Hành động này mô phỏng kẻ tấn công tạo một backdoor access key để duy trì quyền truy cập.

**Lệnh thực thi:**
```bash
# Tạo một user test tạm thời
aws iam create-user --user-name mentor-test-user-11

# Tạo access key cho user này (Hành động kích hoạt báo động)
aws iam create-access-key --user-name mentor-test-user-11
```

**Kỳ vọng:**
1. Trên kênh Slack sẽ nổ 1 thông báo `🚨 Security Alert: CreateAccessKey`.
2. Kiểm tra thông tin trong Slack:
   - **Actor:** (Tên IAM Role/User mà Mentor đang dùng để chạy lệnh)
   - **Severity:** HIGH
   - **Latency:** `< 60 giây` (Time-to-detect được hệ thống Lambda tự đo).
   - **Investigate:** Click vào link để mở thẳng CloudTrail Console.

*(Đừng quên dọn dẹp sau khi test)*
```bash
aws iam delete-access-key --user-name mentor-test-user-11 --access-key-id <ACCESS_KEY_ID_VỪA_TẠO>
aws iam delete-user --user-name mentor-test-user-11
```

## Kịch bản 2: Truy cập Secret bất hợp pháp (Data Threat)
Hành động này kiểm chứng CloudTrail Data Events đã được bật cho Secrets Manager và EventBridge đang bắt đúng.

**Lệnh thực thi:**
```bash
# Chạy lệnh đọc Secret (Có thể test bằng một secret rỗng hoặc secret test)
aws secretsmanager get-secret-value --secret-id non-existent-secret-for-test-11
```
*(Ngay cả khi secret không tồn tại, lệnh này vẫn được CloudTrail ghi lại)*

**Kỳ vọng:**
1. Kênh Slack sẽ nổ thông báo `🚨 Security Alert: GetSecretValue`.
2. Latency cam kết `< 60 giây`.

## Kịch bản 3: Cố gắng vô hiệu hóa log (Blinding Threat)
Mô phỏng kẻ tấn công tắt trail. Hành động này được đánh dấu là `CRITICAL`.

**Lệnh thực thi:**
```bash
aws cloudtrail stop-logging --name tf4-general-cloudtrail
```
*(Nếu bạn bị vướng lỗi `AccessDenied` do SCP ở Mandate 12, sự kiện AccessDenied vẫn sẽ được CloudTrail ghi nhận và cảnh báo)*

**Kỳ vọng:**
1. Kênh Slack nổ thông báo `🚨 Security Alert: StopLogging`.
2. **Severity:** `CRITICAL`.

---
Cảm ơn Mentor đã đánh giá! Toàn bộ luồng dữ liệu (CloudTrail -> EventBridge -> SNS -> Lambda -> Slack) hoạt động hoàn toàn ẩn, không ảnh hưởng đến storefront hay cổng vận hành. Mức chi phí cho hệ thống giám sát này nằm trong khoảng ~$3-5/tháng, hoàn toàn nằm trong ngân sách cho phép.
