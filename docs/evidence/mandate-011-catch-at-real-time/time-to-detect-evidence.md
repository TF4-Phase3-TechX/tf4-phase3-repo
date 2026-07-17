# Bằng chứng Time-to-Detect (TTD)

Tài liệu này ghi nhận phương pháp và kết quả đo lường độ trễ (latency) của hệ thống cảnh báo từ khi sự kiện xảy ra đến khi tin nhắn đến được Slack.

## 1. Phương pháp đo
- **Công thức:** `Delta = Thời điểm Lambda xử lý (datetime.now()) - Thời điểm sự kiện (CloudTrail eventTime)`
- **Logic thực thi:** Nằm trong hàm `lambda_handler` (`infra/terraform/modules/security-slack-alerts/lambda_src/handler.py`).
- **Ghi nhận:** Giá trị Delta được:
  1. Ghi vào CloudWatch Logs dưới dạng `Metric: Mandate11/DetectionLatency = {delta_sec}`.
  2. Hiển thị trực tiếp vào nội dung tin nhắn Slack ở trường `*Latency:*`.

## 2. Mục tiêu cam kết (SLO)
- **Mục tiêu:** p95 < 60 giây. Nghĩa là 95% các cảnh báo phải đến được Slack trong vòng chưa đầy 1 phút kể từ khi hành động nguy hiểm xảy ra.

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
