# ADR-011: Bổ sung SQS Dead Letter Queue (DLQ) chống mất dữ liệu cảnh báo

## 1. Trạng thái
**Đã phê duyệt** (2026-07-21)

## 2. Bối cảnh (Context)
Hiện tại, hệ thống giám sát và cảnh báo bảo mật (Mandate 11) sử dụng pipeline:
`CloudTrail -> EventBridge -> SNS -> Lambda -> Slack`

Trong quá trình nghiệm thu, Audit Team đã chỉ ra một kịch bản rủi ro (lỗ hổng kiến trúc): Nếu webhook của Slack bị sập hoặc gặp sự cố mạng kéo dài (ví dụ 45 phút), hàm Lambda gửi cảnh báo sẽ bị lỗi (HTTP 5xx / Timeout). 
Theo cơ chế bất đồng bộ của AWS, khi Lambda thất bại, SNS sẽ tự động gọi lại (retry) 2 lần. Tuy nhiên, nếu sự cố kéo dài, cả 3 lần gọi (1 lần đầu + 2 lần retry) đều sẽ thất bại. Do hệ thống chưa được cấu hình Dead Letter Queue (DLQ), các sự kiện cảnh báo siêu nhạy cảm này sẽ bị **drop (vứt bỏ) hoàn toàn** khỏi hàng đợi. Hệ quả là hệ thống bị mất dữ liệu cảnh báo (Data Loss) ở tầng notification và sự cố bảo mật sẽ bị bỏ lọt.

## 3. Quyết định (Decision)
Để khắc phục rủi ro mất dữ liệu, chúng ta quyết định:
1. **Thiết lập một SQS Standard Queue** (`audit-security-alerts-dlq`) làm Dead Letter Queue.
2. Cấu hình tính năng **Event Invoke Config** (Destination on Failure) của Lambda để điều hướng các event bị thất bại sau khi hết số lần retry vào hàng đợi SQS DLQ này.
3. Cấp quyền `sqs:SendMessage` cho IAM Role của Lambda để ghi dữ liệu vào DLQ.
4. Bổ sung một luồng dự phòng bằng **Email** qua SNS (gửi về `buithanhnghia@dtu.edu.vn`) để ngay cả khi Slack sập, cảnh báo vẫn có thể tới tay admin qua hòm thư.
5. Bổ sung thêm một Lambda **Redriver** (hoặc sử dụng EventBridge sau này) để định kỳ đọc dữ liệu từ DLQ và gửi lại lên Slack, đảm bảo dữ liệu không bị mất vĩnh viễn.

## 4. Giải trình & Phân tích Chi phí (Cost Analysis)

### 4.1. Giải trình kiến trúc
Việc chọn SQS làm DLQ được đưa ra thay vì dùng EventBridge DLQ hay SNS DLQ vì:
- Lambda Destination (`on_failure`) có khả năng bắt được không chỉ payload gốc mà còn bắt được thông tin lỗi (Error message, Stack trace), giúp dễ dàng điều tra nguyên nhân thất bại hơn.
- SQS là dịch vụ lưu trữ hàng đợi bền bỉ, message có thể lưu trữ tối đa 14 ngày, đủ thời gian để kỹ sư khắc phục sự cố Slack webhook và redrive (bơm lại) các message này.

### 4.2. Tính toán chi phí (Cost - Cập nhật bảng giá AWS tháng 07/2026)
**Phát sinh chi phí cho SQS:**
- SQS Standard Queue được miễn phí **1 triệu requests đầu tiên** mỗi tháng (theo chính sách AWS Free Tier).
- Sau 1 triệu requests, giá là $0.40/triệu requests.
- Khối lượng sự kiện bảo mật cảnh báo hiện tại chỉ rơi vào khoảng vài chục đến vài trăm sự kiện mỗi tháng. Kể cả trong trường hợp bị tấn công dồn dập hoặc spam, số lượng sự kiện cũng khó vượt qua ngưỡng 10,000 sự kiện/tháng.
- **Dự toán:** $0.00 / tháng (nằm hoàn toàn trong Free Tier).

**Phát sinh chi phí cho SNS Email Subscription:**
- AWS SNS cho phép gửi miễn phí **1,000 email đầu tiên** mỗi tháng.
- Số lượng cảnh báo thấp hơn mức này rất nhiều.
- **Dự toán:** $0.00 / tháng.

**Tổng chi phí dự kiến:** ~$0 / tháng.

## 5. Hậu quả (Consequences)
**Tích cực:**
- Triệt tiêu hoàn toàn rủi ro Data Loss khi có sự cố ở endpoint đích (Slack).
- Bổ sung thêm kênh email làm kênh liên lạc dự phòng cực kỳ tin cậy.

**Tiêu cực:**
- Tăng nhẹ số lượng tài nguyên cần quản lý bằng Terraform (thêm SQS và các Policy đi kèm).
- Cần có quy trình redrive thủ công (hoặc viết thêm tool) để lấy message từ DLQ gửi lại lên Slack sau khi Slack hoạt động bình thường.
