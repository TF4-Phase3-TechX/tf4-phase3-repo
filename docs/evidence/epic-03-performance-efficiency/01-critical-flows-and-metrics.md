# PERF-01: Define Critical Flows & Metrics Matrix

## 1. Mục tiêu

Xác định các flow quan trọng cần đo performance và mapping metric phù hợp cho từng flow.

Tài liệu này dùng làm evidence cho Epic Performance Efficiency và làm input cho các task tiếp theo liên quan đến load test, monitoring, dashboard, alerting và Week 1 Pitch.

---

## 2. Critical Flows cần đo

| Flow ID | Flow | Mục tiêu nghiệp vụ / kỹ thuật | Lý do critical | Priority |
|---|---|---|---|---|
| F01 | Browse Product Flow | Người dùng xem danh sách sản phẩm, filter, search, pagination | Đây là flow có traffic cao, ảnh hưởng trực tiếp trải nghiệm tìm kiếm sản phẩm | High |
| F02 | Product Detail Flow | Người dùng xem chi tiết sản phẩm, giá, tồn kho, mô tả, review | Ảnh hưởng trực tiếp đến quyết định mua hàng | High |
| F03 | Cart Flow | Người dùng thêm, sửa, xóa sản phẩm trong giỏ hàng | Flow trung gian trước checkout, cần ổn định và phản hồi nhanh | High |
| F04 | Checkout Flow | Người dùng xác nhận đơn hàng, địa chỉ, voucher, shipping fee | Flow quan trọng trước thanh toán, lỗi ở đây làm mất đơn hàng | Highest |
| F05 | Payment Flow | Người dùng thực hiện thanh toán, hệ thống nhận payment result/webhook | Flow ảnh hưởng trực tiếp doanh thu, cần đo latency và error nghiêm ngặt | Highest |
| F06 | AI Review / Summary Flow | Hệ thống tạo hoặc lấy tóm tắt review bằng AI | Có dependency bên ngoài, dễ phát sinh timeout, cost cao, cần fallback | High |
| F07 | Kafka Async Order Event Flow | Hệ thống publish/consume event sau khi order/payment thành công | Ảnh hưởng đến xử lý async như inventory, notification, audit, fulfillment | Highest |

---

## 3. Metrics cần đo

| Metric | Ý nghĩa | Cách hiểu |
|---|---|---|
| p95 latency | 95% request hoàn thành dưới ngưỡng này | Dùng để đánh giá trải nghiệm phần lớn user |
| p99 latency | 99% request hoàn thành dưới ngưỡng này | Dùng để phát hiện tail latency, request chậm bất thường |
| Request rate | Số request trên giây/phút | Dùng để biết flow nào có tải cao |
| Error rate | Tỷ lệ request lỗi | Bao gồm HTTP 5xx, timeout, business error quan trọng |
| CPU usage | Mức sử dụng CPU của service | Dùng để phát hiện bottleneck xử lý |
| Memory usage | Mức sử dụng RAM của service | Dùng để phát hiện memory leak hoặc quá tải |
| DB latency | Thời gian query database | Quan trọng với product, cart, checkout, payment |
| External dependency latency | Thời gian gọi service ngoài | Quan trọng với payment gateway và AI provider |
| Kafka producer error | Lỗi khi publish event | Quan trọng với order event |
| Kafka consumer lag | Số lượng message chưa xử lý | Dùng để đánh giá async processing có bị backlog không |

---

## 4. Metrics Matrix theo từng Flow

| Flow ID | Flow | p95 Latency Target | p99 Latency Target | Request Rate | Error Rate Target | CPU / Memory | DB Metric | External Metric | Kafka Metric |
|---|---|---:|---:|---|---:|---|---|---|---|
| F01 | Browse Product | <= 300ms | <= 800ms | RPS theo load test | <= 1% | CPU, Memory của product service | Product query latency, pagination query latency | N/A | N/A |
| F02 | Product Detail | <= 350ms | <= 900ms | RPS theo load test | <= 1% | CPU, Memory của product service | Product detail query latency, review query latency | N/A hoặc cache latency nếu có | N/A |
| F03 | Cart | <= 400ms | <= 1000ms | RPS theo load test | <= 1% | CPU, Memory của cart/order service | Cart read/write latency | N/A | N/A |
| F04 | Checkout | <= 800ms | <= 1500ms | RPS theo load test | <= 2% | CPU, Memory của order service | Order transaction latency, inventory check latency | Shipping/voucher service latency nếu có | Order event publish latency |
| F05 | Payment | <= 1200ms | <= 2500ms | RPS theo load test | <= 2% | CPU, Memory của payment service | Payment transaction update latency | Payment gateway latency, webhook latency | Payment event publish latency |
| F06 | AI Review / Summary | <= 3000ms | <= 5000ms | RPS theo load test | <= 3% | CPU, Memory của AI/review service | Review query latency, summary cache latency | AI provider latency, AI timeout rate | N/A |
| F07 | Kafka Async Order Event | <= 500ms publish latency | <= 1000ms publish latency | Message/sec | <= 1% publish/consume error | CPU, Memory của consumer | Audit/order update latency nếu consumer ghi DB | N/A | Consumer lag, message processing time, DLQ count |

