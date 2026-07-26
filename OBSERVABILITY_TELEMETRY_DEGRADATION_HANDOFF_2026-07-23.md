# Bàn giao sự cố suy giảm telemetry

**Thời gian ghi nhận:** 2026-07-23, 13:33-14:37 UTC  
**Owner cần tiếp nhận:** CDO04 / owner hệ thống observability dùng chung  
**Trạng thái:** Đã ghi nhận sự cố runtime; AIO1 chưa thay đổi cấu hình observability.

## Hiện trạng và ảnh hưởng

- `product-reviews` vẫn `Ready 1/1`, restart `0`; chưa ghi nhận application
  outage hoặc mất dữ liệu giao dịch.
- Exporter của ứng dụng thỉnh thoảng nhận `StatusCode.UNAVAILABLE` khi gửi log,
  metric và trace.
- OTel Collector và Jaeger liên tục chạm ngưỡng memory limiter rồi từ chối dữ
  liệu. Một lần lỗi lúc `14:36:41 UTC` đã drop `5.587` trace item.
- Dữ liệu trong Jaeger, OpenSearch và Prometheus có thể bị thiếu, đứt quãng hoặc
  đến trễ. Dashboard, alert, AIOps detection và audit correlation có thể không
  đáng tin cậy.
- `kafkametrics` liên tục gọi `kafka:9092`, trong khi production đã tắt Kafka
  in-cluster; vì vậy hiện không thu được Kafka metrics.

Đây là **suy giảm observability kèm mất telemetry**, chưa phải sự cố
customer-facing đã được xác nhận.

## Bằng chứng

| Thành phần | Cấu hình hiện tại | Quan sát runtime |
|---|---|---|
| OTel Collector | limit `200Mi`, limiter `80%/25%` | Từ chối dữ liệu ở khoảng `118-124Mi` |
| Jaeger | limit `1Gi`, limiter `75%/15%` | Từ chối ở `618-666Mi`; ép GC ở `768-816Mi` |
| Kafka receiver | gọi `kafka:9092` mỗi 10 giây | DNS báo `no such host`; Kafka production đang tắt |

PR AI audit chỉ thay đổi `product-reviews`, không thay đổi cấu hình
observability dùng chung này.

## Hướng xử lý đề xuất — cần owner review

1. Gỡ `kafkametrics` khỏi metrics pipeline của production.
2. Cân nhắc tăng request/limit của OTel Collector lên `192Mi/384Mi`.
3. Cân nhắc giữ request Jaeger ở `1Gi` và tăng limit lên `2Gi`.
4. Nếu memory pressure vẫn còn, cần kiểm tra trace volume, batching, sampling và
   độ trễ ghi OpenSearch thay vì tiếp tục tăng memory.

Trade-off: thay đổi sẽ sử dụng thêm tài nguyên node dùng chung. Cần xác nhận node
headroom và thời điểm rollout trước khi deploy.

## Rollout và điều kiện nghiệm thu

- Collector sẽ rolling restart theo từng node; Jaeger dùng `Recreate`, do đó có
  thể xuất hiện một khoảng telemetry gap ngắn.
- Theo dõi 10-15 phút sau rollout: tất cả pod Ready; không còn
  `Refusing data`, `Dropping data`, `kafka:9092` hoặc exporter
  `StatusCode.UNAVAILABLE`.
- Chạy một AI smoke request; xác nhận record `ai_tool_audit` mới trong OpenSearch
  và trace tương ứng trong Jaeger.

**Quyết định cần owner xác nhận:** capacity, resource values, rollout window và
runtime acceptance.

**Ranh giới kết luận:** Chẩn đoán đã có bằng chứng runtime. Hướng xử lý mới ở
mức đề xuất; chưa implement, deploy hoặc được owner nghiệm thu.
