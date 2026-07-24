# Các vấn đề Performance cần cải thiện

**Mục tiêu:** giảm p95/p99 của Browse → Cart → Checkout dưới cùng sustained-load contract, đồng thời giữ nguyên correctness, reliability và resource invariants.

Tài liệu ghi nhận vấn đề, evidence, hướng điều tra và các corrective change đã được merge. Mọi kết luận về p95/p99 vẫn cần baseline và optimized run cùng sustained-load contract.

## Nguyên tắc không được vi phạm

Các improvement không được đổi latency lấy compute hoặc correctness:

- Không tăng worker node, node-hours, instance class hoặc cluster capacity.
- Không tăng HPA minimum replicas.
- Không tăng CPU/memory requests chỉ để cải thiện số đo.
- Không giảm load, rút ngắn measurement window hoặc thay endpoint mix giữa before/after.
- Không disable tracing, logging, flagd, retry hay validation để giảm latency.
- Browse, Cart và Checkout phải giữ kết quả đúng; error rate không được tăng.

## 1. Two-worker Product Catalog reads trong Checkout preparation gây quá tải — regression đã xác minh

### Evidence hiện có

Current Jaeger trace cho thấy `prepareOrderItemsAndShippingQuoteFromCart` mất **21.498 ms**, chiếm khoảng 59% selected `CheckoutService/PlaceOrder` span (**36.348 ms**). Trong phase này trace có Product Catalog, Currency và Quote dependency trước Payment.

