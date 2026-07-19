# Alert Flow Diagram

Dưới đây là sơ đồ kiến trúc thể hiện đường đi của dữ liệu từ khi sự kiện nguy hiểm xảy ra cho đến khi hệ thống phát cảnh báo tới người vận hành.

![Alert Flow Diagram](./images/eventbridge-diagram.gif)

## Các thành phần chính
1. **CloudTrail:** Bắt mọi API calls (bao gồm cả Management Events, Read-Only và Write-Only).
2. **EventBridge (2 Rules: `cloudtrail_alerts_readonly_sensitive` & `cloudtrail_alerts_writeonly_sensitive`):** Hoạt động như một bộ lọc siêu tốc, chặn các Read-Only và Write-Only events nguy hiểm có trong danh sách (Event Catalog). Rule Read-Only được cấp đặc quyền `ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS` để không bỏ sót các sự kiện như `GetSecretValue`.
3. **SNS (`audit-security-alerts`):** Đóng vai trò làm router trung gian, giúp dễ dàng mở rộng thêm kênh cảnh báo (VD: Email, PagerDuty) về sau.
4. **Lambda (`audit-security-slack-alerts`):** Xử lý logic nghiệp vụ (tính time-to-detect, giảm nhiễu) và trang trí tin nhắn cho dễ đọc.
5. **Slack Webhook:** Kênh nhận tin nhắn trực tiếp của đội bảo mật.
