# Test Runbook (Dành cho Mentor)

Chào Mentor, dưới đây là các bước để tự kiểm chứng Mandate 11: Bắt tại trận. Hệ thống đã được thiết lập để bắt các hành vi nguy hiểm, đo lường time-to-detect và định tuyến cảnh báo về Slack.

> [!WARNING]
> Chỉ dùng identity test đã được phê duyệt. Không dùng `root` và không chạy `StopLogging` hoặc `DeleteTrail` trên `tf4-general-cloudtrail`.

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

> [!NOTE]
> **Bài học từ thực tế (Troubleshooting):** Trong quá trình kiểm thử ban đầu, team ghi nhận hiện tượng các sự kiện nhạy cảm (như IAM CreateUser) bị bỏ sót hoàn toàn dù CloudTrail đã ghi nhận thành công. Nguyên nhân gốc rễ không phải do độ trễ của AWS (CloudTrail Delivery Latency), mà là do cấu trúc gộp chung mảng `$or` quá phức tạp trong một rule EventBridge. Việc tách thành 2 rule (Read-only và Write-only) đã khôi phục luồng nhận sự kiện. Chỉ kết luận đạt SLO `p95 < 60s` sau khi custom metric được deploy và có ít nhất ba datapoint runtime hợp lệ.

*(Đừng quên dọn dẹp sau khi test)*
```bash
aws iam delete-access-key --user-name mentor-test-user-11 --access-key-id <ACCESS_KEY_ID_VỪA_TẠO>
aws iam delete-user --user-name mentor-test-user-11
```

## Kịch bản 2: Truy cập Secret/Parameter bất hợp pháp (Read-only Management Event)
Hành động này kiểm chứng CloudTrail ghi nhận API đọc của Secrets Manager/SSM và EventBridge nhận read-only management event.

**Lệnh thực thi:**
```bash
# Chạy lệnh đọc Secret/Parameter (Có thể test bằng một giá trị không tồn tại)
aws secretsmanager get-secret-value --secret-id non-existent-secret-for-test-11
aws ssm get-parameter --name non-existent-param-for-test-11
```
*(Ngay cả khi tài nguyên không tồn tại, lệnh này vẫn được CloudTrail ghi lại)*

**Kỳ vọng:**
1. Kênh Slack sẽ nổ thông báo `🚨 Security Alert: GetSecretValue` hoặc `GetParameter`.
2. Latency cam kết `< 60 giây`.

> [!NOTE]
> **Bài học từ thực tế (Troubleshooting):** Sự kiện `GetSecretValue` và `GetParameter` là các API đọc (Read-only). Ban đầu hệ thống đã bỏ lỡ toàn bộ các sự kiện này. Qua quá trình debug chuyên sâu, team phát hiện root cause: AWS EventBridge mặc định (state `ENABLED`) sẽ lọc bỏ hoàn toàn các Read-Only Management Events từ CloudTrail để tiết kiệm chi phí. Để bắt được chúng, rule bắt buộc phải sử dụng state `ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS`. Đây là một phát hiện quan trọng giúp đảm bảo tính toàn vẹn (không bỏ lọt) của hệ thống Mandate 11.

## Kịch bản 3: Cố gắng vô hiệu hóa log (Blinding Threat)
Mô phỏng kẻ tấn công tắt trail. Hành động này được đánh dấu là `CRITICAL` và chỉ được test trên trail cô lập do CDO08/owner tạo riêng.

> [!CAUTION]
> Không chạy kịch bản này trên `tf4-general-cloudtrail`. Kịch bản nghiệm thu mặc định là Kịch bản 1; chỉ chạy `StopLogging` khi owner xác nhận trail test không chứa audit trail chính và có người chịu trách nhiệm bật lại ngay.

**Lệnh thực thi:**
```bash
aws cloudtrail stop-logging --name <isolated-test-trail>
aws cloudtrail start-logging --name <isolated-test-trail>
```

Nếu không có trail test cô lập, bỏ qua kịch bản này và dùng `CreateAccessKey` ở Kịch bản 1 để mentor kiểm tra luồng cảnh báo.

**Kỳ vọng:**
1. Kênh Slack nổ thông báo `🚨 Security Alert: StopLogging`.
2. **Severity:** `CRITICAL`.

---
Cảm ơn Mentor đã đánh giá! Toàn bộ luồng dữ liệu (CloudTrail -> EventBridge -> SNS -> Lambda -> Slack) hoạt động hoàn toàn ẩn, không ảnh hưởng đến storefront hay cổng vận hành. Mức chi phí cho hệ thống giám sát này nằm trong khoảng ~$3-5/tháng, hoàn toàn nằm trong ngân sách cho phép.
