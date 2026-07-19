# Các vấn đề Performance cần cải thiện

**Mục tiêu:** giảm p95/p99 của Browse → Cart → Checkout dưới cùng sustained-load contract, đồng thời giữ nguyên correctness, reliability và resource invariants.

Tài liệu này chỉ ghi nhận vấn đề, evidence và hướng điều tra. Solution design, target file và implementation detail sẽ được chốt sau khi có baseline chính thức ở 200 users và trace/metric tương ứng.

## Nguyên tắc không được vi phạm

Các improvement không được đổi latency lấy compute hoặc correctness:

- Không tăng worker node, node-hours, instance class hoặc cluster capacity.
- Không tăng HPA minimum replicas.
- Không tăng CPU/memory requests chỉ để cải thiện số đo.
- Không giảm load, rút ngắn measurement window hoặc thay endpoint mix giữa before/after.
- Không disable tracing, logging, flagd, retry hay validation để giảm latency.
- Browse, Cart và Checkout phải giữ kết quả đúng; error rate không được tăng.

## 1. Checkout preparation có khả năng tạo critical path tuần tự

### Evidence hiện có

Current Jaeger trace cho thấy `prepareOrderItemsAndShippingQuoteFromCart` mất **21.498 ms**, chiếm khoảng 59% selected `CheckoutService/PlaceOrder` span (**36.348 ms**). Trong phase này trace có Product Catalog, Currency và Quote dependency trước Payment.

Với multi-item cart, mỗi item cần product lookup và currency conversion. Nếu các call này xảy ra tuần tự, critical path sẽ tăng cùng số item và tail latency có thể tăng mạnh hơn khi downstream có jitter hoặc retry.

### Câu hỏi cần xác nhận trong baseline chính thức

- Multi-item Checkout có p95/p99 cao hơn single-item Checkout ở cùng user load không?
- Child span nào đóng góp lớn nhất tại p99: Product Catalog, Currency, Quote hay retry/backoff?
- Shipping quote có độc lập với item preparation không?
- Có downstream saturation, queue buildup, connection-pool pressure hoặc retry amplification trong sustained window không?

### Hướng xử lý cần đánh giá sau evidence

Đánh giá khả năng rút ngắn critical path bằng cách chỉ concurrent hóa các read operation thực sự độc lập. Nếu chọn approach này, cần bounded concurrency, preserve item ordering, giữ retry/deadline hiện hữu và cancel work đúng cách khi một dependency fail. Payment, shipping fulfillment, cart mutation và post-payment side effects phải tiếp tục có ordering correctness rõ ràng.

## 2. Checkout confirmation có dấu hiệu downstream work dư thừa

### Evidence hiện có

Checkout đã tính authoritative order cost trước payment. Sau đó confirmation response cần hydrate product display data; generic product hydration có thể kéo theo Currency work cho một price không phải dữ liệu được confirmation page dùng để hiển thị.

Điều này có thể tạo thêm Product Catalog/Currency dependency trên request path sau khi Checkout business flow đã hoàn thành phần cost calculation cần thiết.

### Câu hỏi cần xác nhận

- Confirmation page/consumer thực sự cần những field product nào?
- Có consumer nào phụ thuộc vào hydrated product price theo selected currency không?
- Bao nhiêu Product Catalog/Currency request được sinh thêm trên mỗi Checkout, đặc biệt ở multi-item cart?
- Work này xuất hiện trong client-observed Checkout latency hay sau response boundary?

### Hướng xử lý cần đánh giá sau evidence

Xác định response contract tối thiểu cho confirmation display và loại bỏ work không phục vụ consumer đó. Bất kỳ thay đổi nào cũng phải bảo toàn meaning của monetary fields: không được trả USD value dưới tên hoặc contract khiến caller hiểu là selected currency.

## 3. Browse catalog có N+1 Currency fan-out với non-USD

### Evidence hiện có

Browse catalog lấy danh sách product rồi thực hiện Currency conversion theo từng product khi selected currency không phải USD. Đây là N+1 downstream pattern: một list request sinh nhiều Currency RPC.

Ở tải thấp pattern có thể chưa lộ rõ. Dưới sustained load, fan-out làm tăng Currency request volume, contention và xác suất một slow call ảnh hưởng response tail.

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

## 5. Observability cần được dùng để chứng minh root cause, không chỉ show service latency

### Evidence hiện có

Jaeger, Grafana span metrics và Locust raw artifacts hiện đã available. Current trace đã chỉ ra Checkout preparation phase, nhưng chưa đủ để kết luận p99 root cause ở 200 users.

### Điều cần có trong baseline và optimized run

- Exact T0/T1 UTC; cùng window ở Locust, Grafana và Jaeger.
- Checkout traces gồm cả representative successful request và slow/error request nếu tồn tại.
- p50/p95/p99 riêng cho Browse, Cart, Checkout và storefront.
- Dependency request/error/latency cho Cart, Product Catalog, Currency, Quote, Payment, Shipping, Email và Kafka.
- CPU/memory usage, throttling, replica count, node count/node-hours, restart/OOM/Pending và relevant pool/queue signals.
- Request volume, success denominator và endpoint mix để chứng minh before/after comparable.

## Prioritization trước implementation

| Priority | Vấn đề | Lý do |
|---|---|---|
| P0 | Checkout preparation sequential path | Nằm trên selected critical path; khả năng tăng theo cart size và downstream jitter |
| P1 | Confirmation hydration work dư thừa | Có khả năng loại bỏ downstream work mà không đổi business result |
| P2 | Browse Currency N+1 | Có potential fan-out lớn, nhưng phụ thuộc money/rate semantics |
| P3 | Invalid Recommendations hydration request | Low-risk request elimination; tác động chính là giảm noise và load thừa |

## Acceptance trước khi giữ bất kỳ improvement nào

Một improvement chỉ được giữ khi baseline và optimized run dùng cùng sustained-load contract, p99 đạt improvement target đã chốt trước, p95 không regress, correctness/success rate/error rate không regress, và các resource invariants vẫn giữ nguyên. Nếu không đạt bất kỳ gate nào, optimized run là FAIL và thay đổi không được promote.