---

## 5. Endpoint / Component Mapping

| Flow | Endpoint / Component cần đo | Ghi chú |
|---|---|---|
| Browse Product | `GET /products` | Đo search, filter, sort, pagination |
| Product Detail | `GET /products/:id` | Đo query product detail, inventory, review summary nếu có |
| Cart | `GET /cart`, `POST /cart/items`, `PATCH /cart/items/:id`, `DELETE /cart/items/:id` | Đo read/write cart |
| Checkout | `POST /checkout/preview`, `POST /orders` | Đo validate cart, inventory, coupon, shipping, tạo order |
| Payment | `POST /payments`, `POST /payments/webhook` | Đo payment request, callback/webhook, update order status |
| AI Review / Summary | `GET /products/:id/review-summary`, `POST /ai/reviews/summary` | Đo AI latency, timeout, fallback |
| Kafka Async Order Event | `order.created`, `payment.succeeded`, `order.completed` | Đo producer, consumer, lag, retry, DLQ |

---

## 6. SLO / Threshold đề xuất ban đầu

| Nhóm | Target |
|---|---|
| API availability | >= 99.5% |
| Critical API p99 latency | Checkout/Payment p99 <= 2500ms |
| Normal API p99 latency | Browse/Product/Cart p99 <= 1000ms |
| AI flow timeout | Timeout sau 5000ms, cần fallback |
| Error rate | Normal flow <= 1%, critical flow <= 2%, AI flow <= 3% |
| Kafka consumer lag | Không vượt quá 60 giây backlog trong điều kiện tải bình thường |
| DLQ count | 0 trong happy path test |
| CPU usage | Cảnh báo khi > 70%, critical khi > 85% |
| Memory usage | Cảnh báo khi > 75%, critical khi > 90% |

---

## 7. Flow Priority cho Performance Test

| Priority | Flow | Lý do |
|---|---|---|
| P0 | Checkout Flow | Ảnh hưởng trực tiếp đến khả năng tạo đơn |
| P0 | Payment Flow | Ảnh hưởng trực tiếp doanh thu |
| P0 | Kafka Async Order Event Flow | Ảnh hưởng xử lý hậu kỳ đơn hàng |
| P1 | Browse Product Flow | Traffic cao |
| P1 | Product Detail Flow | Ảnh hưởng quyết định mua hàng |
| P1 | Cart Flow | Ảnh hưởng conversion trước checkout |
| P2 | AI Review / Summary Flow | Có dependency AI, cần kiểm soát timeout/cost |

---

## 8. Risk / Bottleneck cần theo dõi

| Flow | Risk chính | Metric dùng để phát hiện |
|---|---|---|
| Browse Product | Query chậm khi filter/search nhiều | p95/p99 latency, DB latency, CPU |
| Product Detail | Load nhiều dữ liệu liên quan như review, inventory | p95/p99 latency, DB latency |
| Cart | Write conflict, update cart liên tục | Error rate, DB write latency |
| Checkout | Transaction dài, lock inventory, validate nhiều bước | p99 latency, DB transaction latency, error rate |
| Payment | Payment gateway chậm hoặc webhook retry | External latency, timeout rate, error rate |
| AI Review / Summary | AI provider timeout, response chậm, cost cao | AI latency, timeout rate, fallback rate |
| Kafka Async Order Event | Consumer xử lý chậm, backlog tăng | Consumer lag, processing time, DLQ count |

---

## 9. Checklist Review với TechLead

| Item | Status |
|---|---|
| Critical flows đã bao phủ Browse, Product Detail, Cart, Checkout, Payment | Done |
| Đã bổ sung AI Review / Summary Flow | Done |
| Đã bổ sung Kafka Async Order Event Flow | Done |
| Có p95/p99 latency cho từng flow | Done |
| Có request rate cho từng flow | Done |
| Có error rate cho từng flow | Done |
| Có CPU / memory metric | Done |
| Có DB latency metric | Done |
| Có external dependency metric cho Payment và AI | Done |
| Có Kafka lag / DLQ / processing time | Done |
| Có priority P0/P1/P2 cho performance test | Done |
| Cần TechLead confirm threshold cuối cùng | Pending Review |

---

## 10. Kết luận

Danh sách flow và metrics hiện tại đủ để dùng cho Week 1 Pitch và làm input cho các task performance tiếp theo.

Các flow critical nhất cần ưu tiên đo trước:

1. Checkout Flow
2. Payment Flow
3. Kafka Async Order Event Flow
4. Browse Product Flow
5. Product Detail Flow
6. Cart Flow
7. AI Review / Summary Flow

Các metric bắt buộc cần có trong performance report:

- p95 latency
- p99 latency
- request rate
- error rate
- CPU usage
- memory usage
- DB latency
- external dependency latency
- Kafka consumer lag
- DLQ count