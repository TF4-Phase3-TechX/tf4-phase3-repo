# C0G-89 — D16-PERF-03: Xác định Critical-Path Latency Bottleneck với Jaeger

**Jira:** `C0G-89` — `[D16-PERF-03] Identify Critical-Path Latency Bottleneck with Jaeger`  
**Trạng thái evidence:** Ready for Tech Lead review  
**Nguồn dữ liệu:** [C0G-88 baseline](baseline-and-resources-consump/BASELINE-PERFORMANCE.md)

## Phạm vi và dữ liệu

Phân tích này chỉ dùng dữ liệu đã lưu của load test 200 concurrent users trong cửa sổ `2026-07-18T18:50:45Z` đến `2026-07-18T19:31:33Z`.

> Cửa sổ C0G-88 dài 40m48s nên không phải strict 15-minute acceptance run. Điều này không làm thay đổi kết luận trace-level bên dưới, nhưng kết quả sau tối ưu vẫn phải được xác nhận lại bằng strict run riêng.

| Flow | Endpoint | Requests | Failures | p95 | p99 |
|---|---|---:|---:|---:|---:|
| Browse | `GET /` | 3,894 | 1 | 310ms | 520ms |
| Cart read | `GET /api/cart` | 10,918 | 0 | 290ms | 500ms |
| Cart write | `POST /api/cart` | 21,505 | 0 | 99ms | 320ms |
| **Checkout** | **`POST /api/checkout`** | **7,095** | **0** | **500ms** | **820ms** |

Nguồn: [`locust/stats.csv`](baseline-and-resources-consump/runs/baseline-200-users-20260718T1850Z/locust/stats.csv). Trong phạm vi Browse → Cart → Checkout, `POST /api/checkout` có p99 cao nhất nên là flow bị ảnh hưởng.

## Jaeger evidence

| Vai trò | Trace ID | Loại request | Độ dài root trace | `PlaceOrder` server span | Preparation span |
|---|---|---|---:|---:|---:|
| Slow checkout | [`c2d1f3c03b6abbf5ac625dd285e74bb3`](baseline-and-resources-consump/runs/baseline-200-users-20260718T1850Z/traces/checkout-slow-c2d1f3c03b6abbf5ac625dd285e74bb3.json) | `user_checkout_multi`, 2 order items | 1,647.316ms | 1,006.513ms | 759.897ms |
| Representative checkout | [`0606c19c958648f9a92402a763394dc2`](baseline-and-resources-consump/runs/baseline-200-users-20260718T1850Z/traces/checkout-representative-0606c19c958648f9a92402a763394dc2.json) | `user_checkout_single`, 1 order item | 402.660ms | 57.072ms | 29.539ms |

Trace IDs được chọn từ [`selected-trace-ids.txt`](baseline-and-resources-consump/runs/baseline-200-users-20260718T1850Z/traces/selected-trace-ids.txt). Cả hai trace có `rpc.grpc.status_code=0`; slow trace trả HTTP `200`.

## Critical path và bottleneck

### Slow trace critical path

```text
POST /api/checkout (1,015.254ms)
└─ CheckoutService/PlaceOrder server (1,006.513ms)
   └─ prepareOrderItemsAndShippingQuoteFromCart (759.897ms)
      ├─ GetCart / Valkey (1.609ms / 0.764ms)
      ├─ ProductCatalog/GetProduct #1 → PostgreSQL (183.782ms / 130.688ms)
      ├─ Currency/Convert #1 (10.724ms)
      ├─ ProductCatalog/GetProduct #2 → PostgreSQL (250.679ms / 83.722ms)
      ├─ Currency/Convert #2 (298.793ms)
      ├─ Shipping quote (7.525ms)
      └─ Currency/Convert shipping (6.282ms)
   ├─ Payment/Charge (24.778ms)
   └─ Ship order (2.389ms)
```

`prepareOrderItemsAndShippingQuoteFromCart` là slowest application span trong `PlaceOrder`:

```text
759.897ms / 1,006.513ms = 75.5%
```

Nó cao hơn representative trace `730.358ms` (từ `29.539ms` lên `759.897ms`, xấp xỉ `25.7×`). Payment (`24.778ms`) và ship-order (`2.389ms`) không phải bottleneck của trace này.

## Root-cause statement

**Root cause:** checkout preparation xử lý từng cart item theo thứ tự: `GetProduct` rồi `Convert` cho item hiện tại trước khi bắt đầu item kế tiếp. Với slow multi-item trace, hai cặp work này tạo serial dependency trên critical path:

- item 1: `GetProduct` `183.782ms` → `Convert` `10.724ms`;
- item 2: `GetProduct` `250.679ms` → `Convert` `298.793ms`.

