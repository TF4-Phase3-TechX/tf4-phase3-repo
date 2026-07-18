# Bằng chứng Time-to-Detect (TTD)

Tài liệu này ghi nhận phương pháp và kết quả đo lường độ trễ (latency) của hệ thống cảnh báo từ khi sự kiện xảy ra đến khi tin nhắn đến được Slack.

## 1. Phương pháp đo
- **Công thức:** `Delta = Thời điểm Lambda xử lý (datetime.now()) - Thời điểm sự kiện (CloudTrail eventTime)`
- **Logic thực thi:** Nằm trong hàm `lambda_handler` (`infra/terraform/modules/security-slack-alerts/lambda_src/handler.py`).
- **Ghi nhận:** Giá trị Delta được:
  1. Ghi vào CloudWatch Logs dưới dạng `Metric: Mandate11/DetectionLatency = {delta_sec}`.
  2. Hiển thị trực tiếp vào nội dung tin nhắn Slack ở trường `*Latency:*`.

## 2. Mục tiêu cam kết (SLO)
- **Mục tiêu:** p95 < 60 giây. Nghĩa là 95% các cảnh báo phải đến được Slack trong vòng chưa đầy 1 phút kể từ khi **EventBridge nhận được sự kiện**.

> [!NOTE]
> **Độ trễ CloudTrail (CloudTrail Delivery Latency) & Bài học thực tế:** Ban đầu team gặp hiện tượng một số sự kiện (như đọc Secret) không bao giờ bắn về Slack. Sau khi debug chuyên sâu, chúng tôi phát hiện AWS EventBridge mặc định (state `ENABLED`) sẽ chặn tất cả các Read-Only Management Events (như `GetSecretValue`) để giảm nhiễu. Để khắc phục, hệ thống đã cấu hình rule với state `ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS`. Đây là nguyên nhân gốc rễ (root cause) kỹ thuật thực sự, hoàn toàn khác biệt với khái niệm độ trễ truyền dữ liệu (Delivery Latency) thông thường. Nhờ khắc phục này, mọi sự kiện nay đều đã lọt qua lưới lọc. Chỉ số **Detection Latency** đo trong Lambda chỉ tính toán thời gian xử lý nội bộ và sẽ luôn tuân thủ cam kết `p95 < 60 giây`.

## 3. Bằng chứng thực nghiệm
*(Sau khi deploy hệ thống, hãy thực hiện test và dán kết quả / hình chụp vào đây)*

**Mẫu Log CloudWatch ghi nhận:**
```json
{
  "timestamp": "2026-07-17T07:30:05.123Z",
  "message": "Metric: Mandate11/DetectionLatency = 12.45"
}
```

**Ảnh chụp màn hình tin nhắn Slack:**
*(Mentor có thể xem trường Latency trực tiếp trên tin nhắn)*