Controlled reapply của worker pool hai Product Catalog reads từ PR [#496](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/496) làm Product Catalog quá tải và Checkout fail liên tục dưới load. Để tiếp tục quan sát, `getProducts` đã được trả về một Product Catalog RPC in-flight theo từng Checkout tại commit [`42e10de`](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/commit/42e10de) / PR [#558](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/558).

Kết luận này chỉ áp dụng cho fan-out hai-worker Product Catalog. Independent Shipping quote parallelization, non-USD `BatchConvert`, validation, retry/deadline và exact-money handling vẫn giữ nguyên trong corrective change; chúng không bị quy kết là nguyên nhân của regression này.

### Đã xử lý để tiếp tục quan sát

- Product Catalog reads trong `getProducts` chạy tuần tự, giữ nguyên thứ tự cart item, retry/deadline và nil-response validation.
- Parallel order-item preparation với independent Shipping quote vẫn giữ nguyên; lỗi ở một nhánh vẫn cancel nhánh còn lại trước Payment, fulfillment hoặc cart mutation.
- Non-USD item conversion vẫn dùng `CurrencyService.BatchConvert`, với validation response/cardinality/currency/money và checked money arithmetic.

Không dùng finding này để suy ngược một root cause đơn lẻ cho các incident lịch sử không thuộc controlled reapply.

## 2. Confirmation hydration N+1 Product Catalog reads — đã xử lý ở PR #565

### Evidence hiện có

Trước PR [#565](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/565), Checkout đã tính authoritative `cost` trước Payment nhưng sau khi `CheckoutGateway.placeOrder` trả về, `frontend/pages/api/checkout.ts` vẫn gọi `ProductCatalogService.getProductForDisplay(productId)` một lần cho từng order item. Multi-item cart vì vậy tạo N Product Catalog gRPC `GetProduct` độc lập trên confirmation path.

### Đã triển khai

PR [#565](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/565) loại bỏ các read thừa trên normal confirmation path:

- Thêm field protobuf additive `OrderItem.product_display`, gồm `name`, `picture`, `categories`.
- Checkout tái sử dụng display metadata từ kết quả Product Catalog đã đọc để định giá; không tạo Product Catalog RPC mới.
- Product Catalog reads trong Checkout vẫn tuần tự; không khôi phục fan-out hai worker từng gây quá tải.
- Frontend confirmation ưu tiên `productDisplay` từ Checkout response, nên không còn N lần `getProductForDisplay` trên normal path.
- Khi frontend mới gặp Checkout pod cũ chưa trả `product_display`, frontend fallback về `getProductForDisplay`; rollout/mixed-version vẫn không làm confirmation lỗi.
- Monetary fields và shipping cost từ Checkout response vẫn là authoritative.

Regression coverage xác nhận display metadata giữ đúng thứ tự, trường hiển thị, `cost`, shipping cost và error behavior cho multi-item confirmation.

## 3. Browse catalog có N+1 Currency fan-out với non-USD — đã xử lý ở PR #324

### Evidence hiện có

Trước PR #324, Browse catalog lấy danh sách product rồi thực hiện Currency conversion theo từng product khi selected currency không phải USD. Đây là N+1 downstream pattern: một list request sinh nhiều Currency RPC.

Ở tải thấp pattern có thể chưa lộ rõ. Dưới sustained load, fan-out làm tăng Currency request volume, contention và xác suất một slow call ảnh hưởng response tail.

### Đã triển khai

PR [#324](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/324) thay thế N Currency `Convert` RPC bằng một `BatchConvert` RPC cho mỗi Browse non-USD:

- `CurrencyService.BatchConvert` nhận toàn bộ product prices, validate toàn bộ currency codes trước khi trả kết quả, và giữ nguyên thứ tự input/output.
- Frontend chỉ gọi batch khi currency khác USD và catalog không rỗng; USD, currency trống và catalog rỗng vẫn không phát sinh Currency RPC.
- Frontend kiểm tra response cardinality trước khi gán price vào product để không trả catalog bị lệch giá.

Đã xác nhận trên môi trường Kubernetes với images triển khai mới: Browse EUR trả đủ 10 products, toàn bộ giá là EUR và có cùng thứ tự product IDs với Browse USD. Đây xác nhận BatchConvert chạy trên real Browse path; chưa có baseline/optimized sustained-load comparable nên chưa được kết luận mức cải thiện p95/p99.

### Câu hỏi cần xác nhận

- Browse p99 theo USD và non-USD khác nhau thế nào?
- Currency service request rate/error/latency có tăng tương quan với Browse p99 không?
- Currency rate có contract ổn định và exact-money semantics có thể dùng lại một cách an toàn không?
- Số product trên response list và page size có đủ để fan-out trở thành bottleneck thực tế không?

### Hướng xử lý cần đánh giá sau evidence

Chỉ cân nhắc giảm fan-out nếu rate freshness, rounding và exact-money behavior được chứng minh. Không dùng JavaScript floating-point hoặc arbitrary cache TTL. Nếu không có safe rate contract, ưu tiên bảo vệ downstream bằng concurrency limit thay vì tạo cache semantics mới.

## 4. Product route có request Recommendations không hợp lệ khi hydration

### Evidence hiện có

Product route có thời điểm `productId` chưa sẵn sàng trong client hydration, trong khi Recommendations query có thể được enable. Điều này có thể tạo request với identifier rỗng/`undefined` trước request hợp lệ.

Đây không phải Checkout bottleneck chính, nhưng là request thừa làm tăng load nền lên frontend/recommendation path và làm noise cho Browse metrics.

### Câu hỏi cần xác nhận

- Có request `productIds=undefined` trong frontend access logs/traces không?
- Response/error behavior của request này là gì?
- Tần suất theo page navigation và ảnh hưởng lên recommendation service ra sao?

### Hướng xử lý cần đánh giá sau evidence

Chỉ khởi tạo Recommendations query khi product identifier hợp lệ; đảm bảo normalization của input và cache/query key nhất quán để không leak stale recommendation giữa product routes.

## 5. Checkout USD path gọi Currency `Convert` theo từng item — đã xử lý ở PR #565

### Evidence hiện có

Trước PR [#565](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/565), `prepOrderItems` đã validate mọi product price là USD nhưng khi `userCurrency == "USD"` vẫn gọi unary `CurrencyService.Convert(price, "USD")` cho từng item. Multi-item Checkout do đó tạo N Currency RPC no-op; non-USD path đã dùng một `BatchConvert` cho toàn bộ prices.

### Đã triển khai

- USD item prices được copy bằng `copyMoney` sau validation, không gọi `Convert` hoặc `BatchConvert`.
- Vẫn giữ đúng một lần Currency `Convert` cho shipping cost.
- Non-USD item path vẫn dùng `CurrencyService.BatchConvert`, với validation response/cardinality/currency/money và checked money arithmetic.
- Regression coverage xác nhận Checkout USD multi-item giữ exact total, item ordering và currency code; không gọi `Convert`/`BatchConvert` cho item prices và chỉ gọi một `Convert` cho shipping.

Thay đổi chỉ giảm downstream RPC; Checkout response, email payload và Kafka order event tăng nhẹ display metadata cho mỗi item.

## 6. Product Catalog PostgreSQL connection pool quá lớn — đã xử lý ở PR #592

PR [#592](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/592) giới hạn connection pool của Product Catalog PostgreSQL:

- `MaxOpenConns`: 20.
- `MaxIdleConns`: 5.

Mục tiêu là bound concurrent database connection usage của Product Catalog, giảm khả năng downstream database bị quá tải mà không tăng cluster capacity hoặc replica minimum.

## Verification cho PR #565 và #592

Đã chạy thành công:

```text
go test -count=1 ./...
go vet ./...
go build ./...
npm run typecheck
git diff --check
```

Runtime steady state của PR #565 chỉ giảm downstream RPC:

- Confirmation giảm N Product Catalog `GetProduct` calls.
- USD Checkout item pricing giảm N Currency `Convert` calls.

## Prioritization sau implementation

| Priority | Vấn đề | Trạng thái / lý do |
|---|---|---|
| P0 | Two-worker Product Catalog reads trong Checkout | Regression đã xác minh; giữ tuần tự tại PR #558, không khôi phục fan-out |
| P1 | Confirmation hydration N+1 Product Catalog reads | Đã xử lý tại PR #565 bằng `product_display` additive và compatibility fallback |
| P2 | Checkout USD per-item Currency `Convert` | Đã xử lý tại PR #565 bằng validated `copyMoney`; shipping vẫn convert một lần |
| P2 | Browse Currency N+1 | Đã xử lý tại PR #324; vẫn cần baseline/optimized evidence về p95/p99 và correctness |
| P2 | Product Catalog PostgreSQL connection usage | Đã bound tại PR #592: open 20, idle 5 |
| P3 | Invalid Recommendations hydration request | Low-risk request elimination; tác động chính là giảm noise và load thừa |

## Acceptance trước khi giữ bất kỳ improvement nào

Một improvement chỉ được giữ khi baseline và optimized run dùng cùng sustained-load contract, p99 đạt improvement target đã chốt trước, p95 không regress, correctness/success rate/error rate không regress, và các resource invariants vẫn giữ nguyên. Nếu không đạt bất kỳ gate nào, optimized run là FAIL và thay đổi không được promote.
