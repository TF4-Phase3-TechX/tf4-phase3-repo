# PERF-03: System Bottleneck Analysis & Recommendations

Tài liệu này phân tích chi tiết các điểm nghẽn hiệu năng (bottleneck) nghi ngờ trong kiến trúc hệ thống TechX Corp Platform và đề xuất giải pháp xử lý cụ thể cho từng hạng mục.

---

## 🚀 1. PERF-03.1: Phân tích N+1 Currency Conversion

### 🔍 Chi tiết vấn đề
Tại file [ProductCatalog.service.ts](file:///d:/Phase3_Xbrain/tf4-phase3-repo/techx-corp-platform/src/frontend/services/ProductCatalog.service.ts), hàm `listProducts` được triển khai như sau:
```typescript
  async listProducts(currencyCode = 'USD') {
    const { products: productList } = await ProductCatalogGateway.listProducts();

    return Promise.all(
      productList.map(async product => {
        const priceUsd = await this.getProductPrice(product.priceUsd!, currencyCode);

        return {
          ...product,
          priceUsd,
        };
      })
    );
  },
```
Khi người dùng chọn đơn vị tiền tệ khác USD (ví dụ: VND, EUR):
*   Hệ thống thực hiện vòng lặp qua danh sách sản phẩm (N sản phẩm).
*   Với mỗi sản phẩm, hàm `getProductPrice` gọi trực tiếp gRPC `CurrencyGateway.convert` để quy đổi giá.
*   **Hậu quả:** Phát sinh **N+1 cuộc gọi gRPC đồng thời** từ Frontend service sang `currency` service chỉ để lấy danh sách sản phẩm.

### 📉 Impact tới Browse Latency
*   **Độ trễ tích lũy (Latency Accumulation):** Mặc dù sử dụng `Promise.all` để chạy song song, việc mở hàng chục kết nối gRPC đồng thời tạo ra overhead lớn về TCP/gRPC connection, tăng tải CPU cho Frontend và Currency service.
*   **Rủi ro nghẽn cổ chai:** Nếu có 100 sản phẩm, 100 request gRPC sẽ oanh tạc `currency` service. Nếu chỉ cần 1 request gRPC bị chậm hoặc lỗi, toàn bộ trang chủ/danh sách sản phẩm sẽ bị chậm hoặc lỗi theo (All-or-Nothing failure).

### 📊 Metric cần đo
*   gRPC Client Latency của phương thức `/oteldemo.CurrencyService/Convert`.
*   Tần suất gọi gRPC (gRPC Request Rate) tới `currency` service trên mỗi request HTTP vào trang chủ.
*   Tỷ lệ lỗi (Error Rate) và p95/p99 latency của endpoint HTTP `/api/products`.

### 🛠️ Giải pháp đề xuất (Fix & Mitigation)
*   **Giải pháp tối ưu (Batching):** Bổ sung phương thức quy đổi hàng loạt vào API gRPC của `CurrencyService` (ví dụ: `ConvertPrices` nhận danh sách `Money` và quy đổi trong 1 gRPC call duy nhất).
*   **Giải pháp giảm thiểu (Caching):** Vì tỷ giá tiền tệ không biến động theo từng mili-giây, ta có thể lưu cấu hình tỷ giá (exchange rates) vào Valkey Cache hoặc lưu trực tiếp trên In-memory của Frontend service với TTL (ví dụ: 5 phút). Khi cần chuyển đổi giá, Frontend chỉ cần tự tính toán local thay vì gọi gRPC sang `currency`.

---

## 🔍 2. PERF-03.2: Phân tích Catalog Search Bottleneck

### 🔍 Chi tiết vấn đề
Tại file [main.go](file:///d:/Phase3_Xbrain/tf4-phase3-repo/techx-corp-platform/src/product-catalog/main.go) của `product-catalog` service, hàm tìm kiếm sản phẩm truy vấn database PostgreSQL như sau:
```go
	rows, err := db.QueryContext(ctx, `
		SELECT p.id, p.name, p.description, p.picture, 
		       p.price_currency_code, p.price_units, p.price_nanos, p.categories
		FROM catalog.products p
		WHERE LOWER(p.name) LIKE $1 OR LOWER(p.description) LIKE $1
		ORDER BY p.id
	`, searchPattern)
```
Trong đó, `searchPattern := "%" + strings.ToLower(query) + "%"`.

### ⚠️ Rủi ro Full Table Scan & Phân tích
*   **LIKE song phương (`%query%`):** Việc đặt ký tự đại diện `%` ở cả đầu và cuối chuỗi tìm kiếm khiến cho các chỉ mục B-Tree thông thường trên cột `name` hoặc `description` hoàn toàn vô dụng.
*   **Hàm LOWER():** Việc bọc cột trong hàm `LOWER(p.name)` ngăn cản PostgreSQL sử dụng chỉ mục thường trừ khi có Functional Index đặc thù.
*   **Thiếu LIMIT:** Câu lệnh truy vấn không giới hạn số lượng kết quả trả về (`LIMIT`). Nếu người dùng tìm kiếm ký tự phổ biến như `%a%`, PostgreSQL sẽ quét toàn bộ bảng và trả về hàng ngàn dòng, gây nghẽn RAM/Network khi serialize dữ liệu sang gRPC.
*   **Kết luận:** Hệ thống bắt buộc phải quét toàn bộ bảng sản phẩm (**Full Table Scan / Sequential Scan**) cho mỗi lượt tìm kiếm. Khi bảng sản phẩm tăng lên hàng triệu bản ghi, database sẽ bị quá tải CPU/IO và treo hệ thống.

### 📊 Metric cần đo sau deploy
*   Database Sequential Scan Count (`pg_stat_user_tables`).
*   Query Execution Time của câu lệnh tìm kiếm trong database.
*   Tải CPU và Disk Read I/O của PostgreSQL instance.

### 🛠️ Giải pháp đề xuất (Fix & Mitigation)
*   **Thêm LIMIT:** Bắt buộc bổ sung mệnh đề `LIMIT 20` hoặc `LIMIT 50` vào cuối câu lệnh SQL để chặn việc kéo quá nhiều dữ liệu lên memory.
*   **Sử dụng Trigram Index:** Cài đặt extension `pg_trgm` trong PostgreSQL và tạo chỉ mục GIN/GIST Trigram trên 2 cột tìm kiếm để tăng tốc tìm kiếm wildcard (`%query%`):
    ```sql
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    CREATE INDEX idx_products_name_trgm ON catalog.products USING gin (LOWER(name) gin_trgm_ops);
    ```
*   **Full-Text Search:** Nếu hệ thống mở rộng, chuyển sang dùng tính năng Full-Text Search (`tsvector`/`tsquery`) của PostgreSQL hoặc đồng bộ dữ liệu sang OpenSearch để tìm kiếm chuyên nghiệp.

---

## 🔗 3. PERF-03.3: Phân tích Checkout Sequential Dependency

### 🔍 Chi tiết vấn đề
Tại file [main.go](file:///d:/Phase3_Xbrain/tf4-phase3-repo/techx-corp-platform/src/checkout/main.go), hàm `PlaceOrder` thực hiện một chuỗi các cuộc gọi tuần tự (sequential synchronous calls) đến nhiều microservices khác nhau:
```go
// 1. Chuẩn bị thông tin giỏ hàng và phí ship (Gọi Cart và Shipping)
prep, err := cs.prepareOrderItemsAndShippingQuoteFromCart(ctx, req.UserId, req.UserCurrency, req.Address)

// 2. Thanh toán thẻ (Gọi Payment)
txID, err := cs.chargeCard(ctx, total, req.CreditCard)

// 3. Giao hàng (Gọi Shipping)
shippingTrackingID, err := cs.shipOrder(ctx, req.Address, prep.cartItems)

// 4. Xóa giỏ hàng (Gọi Cart)
_ = cs.emptyUserCart(ctx, req.UserId)

// 5. Gửi Email xác nhận (Gọi Email)
_ = cs.sendOrderConfirmation(ctx, req.Email, orderResult)

// 6. Gửi dữ liệu thống kê (Đẩy vào Kafka)
err := cs.sendToPostProcessor(ctx, orderResult)
```

### 📉 Phân tích Rủi ro Latency Cao & Lỗi Dây Chuyền
*   **Độ trễ tích lũy tuyến tính (Linear Latency Accumulation):**
    $$\text{Latency}_{\text{Checkout}} = \text{T}_{\text{Cart}} + \text{T}_{\text{ShippingQuote}} + \text{T}_{\text{Payment}} + \text{T}_{\text{ShipOrder}} + \text{T}_{\text{EmptyCart}} + \text{T}_{\text{Email}} + \text{T}_{\text{Kafka}}$$
    Chỉ cần một dịch vụ trong chuỗi bị chậm (ví dụ: `payment` mất 2s phản hồi), toàn bộ API checkout của khách hàng sẽ bị treo, tăng nguy cơ timeout phía Client.
*   **Lỗi dây chuyền & Thiếu Idempotency (Cascading Failure):** Nếu bước 2 (Thanh toán) đã trừ tiền thành công nhưng bước 3 (Giao hàng) hoặc bước 6 (Đẩy sự kiện vào Kafka) bị lỗi, đơn hàng sẽ thất bại nhưng khách hàng vẫn bị trừ tiền. Hệ thống hiện chưa có cơ chế bù trừ giao dịch (Saga/Compensation) hoặc Idempotency Key để Client retry an toàn.

### 📊 Metric cần đo
*   Thời gian xử lý gRPC phương thức `/oteldemo.CheckoutService/PlaceOrder`.
*   Thời gian phản hồi riêng lẻ của các downstream gRPC calls (`PaymentService`, `ShippingService`, `CartService`).
*   Tần suất xảy ra lỗi nửa chừng (Thanh toán thành công nhưng không ship được hàng hoặc mất message Kafka).

### 🛠️ Giải pháp đề xuất (Fix & Mitigation)
*   **Thiết lập Timeout & Retry Budget:** Áp dụng Client-side Timeout nghiêm ngặt cho mỗi downstream call (ví dụ: tối đa 1.5s cho `payment`, 1s cho `shipping`). Nếu quá hạn, trả lỗi sớm thay vì treo kết nối.
*   **Xử lý Bất đồng bộ (Asynchronous Processing):**
    *   Các tác vụ không chặn luồng thanh toán chính như **Xóa giỏ hàng (Empty Cart)** và **Gửi Email xác nhận (Email Service)** nên được đẩy vào hàng đợi xử lý ngầm (Go goroutine/Worker) thay vì gọi tuần tự đồng bộ.
*   **Idempotency & Outbox Pattern:**
    *   Bắt buộc yêu cầu Client gửi kèm `Idempotency-Key` khi thực hiện checkout để tránh thanh toán trùng lặp khi retry do timeout.
    *   Sử dụng Transactional Outbox Pattern để lưu sự kiện đơn hàng vào database cục bộ trước, sau đó một worker phụ trách đẩy sang Kafka bất đồng bộ để tránh làm chậm luồng checkout khi Kafka gặp sự cố.

---

## 📊 4. PERF-03.4: Bảng Tổng hợp Bottleneck Analysis & Khuyến nghị

| Tên Bottleneck | Thành phần bị ảnh hưởng | Mức độ ảnh hưởng (Impact) | Bằng chứng đo lường cần có | Khuyến nghị cho Week 1 Pitch | Định hướng xử lý trong Week 2 |
|---|---|---|---|---|---|
| **N+1 Currency Conversion** | `frontend`, `currency` | **Medium** (Tăng browse latency & quá tải gRPC) | Traces trên Jaeger cho thấy N nhát `/oteldemo.CurrencyService/Convert` chạy song song cho 1 request trang chủ. | Báo cáo kiến trúc lỗi và đề xuất cache tỷ giá in-memory tại Frontend để chặn gọi gRPC thừa. | Triển khai Redis/Valkey Cache cho Exchange Rates hoặc tối ưu hóa gRPC API sang dạng Batch. |
| **Catalog Search Full Scan** | `product-catalog`, `postgresql` | **High** (Gây nghẽn CPU/Disk IO database) | Câu lệnh SQL chứa `LOWER()` + `LIKE %...%` không sử dụng index; không có `LIMIT`. | Thêm mệnh đề `LIMIT 20` vào code Go để giới hạn dữ liệu load lên RAM. | Tạo chỉ mục Trigram GIN index trên PostgreSQL hoặc chuyển sang dùng OpenSearch. |
| **Checkout Sequential Sync** | `checkout`, `payment`, `shipping`, `cart`, `email` | **High** (Tăng tỷ lệ rớt đơn hàng, treo API) | Traces trên Jaeger hiển thị các thanh Span gRPC nối đuôi nhau dài dặc. | Thiết lập strict timeout budget cho từng dịch vụ gọi ngoài; đẩy luồng gửi email và empty cart chạy ngầm. | Áp dụng Idempotency Key cho Payment và chuyển đổi luồng gửi thông báo đơn hàng sang Event-Driven (Kafka). |