Tổng durations của hai `GetProduct` client spans là `434.461ms`; hai `Convert` client spans là `309.517ms`. Code hiện tại xác nhận thứ tự này: [`prepOrderItems`](../../../techx-corp-platform/src/checkout/main.go#L579-L600) dùng vòng lặp tuần tự, và [`prepareOrderItemsAndShippingQuoteFromCart`](../../../techx-corp-platform/src/checkout/main.go#L447-L485) chỉ quote shipping sau khi đã chuẩn bị toàn bộ item.

Đây là kết luận từ span parent/child, `startTime`, duration và code path hiện hữu; không suy luận từ CPU hay memory snapshot.

## Các giả thuyết đã kiểm tra

| Hạng mục Jira yêu cầu | Quan sát từ trace/code | Kết luận |
|---|---|---|
| Repeated span | Hai `ProductCatalog/GetProduct`, hai product `postgresql`, hai item-level `Currency/Convert` trong order 2 items. | Có repeated per-item calls; đây là nguồn serial work. |
| Sequential downstream call | Item 2 bắt đầu sau item 1 conversion; source loop xử lý từng item tuần tự. | Có serial dependency đã xác nhận. |
| DB query count | 2 PostgreSQL `SELECT ... WHERE p.id = $1` spans, một cho mỗi product lookup. | 2 queries trong trace; không phải N+1 vượt ngoài số item ở sample này. |
| Connection wait | Không có span/tag pool wait hoặc `sql.conn.acquire`. | Không đủ telemetry để kết luận có/không connection wait. |
| Serialization | Không có serialization span; JSON shipping payload không nằm trên slow segment đáng kể. | Không đủ telemetry để kết luận serialization là cause. |
| Cache miss | Cart dùng Valkey `HGET` thành công trong `0.764ms`; catalog trace cho thấy PostgreSQL query nhưng không có cache-hit/miss tag. | Cart cache không phải bottleneck; không kết luận catalog cache miss. |
| Retry | `retryRead` tồn tại cho read calls, nhưng selected slow trace không có error status, retry event hoặc repeated failed attempt. | Không có retry evidence trong trace này. |
| Queue buildup | `kafkaQueueProblems=off`; không có queue-wait/error span trong critical preparation branch. | Không có queue buildup evidence trong trace này. |

## Đề xuất optimization (không thêm compute)

Thay đổi `prepOrderItems` để thực hiện product lookup và currency conversion cho các cart item **concurrently với bounded fan-out**, sau đó ghép kết quả theo index ban đầu. Không thay đổi replica, CPU, memory hoặc HPA.

- Giới hạn concurrency theo số cart items (và một upper bound nhỏ) để không tạo request burst không kiểm soát đến Product Catalog/Currency.
- Dùng `errgroup.WithContext` hoặc `sync.WaitGroup` + cancellation để trả error an toàn và giữ nguyên thứ tự items.
- Giữ `retryRead` per-call hiện có; không retry payment/ship-order.
- Shipping quote có thể chạy song song với item preparation vì nó chỉ dùng `address` và `cartItems`; đây là follow-up tối thiểu sau khi bounded item fan-out được benchmark.

### Expected p99 impact

Nếu chỉ song song hóa hai item branches của trace mẫu, critical duration của phần item work chuyển từ tổng `743.978ms` (`434.461ms + 309.517ms`) sang branch dài nhất khoảng `549.472ms` (`250.679ms + 298.793ms`): ceiling lý thuyết là giảm khoảng `194.506ms` trên preparation span.

Do đó mục tiêu thực nghiệm hợp lý là giảm checkout p99 từ baseline `820ms` về khoảng **625ms hoặc thấp hơn**, nhưng đây là **estimate, không phải SLO claim**. Tail latency, downstream contention, item count và trace sampling có thể làm kết quả khác; phải xác nhận bằng strict 200-user/15-minute post-change run.

## Risks và trade-offs

- Bounded fan-out giảm serial latency nhưng tăng concurrent load lên Product Catalog, PostgreSQL và Currency; cần giới hạn rõ ràng và đo error rate/p99 sau thay đổi.
- Cancellation/error aggregation phức tạp hơn; response phải vẫn fail atomically trước payment nếu bất kỳ preparation call nào lỗi.
- Kết quả `orderItems` phải giữ đúng thứ tự cart để không thay đổi order semantics.
- Không song song hóa payment, shipping fulfillment, empty-cart hoặc Kafka publish vì chúng có side effect/thứ tự nghiệp vụ.

## Jira acceptance checklist

- [x] Bottleneck có Jaeger evidence.
- [x] Không kết luận chỉ từ phỏng đoán.
- [x] Có before span duration.
- [x] Có root-cause statement rõ.
- [x] Có optimization proposal không thêm compute.
- [ ] Tech Lead review hoàn tất.

## Tech Lead review

| Reviewer | Ngày | Quyết định | Ghi chú |
|---|---|---|---|
| Pending | — | Pending | Cần xác nhận bounded fan-out không vi phạm downstream capacity và order semantics trước khi triển khai. |
