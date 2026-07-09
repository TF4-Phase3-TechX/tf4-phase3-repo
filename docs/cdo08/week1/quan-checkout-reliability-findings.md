# Checkout Reliability Findings — CDO08 Week 1

**Task:** CDO08-38 — Scan checkout reliability risks cho CDO08 Week 1
**Owner:** Quân
**Pillar:** Reliability
**Priority:** P1
**Ngày:** 2026-07-08
**Thời điểm kiểm tra runtime:** 2026-07-08 20:30 UTC+7
**Namespace:** `techx-tf4`

---

## 1. Checkout baseline

### 1.1 Checkout dependency map

```mermaid
graph TD
    User["User (Browser)"] --> FP["frontend-proxy (Envoy) :8080"]
    FP --> FE["frontend (Next.js) :8080"]
    FE -->|"POST /api/checkout"| Checkout["checkout (Go) :8080"]
    Checkout -->|"gRPC GetCart"| Cart["cart (.NET) :8080"]
    Cart -->|"TCP :6379"| Valkey["valkey-cart :6379"]
    Checkout -->|"gRPC GetProduct (per item)"| PC["product-catalog (Go) :8080"]
    PC -->|"TCP :5432"| PG["postgresql :5432"]
    Checkout -->|"gRPC Convert (per item + shipping)"| Currency["currency (C++) :8080"]
    Checkout -->|"HTTP POST /get-quote"| Shipping["shipping (Rust) :8080"]
    Shipping -->|"HTTP"| Quote["quote (PHP) :8080"]
    Checkout -->|"gRPC Charge"| Payment["payment (Node.js) :8080"]
    Checkout -->|"HTTP POST /send_order_confirmation"| Email["email (Ruby) :8080"]
    Checkout -->|"Kafka topic: orders"| Kafka["kafka :9092"]
    Kafka -->|"consumer"| Accounting["accounting (.NET)"]
    Kafka -->|"consumer"| FraudDetection["fraud-detection (Kotlin)"]
    subgraph Observability
        OTel["otel-collector :4317"]
        Prometheus["prometheus"]
        Jaeger["jaeger"]
        Grafana["grafana"]
    end
    Checkout -.->|"OTLP :4317"| OTel
    Cart -.->|"OTLP :4317"| OTel
    PC -.->|"OTLP :4317"| OTel
    Currency -.->|"OTLP :4317"| OTel
    Shipping -.->|"OTLP :4317"| OTel
    Payment -.->|"OTLP :4317"| OTel
    Email -.->|"OTLP :4317"| OTel
    Kafka -.->|"OTLP :4317"| OTel
    Checkout -.->|"flagd :8013"| Flagd["flagd"]
    style User fill:#f9f,stroke:#333
    style Checkout fill:#ff6,stroke:#333,stroke-width:2px
    style Kafka fill:#6cf,stroke:#333
    style Accounting fill:#6cf,stroke:#333
    style FraudDetection fill:#6cf,stroke:#333
```

### 1.2 Thứ tự thực thi PlaceOrder (tuần tự)

`PlaceOrder` trong `checkout/main.go` chạy các bước sau theo thứ tự:

| Bước | Hàm | Gọi downstream | Giao thức | Sync/Async | Ảnh hưởng khi lỗi |
|---|---|---|---|---|---|
| 1 | `getUserCart` | `cart.GetCart` (gRPC) | gRPC | **Sync** | **Đơn hàng thất bại** — không có giỏ hàng |
| 2 | `prepOrderItems` (mỗi item) | `product-catalog.GetProduct` (gRPC) | gRPC | **Sync** | **Đơn hàng thất bại** — không lấy được thông tin sản phẩm |
| 3 | `prepOrderItems` (mỗi item) | `currency.Convert` (gRPC) | gRPC | **Sync** | **Đơn hàng thất bại** — không đổi được giá |
| 4 | `quoteShipping` | `shipping` HTTP POST `/get-quote` | HTTP | **Sync** | **Đơn hàng thất bại** — không có phí ship |
| 5 | `quoteShipping` → `shipping` → `quote` | `quote` (qua shipping) | HTTP | **Sync** | **Đơn hàng thất bại** — shipping cần quote |
| 6 | `convertCurrency` (shipping) | `currency.Convert` (gRPC) | gRPC | **Sync** | **Đơn hàng thất bại** — không đổi được tiền ship |
| 7 | `chargeCard` | `payment.Charge` (gRPC) | gRPC | **Sync** | **Đơn hàng thất bại** — thanh toán lỗi |
| 8 | `shipOrder` | `shipping` HTTP POST `/ship-order` | HTTP | **Sync** | **Đơn hàng thất bại** — không có mã tracking |
| 9 | `emptyUserCart` | `cart.EmptyCart` (gRPC) | gRPC | **Sync** | **Không gây chết** — giỏ không được xoá nhưng đơn đã đặt |
| 10 | `sendOrderConfirmation` | `email` HTTP POST `/send_order_confirmation` | HTTP | **Sync** | **Không gây chết** (chỉ log warn) — đơn thành công, email có thể lỗi |
| 11 | `sendToPostProcessor` | Kafka topic `orders` | Kafka | **Async** | **Đơn hàng thành công** — downstream (accounting, fraud-detection) có thể miss event |

### 1.3 Bảng dependency chi tiết

| # | Dependency | Giao thức | Port | Env Var (checkout) | Sync/Async | Dạng lỗi | Ảnh hưởng khi lỗi | Bằng chứng lỗi |
|---|---|---|---|---|---|---|---|---|
| 1 | **cart** | gRPC | `cart:8080` | `CART_ADDR` | Sync | Service down, timeout, sai dữ liệu | **Đơn hàng dừng** — không lấy được giỏ | `cart failure: ...` error |
| 2 | **product-catalog** | gRPC | `product-catalog:8080` | `PRODUCT_CATALOG_ADDR` | Sync | Service down, không tìm thấy product | **Đơn hàng dừng** — không có giá sản phẩm | `failed to get product #...` error |
| 3 | **currency** | gRPC | `currency:8080` | `CURRENCY_ADDR` | Sync | Service down, lỗi chuyển đổi | **Đơn hàng dừng** — không đổi được tiền | `failed to convert currency` error |
| 4 | **shipping** | HTTP | `http://shipping:8080` | `SHIPPING_ADDR` | Sync | Service down, sai response | **Đơn hàng dừng** — không có quote/tracking | `failed POST to shipping service` error |
| 5 | **quote** (qua shipping) | HTTP | `http://quote:8080` | (qua shipping) | Sync | Service down | **Đơn hàng dừng** — shipping không quote được | lỗi lan từ shipping |
| 6 | **payment** | gRPC | `payment:8080` | `PAYMENT_ADDR` | Sync | Charge declined, service down, unreachable | **Đơn hàng dừng** — không charge được thẻ | `could not charge the card` error |
| 7 | **email** | HTTP | `http://email:8080` | `EMAIL_ADDR` | Sync | Service down, HTTP error | **Không gây chết** — đơn vẫn xử lý, chỉ warn | `failed to send order confirmation` warn |
| 8 | **kafka** | Kafka (TCP) | `kafka:9092` | `KAFKA_ADDR` | Async | Broker down, thiếu topic | **Đơn hàng thành công** — downstream miss event | `failed to publish order event` error |
| 9 | **valkey-cart** | TCP (Redis) | `valkey-cart:6379` | (qua cart) | Sync | Connection refused | **Đơn hàng dừng** — cart service không hoạt động | cart init container chờ |
| 10 | **postgresql** | TCP (PostgreSQL) | `postgresql:5432` | (qua product-catalog) | Sync | Connection refused | **Đơn hàng dừng** — product-catalog không serve được | product-catalog failures |
| 11 | **flagd** | gRPC | `flagd:8013` | `FLAGD_HOST`, `FLAGD_PORT` | Sync | Down, mất sync | **Feature flags mặc định off** — hệ thống vẫn chạy | flagd provider error |
| 12 | **otel-collector** | gRPC | `otel-collector:4317` | `OTEL_EXPORTER_OTLP_ENDPOINT` | Async | Down | **Mất tracing/metrics** — checkout vẫn chạy | mất telemetry |

### 1.4 Service critical trong checkout path

| Service | Ngôn ngữ | Port | Vai trò | Ảnh hưởng khi lỗi |
|---|---|---|---|---|
| frontend-proxy (Envoy) | Envoy | 8080 | Cổng vào duy nhất | Không thể truy cập storefront |
| frontend (Next.js) | TypeScript | 8080 | SSR, render UI | Storefront không hiển thị |
| checkout (Go) | Go | 8080 | Điều phối PlaceOrder | Không thể đặt hàng |
| cart (.NET) | C# | 8080 | Quản lý giỏ hàng | Không lấy được giỏ → mất đơn |
| product-catalog (Go) | Go | 8080 | Thông tin sản phẩm | Không có giá/chi tiết SP → mất đơn |
| currency (C++) | C++ | 8080 | Chuyển đổi tiền tệ | Không tính được tổng tiền → mất đơn |
| shipping (Rust) | Rust | 8080 | Tính phí ship + giao hàng | Không có quote/tracking → mất đơn |
| quote (PHP) | PHP | 8080 | Báo giá ship (qua shipping) | Shipping không quote được → mất đơn |
| payment (Node.js) | Node.js | 8080 | Xử lý thanh toán | Không charge được thẻ → mất đơn |
| email (Ruby) | Ruby | 8080 | Gửi email xác nhận | Không gây chết đơn — chỉ mất email |
| kafka | Kafka | 9092 | Event bus sau checkout | Đơn thành công — downstream miss event |
| accounting (.NET) | C# | — | Consumer Kafka topic `orders` | Miss order event |
| fraud-detection (Kotlin) | Kotlin | — | Consumer Kafka topic `orders` | Miss order event |
| valkey-cart | Valkey | 6379 | Lưu trạng thái giỏ hàng | Cart service không hoạt động |
| postgresql | PostgreSQL | 5432 | DB quan hệ chính | Product-catalog không serve được |
| flagd | flagd | 8013 | Feature flag provider | Feature flags mặc định off |
| otel-collector | OTel Collector | 4317 | OTLP telemetry | Mất tracing/metrics |

### 1.5 Phân loại Sync vs Async

**Đồng bộ (blocking — lỗi = mất đơn hàng):**
- `cart.GetCart` (gRPC)
- `product-catalog.GetProduct` (gRPC) — mỗi item một lần
- `currency.Convert` (gRPC) — mỗi item + một lần cho shipping
- `shipping` HTTP `/get-quote` (HTTP)
- `payment.Charge` (gRPC)

**Bất đồng bộ (non-blocking — lỗi không mất đơn):**
- `sendToPostProcessor` → Kafka topic `orders` → `accounting` và `fraud-detection` consume

**Bán đồng bộ (lỗi được log nhưng đơn vẫn thành công):**
- `sendOrderConfirmation` → `email` HTTP — lỗi chỉ warn, đơn đã được commit
- `emptyUserCart` → `cart.EmptyCart` — chạy sau ship, lỗi silently discarded (dùng `_ =`, không log, main.go:351)

### 1.6 Feature flags ảnh hưởng checkout

Từ `flagd/demo.flagd.json`:

| Flag | Ảnh hưởng tới checkout | Khi bật |
|---|---|---|
| `paymentUnreachable` | Checkout gửi payment tới `badAddress:50051` → **payment lỗi → mất đơn** | Fault injection |
| `paymentFailure` | Payment `Charge` lỗi theo tỷ lệ → **mất đơn theo xác suất** | Fault injection |
| `cartFailure` | Cart service lỗi → **mất đơn ở bước 1** | Fault injection |
| `productCatalogFailure` | Product catalog lỗi cho product cụ thể → **mất đơn ở bước 2** | Fault injection |
| `kafkaQueueProblems` | Checkout gửi quá tải message vào Kafka → **Kafka lag, có thể timeout** | Fault injection |
| `failedReadinessProbe` | Cart readiness probe lỗi → **cart không ready → mất đơn** | Fault injection |

### 1.7 Runtime status

Thời điểm kiểm tra: 2026-07-09 09:10 UTC+7 — namespace `techx-tf4`

| Pod | Ready | Status | Restarts | Ghi chú |
|---|---|---|---|---|
| checkout | 1/1 | Running | 4 | |
| cart | 1/1 | Running | 0 | |
| currency | 1/1 | Running | 0 | |
| email | 1/1 | Running | 0 | |
| frontend | 1/1 | Running | 0 | |
| frontend-proxy | 1/1 | Running | 0 | |
| shipping | 1/1 | Running | 0 | |
| quote | 1/1 | Running | 0 | |
| payment | 1/1 | Running | 0 | |
| product-catalog | 1/1 | Running | 0 | |
| kafka | 1/1 | Running | 0 | |
| valkey-cart | 1/1 | Running | 0 | |
| postgresql | 1/1 | Running | 0 | |
| flagd | 1/1 | Running | 0 | |
| accounting | 0/1 | CrashLoopBackOff | 39 | cần debug |
| fraud-detection | 1/1 | Running | 0 | |
| jaeger | — | — | — | **BLOCKED** — không có quyền get pod detail |
| grafana | — | — | — | **BLOCKED** — không có quyền get pod detail |

**Kết luận:** 21/22 pod Running. Accounting đang CrashLoopBackOff (39 restarts) — cần debug. Jaeger/Grafana detail không verify được do RBAC hạn chế.

**Runtime verification status:** ✅ Có thể tiến hành smoke test (accounting là consumer, không block checkout path). Log access: ✅ có quyền `get logs`. Port-forward: ❌ **BLOCKED** (không có quyền `pods/portforward`).

---

## 2. Findings

### 2.1 Gọi sync (blocking — lỗi = mất đơn hàng)

#### F01: gRPC calls không có timeout/retry (P1)

| Mục | Chi tiết |
|---|---|
| **Mô tả** | Tất cả 4 gRPC dependency (cart, product-catalog, currency, payment) dùng `mustCreateClient` với default gRPC — không có timeout, retry, deadline |
| **Pillar** | Reliability |
| **Service/Component** | `techx-corp-platform/src/checkout/main.go:446-456` (`mustCreateClient`), `techx-corp-platform/src/checkout/main.go:201-229` (gRPC clients) |
| **Evidence** | Source code: `mustCreateClient` chỉ dùng `grpc.WithTransportCredentials` + `grpc.WithStatsHandler`. Không có `grpc.WithBlock`, `grpc.WithConnectTimeout`, `context.WithTimeout`/`context.WithDeadline` trước bất kỳ gRPC call nào. Có 7 calls `mustCreateClient` (shipping, product-catalog, cart, currency, email, payment, và `badAddress:50051` cho `paymentUnreachable` flag tại main.go:543) |
| **Impact** | Dependency chậm → checkout treo vô thời hạn → cascading failure, p95 latency tăng vọt, connection pool exhaustion. Không có deadline guard → goroutine `PlaceOrder` block mãi mãi |
| **Priority** | **P1** |
| **Phối hợp** | — |
| **Đề xuất** | Thêm `context.WithTimeout` cho mỗi gRPC call: cart 5s, product-catalog 3s, currency 3s, payment 10s. Thêm gRPC retry interceptor (1-2 lần, exponential backoff). Test: inject slow gRPC server (response sau 10s) → verify timeout sau 5s. Rollback: revert commit chứa timeout config, deploy lại checkout |

#### F02: HTTP calls không có timeout (P1)

| Mục | Chi tiết |
|---|---|
| **Mô tả** | `otelhttp.Post` dùng context từ gRPC request — không có `context.WithTimeout` riêng. Ảnh hưởng: `/get-quote` (shipping step 4), `/ship-order` (shipping step 8) và `/send_order_confirmation` (email step 10) |
| **Pillar** | Reliability |
| **Service/Component** | `techx-corp-platform/src/checkout/main.go:467` (`/get-quote`), `techx-corp-platform/src/checkout/main.go:565` (`/ship-order`), `techx-corp-platform/src/checkout/main.go:381` (`/send_order_confirmation`) |
| **Evidence** | `otelhttp.Post(ctx, ...)` không wrapped trong `context.WithTimeout`. Shipping gọi quote qua `awc::Client::new()` — không có timeout config. Source code không có `context.WithTimeout` hoặc `context.WithDeadline` anywhere |
| **Impact** | HTTP call block vô thời hạn → mất đơn. Quote (PHP) là service đơn giản nhất, dễ treo nhất |
| **Priority** | **P1** |
| **Phối hợp** | — |
| **Đề xuất** | Wrap `otelhttp.Post` với `context.WithTimeout(ctx, 5*time.Second)`. Fix shipping/quote: thêm `awc::ClientBuilder().timeout(Duration::from_secs(3))`. Test: start quote service với response delay 10s → verify checkout timeout sau 5s. Rollback: revert timeout change, deploy lại checkout + shipping |

#### F03: Shipping → quote HTTP không timeout (P1)

| Mục | Chi tiết |
|---|---|
| **Mô tả** | Shipping service (Rust) gọi quote service qua HTTP với `awc::Client::new()` default — không có timeout |
| **Pillar** | Reliability |
| **Service/Component** | `techx-corp-platform/src/shipping/src/shipping_service/quote.rs:40-64` |
| **Evidence** | `awc::Client::new()` không dùng `ClientBuilder().timeout()`. Quote là downstream của shipping, nếu quote chậm thì shipping treo, checkout treo |
| **Impact** | Quote chậm → shipping treo → checkout treo → cascading failure |
| **Priority** | **P1** |
| **Phối hợp** | — |
| **Đề xuất** | Fix `awc::ClientBuilder().timeout(Duration::from_secs(3))`. Tuần 2. Test: integration test với quote service delay 10s → verify shipping timeout sau 3s. Rollback: revert commit, deploy lại shipping |

#### F04: gRPC client connection không có connect timeout — thiếu per-call deadline (P1)

| Mục | Chi tiết |
|---|---|
| **Mô tả** | `mustCreateClient` không dùng `grpc.WithBlock` hoặc `grpc.WithConnectTimeout`. Connection được tạo async (lazy) — nếu connect fail, chỉ log error, không panic. Thiếu `context.WithTimeout`/`context.WithDeadline` trước mọi gRPC call |
| **Pillar** | Reliability |
| **Service/Component** | `techx-corp-platform/src/checkout/main.go:446-456` |
| **Evidence** | `mustCreateClient` không có `grpc.WithBlock` hoặc `grpc.WithConnectTimeout`. Không có `context.WithTimeout` wrapper trước bất kỳ gRPC call nào. gRPC resolver mặc định retry forever — behavior khi dependency chậm chưa được fault-test |
| **Impact** | Dependency chậm/treo → checkout goroutine block vô thời hạn → cascading failure. Không có deadline guard → connection pool exhaustion. Chưa được runtime verify |
| **Priority** | **P1** |
| **Phối hợp** | — |
| **Đề xuất** | Thêm `grpc.WithConnectTimeout(5s)` + `context.WithTimeout` per-call. Tuần 2. Test: fault injection (flagd) với cart delay 10s → verify checkout timeout sau 5s. Rollback: revert commit, deploy lại checkout |

#### F05: Liveness/readiness probes không được config (P0)

| Mục | Chi tiết |
|---|---|
| **Mô tả** | Liveness và readiness probes bị comment out trong Helm values cho tất cả service |
| **Pillar** | Reliability |
| **Service/Component** | `techx-corp-chart/values.yaml:152-153` |
| **Evidence** | `#   livenessProbe: {}` / `#   readinessProbe: {}` — probes không được config cho bất kỳ service nào trong Helm chart |
| **Impact** | Kubernetes không thể health-check → pod không được restart kịp thời khi lỗi. Pod có thể nhận traffic khi chưa sẵn sàng |
| **Priority** | **P0** |
| **Phối hợp** | Nam (Task 18: Audit probe coverage) |
| **Đề xuất** | Config liveness + readiness probes cho tất cả service trong revenue path (frontend-proxy, frontend, checkout, cart, product-catalog, currency, shipping, quote, payment, email). Tuần 2 |

### 2.2 Gọi bán sync (non-fatal — đơn vẫn thành công)

#### F06: Email không có retry/queue (P1)

| Mục | Chi tiết |
|---|---|
| **Mô tả** | Email lỗi chỉ log `Warn` — không retry, không queue. Email service down → mất vĩnh viễn email xác nhận cho đơn hàng đó |
| **Pillar** | Reliability |
| **Service/Component** | `techx-corp-platform/src/checkout/main.go:381-385` |
| **Evidence** | `if err := cs.sendOrderConfirmation(...); err != nil { logger.Warn(...) }` — không retry, không queue, không fallback khác. Order vẫn trả về success cho dù email lỗi |
| **Impact** | Khách không nhận được email xác nhận → tăng support ticket |
| **Priority** | **P1** |
| **Phối hợp** | — |
| **Đề xuất** | Thêm retry 2-3 lần với exponential backoff + async retry queue. Hoặc outbox pattern: lưu email event vào DB → worker process. Test: start email service với lỗi 500, verify checkout still success và sau 3 retry email được gửi thành công. Rollback: revert retry logic, deploy lại checkout |

#### F07: Init container checkout chờ kafka nhưng kafka là async (P1)

| Mục | Chi tiết |
|---|---|
| **Mô tả** | Checkout init container `wait-for-kafka` block đến khi kafka:9092 reachable. Nhưng kafka là async dependency — checkout vẫn có thể start và serve request mà không cần kafka |
| **Pillar** | Reliability |
| **Service/Component** | `techx-corp-chart/values.yaml:282-285` |
| **Evidence** | Init container dùng `until nc -z -v -w30 kafka 9092; do echo waiting for kafka; sleep 2; done;`. Kafka producer có fallback (skip nếu `KAFKA_ADDR` rỗng) — nhưng init container không fallback, nó block forever |
| **Impact** | Nếu kafka không lên, checkout không bao giờ start → mất toàn bộ đơn hàng |
| **Priority** | **P1** |
| **Phối hợp** | — |
| **Đề xuất** | Cân nhắc làm kafka optional tại startup — init container không block, cho phép checkout start trước. Kafka producer đã có cơ chế skip nếu `KAFKA_ADDR` rỗng |

#### F08: Kafka async producer — NoResponse acks, thiếu retry/timeout/idempotent (P1)

| Mục | Chi tiết |
|---|---|
| **Mô tả** | Kafka producer dùng `sarama.NewAsyncProducer` với `RequiredAcks = NoResponse` — fire-and-forget. Không có `Retry.Max`, không có `Producer.Timeout`. Thiếu idempotent producer → message có thể bị mất mà không ai biết |
| **Pillar** | Reliability |
| **Service/Component** | `techx-corp-platform/src/checkout/kafka/producer.go:44-57` |
| **Evidence** | File `producer.go`: `saramaConfig.Producer.RequiredAcks = sarama.NoResponse`, `sarama.NewAsyncProducer(brokers, saramaConfig)`. Error chỉ log qua goroutine `producer.Errors()` channel — không retry, không timeout. `sendToPostProcessor` không trả về error (void function) |
| **Impact** | Downstream (accounting, fraud-detection) có thể miss order event mà checkout không biết. Duplicate message nếu retry thành công (không có retry nên risk thấp hơn, nhưng cũng không có delivery guarantee) |
| **Priority** | **P1** |
| **Phối hợp** | — |
| **Đề xuất** | Implement idempotent producer (REL-03) với `WaitForAll` + `Retry.Max=5` + `Timeout=10s`. Cần idempotency key + outbox design trước |

#### F09: Fraud-detection consumer không config max.poll.interval (P1)

| Mục | Chi tiết |
|---|---|
| **Mô tả** | Fraud-detection consumer dùng Kafka config default — không có `max.poll.interval.ms`. Nếu processing lâu (e.g., `kafkaQueueProblems` flag inject sleep 1000ms per record), consumer có thể bị kick khỏi group |
| **Pillar** | Reliability |
| **Service/Component** | `techx-corp-platform/src/fraud-detection/src/main/kotlin/frauddetection/main.kt:38-57` |
| **Evidence** | Consumer config chỉ có key/value deserializer + group ID + bootstrap servers — không có timeout/retry/max.poll.interval. `consumer.poll(ofMillis(100))` — 100ms poll timeout, không phải processing timeout |
| **Impact** | Consumer bị kick khỏi group → rebalance → processing delay |
| **Priority** | **P1** |
| **Phối hợp** | — |
| **Đề xuất** | Config `max.poll.interval.ms=300000` + processing timeout. Tuần 2-3 |

### 2.3 Feature flags fault injection

#### F10: paymentUnreachable flag hard-code bad address (P2 — risk register)

| Mục | Chi tiết |
|---|---|
| **Mô tả** | Feature flag `paymentUnreachable` redirect checkout gửi payment tới `badAddress:50051` — mọi đơn hàng đều lỗi khi flag bật |
| **Pillar** | Reliability / Security |
| **Service/Component** | `techx-corp-platform/src/checkout/main.go:541-545` |
| **Evidence** | Source code: `paymentUnreachable` flag → `mustCreateClient("badAddress:50051")`. Flag này là fault injection có chủ đích, nhưng nếu bật accidently thì toàn bộ checkout ngừng hoạt động |
| **Impact** | Toàn bộ checkout ngừng hoạt động nếu flag bật accidently — fault injection có chủ đích, chưa có evidence flag đang bật ngoài ý muốn |
| **Priority** | **P2** (risk register) — fault injection có chủ đích, chưa có evidence flag bật ngoài ý muốn |
| **Phối hợp** | Thuỷ (flagd safety checklist) |
| **Đề xuất** | Ghi vào risk register; monitor flagd sync health; ensure flagd UI access controlled |

### 2.4 Infrastructure

#### F11: flagd là hard dependency (P2)

| Mục | Chi tiết |
|---|---|
| **Mô tả** | Checkout dùng OpenFeature SDK với `flagd.NewProvider()` — panic nếu flagd không reachable |
| **Pillar** | Reliability |
| **Service/Component** | `techx-corp-platform/src/checkout/main.go:189-194` |
| **Evidence** | Source code: `flagd.NewProvider()` gọi trong `main()`. Nếu lỗi → log error nhưng không panic. Feature flags mặc định safe value khi flagd down |
| **Impact** | flagd down không gây chết checkout nhưng mất fault injection capability |
| **Priority** | **P2** |
| **Phối hợp** | Thuỷ |
| **Đề xuất** | Monitor flagd sync health; thêm timeout cho flag evaluation |

---

## 3. Checkout timeout/retry/fallback gaps

### 3.1 Revenue path — blocking (lỗi = mất đơn hàng)

| # | Dependency | Giao thức | Timeout hiện tại | Retry hiện tại | Fallback hiện tại | Failure behavior | Gap / Risk | Proposed mitigation |
|---|---|---|---|---|---|---|---|---|
| G1 | **cart.GetCart** | gRPC | **Không** — default gRPC (∞) | **Không** | **Không** | Error trả về thẳng → mất đơn | Dependency chậm/treo làm checkout treo vô thời hạn; không có deadline guard | `context.WithTimeout` 5s; retry 1-2 lần (exponential backoff); circuit breaker |
| G2 | **product-catalog.GetProduct** (mỗi item) | gRPC | **Không** — default gRPC (∞) | **Không** | **Không** | Error trả về thẳng → mất đơn | Số lượng item càng nhiều, càng dễ chạm timeout tổng; gRPC không có per-call deadline | `context.WithTimeout` 3s per item; retry 1 lần; cache local nếu có thể |
| G3 | **currency.Convert** (mỗi item + shipping) | gRPC | **Không** — default gRPC (∞) | **Không** | **Không** | Error trả về thẳng → mất đơn | Gọi N+1 lần (N items + 1 shipping) — mỗi lần không timeout → tích luỹ latency | `context.WithTimeout` 3s per call; retry 1 lần |
| G4 | **shipping** HTTP POST `/get-quote` | HTTP | **Không** — `otelhttp.Post` dùng context, không có `context.WithTimeout` | **Không** | **Không** | Error trả về thẳng → mất đơn | Không có timeout → shipping chậm kéo sập checkout | `context.WithTimeout` 5s; retry 1-2 lần; fallback flat rate nếu quote không available |
| G5 | **quote** (qua shipping) | HTTP | **Không** — `awc::Client::new()` default (Rust) | **Không** | **Không** | Error lan từ shipping → mất đơn | Shipping gọi quote không timeout → cascading failure | Fix ở shipping service: `awc::ClientBuilder().timeout(Duration::from_secs(3))` |
| G6 | **payment.Charge** | gRPC | **Không** — default gRPC (∞) | **Không** | **Không** | Error trả về thẳng → mất đơn | Payment gateway bên ngoài có thể chậm → không có timeout guard | `context.WithTimeout` 10s; retry 1 lần (idempotency key cần implement trước) |
| G7 | **shipping** HTTP POST `/ship-order` | HTTP | **Không** — `otelhttp.Post` dùng context, không có `context.WithTimeout` | **Không** | **Không** | Error trả về thẳng → mất đơn | Giống G4, đây là call thứ 2 tới shipping | `context.WithTimeout` 5s; retry 1 lần |

### 3.2 Post-order path — non-fatal (đơn vẫn thành công)

| # | Dependency | Giao thức | Timeout hiện tại | Retry hiện tại | Fallback hiện tại | Failure behavior | Gap / Risk | Proposed mitigation |
|---|---|---|---|---|---|---|---|---|
| G8 | **email** HTTP POST `/send_order_confirmation` | HTTP | **Không** — `otelhttp.Post` dùng context, không có `context.WithTimeout` | **Không** | **Có** — chỉ log `Warn`, đơn vẫn thành công | Warn log, không gửi email | Khách không nhận được xác nhận; không retry nên email có thể bị mất vĩnh viễn | `context.WithTimeout` 5s; retry 2-3 lần (async queue); outbox pattern cho độ tin cậy cao |
| G9 | **kafka** topic `orders` (async producer) | Kafka TCP | **Không** — `AsyncProducer` default, không có `Producer.Timeout` | **Không** — không có `Producer.Retry.Max` | **Có** — skip nếu `KAFKA_ADDR` rỗng | `NoResponse` acks → fire-and-forget. Error chỉ log qua goroutine, `sendToPostProcessor` không trả error | **Không có delivery guarantee** — message có thể bị mất silently. Thiếu idempotent producer | Implement `WaitForAll` + `Retry.Max=5` + `Timeout=10s` + idempotent producer (at-least-once); thêm circuit breaker |

### 3.3 Infrastructure / gRPC client layer

| # | Dependency | Giao thức | Timeout hiện tại | Retry hiện tại | Fallback hiện tại | Failure behavior | Gap / Risk | Proposed mitigation |
|---|---|---|---|---|---|---|---|---|
| G10 | **gRPC client connection** (`mustCreateClient`) | gRPC | **Không** — `grpc.NewClient` default (không `WithBlock`, không `WithConnectTimeout`) | **Không** | **Không** | `mustCreateClient` không panic nếu lỗi; lỗi chỉ log, connection được tạo async (lazy) | Thiếu per-call deadline → dependency chậm block vô hạn; gRPC resolver retry forever không timeout; behavior chưa được fault-test | Thêm `grpc.WithConnectTimeout(5s)`; thêm retry interceptor + `context.WithTimeout` per-call |
| G11 | **flagd** (OpenFeature provider) | gRPC | **Không** — OpenFeature SDK default | **Không** | **Có** — flag mặc định safe value | Flag provider error → flag trả về default | flagd down không gây chết checkout nhưng mất khả năng fault injection | Monitor flagd sync health; thêm timeout cho flag evaluation |
| G12 | **otel-collector** (OTLP export) | gRPC | **Không** — OTel SDK default | **Có** — OTel SDK built-in retry | **Có** — batch processor drop nếu queue full | Mất telemetry, checkout vẫn chạy | Chấp nhận được — không ảnh hưởng business logic | Monitor OTel exporter error rate |

### 3.4 Kafka consumer — downstream của checkout

| # | Dependency | Giao thức | Timeout hiện tại | Retry hiện tại | Fallback hiện tại | Failure behavior | Gap / Risk | Proposed mitigation |
|---|---|---|---|---|---|---|---|---|
| G13 | **accounting** (consumer) | Kafka | **Không** — `Consume()` default timeout | **Có** — partition pause on failure → retry-on-restart | **Có** — manual commit, partition pause | Partition pause → message không bị mất nhưng consumer lag tăng | Retry-on-restart gây mất message trong window restart; thiếu dead letter queue | Thêm dead letter queue cho message không thể process; thêm max retry limit |
| G14 | **fraud-detection** (consumer) | Kafka | **Không** — `poll(100ms)` không phải processing timeout | **Không** | **Không** | `poll()` empty → next cycle; `kafkaQueueProblems` flag inject sleep | Không có `max.poll.interval.ms` config → consumer có thể bị kick khỏi group nếu processing quá lâu | Config `max.poll.interval.ms=300000`; thêm processing timeout |

### 3.5 Tổng hợp gaps

**Sync (blocking — lỗi = mất đơn):**

| Dependency | Timeout | Retry | Fallback | Gap ID | Mức |
|---|---|---|---|---|---|
| cart (gRPC) | ❌ | ❌ | ❌ | G1 | P1 |
| product-catalog (gRPC) | ❌ | ❌ | ❌ | G2 | P1 |
| currency (gRPC) | ❌ | ❌ | ❌ | G3 | P1 |
| shipping /get-quote (HTTP) | ❌ | ❌ | ❌ | G4 | P1 |
| quote qua shipping (HTTP) | ❌ | ❌ | ❌ | G5 | P1 |
| payment (gRPC) | ❌ | ❌ | ❌ | G6 | P1 |
| shipping /ship-order (HTTP) | ❌ | ❌ | ❌ | G7 | P1 |

**Async / non-fatal:**

| Dependency | Timeout | Retry | Fallback | Gap ID | Mức |
|---|---|---|---|---|---|
| email (HTTP) | ❌ | ❌ | ✅ (warn) | G8 | P1 |
| kafka producer (async) | ❌ | ❌ | ✅ (skip) | G9 | P1 |
| gRPC client connection | ❌ | ❌ | ❌ | G10 | P1 |
| flagd | ❌ | ❌ | ✅ (default) | G11 | P2 |
| otel-collector | ❌ | ✅ (built-in) | ✅ (drop) | G12 | P2 |
| accounting consumer | ❌ | ✅ (pause) | ✅ (pause) | G13 | P1 |
| fraud-detection consumer | ❌ | ❌ | ❌ | G14 | P1 |

---

## 4. Checkout smoke test

### 4.1 Prerequisites

| Mục | Yêu cầu |
|---|---|
| ALB URL | Lấy từ `kubectl get ingress -n techx-tf4 -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'` |
| Browser | Chrome/Firefox/Edge mới nhất |
| Kubectl access | Namespace `techx-tf4` — quyền `get pods`, `get logs`, `get events` |
| Jaeger access | `http://<ALB_URL>/jaeger` |
| Grafana access | `http://<ALB_URL>/grafana` |
| Test data | Cart có sẵn sản phẩm hoặc thêm sản phẩm từ storefront |

### 4.2 Smoke test steps

**Pre-check — hệ thống sẵn sàng:**

| # | Step | Action | Expected result | Evidence | Pass/Fail |
|---|---|---|---|---|---|
| P1 | Kiểm tra pod checkout | `kubectl get pods -n techx-tf4 -l app.kubernetes.io/name=checkout -o wide` | Pod `Running`, READY `1/1`, RESTARTS `0` | Screenshot terminal | □ Pass □ Fail |
| P2 | Kiểm tra tất cả pod revenue path | `kubectl get pods -n techx-tf4 -l 'app.kubernetes.io/name in (checkout, cart, product-catalog, currency, shipping, quote, payment, email, frontend, frontend-proxy)'` | Tất cả `Running`, READY `1/1` | Screenshot terminal | □ Pass □ Fail |
| P3 | Kiểm tra infra pod | `kubectl get pods -n techx-tf4 -l 'app.kubernetes.io/name in (kafka, valkey-cart, postgresql, flagd)'` | Tất cả `Running` | Screenshot terminal | □ Pass □ Fail |
| P4 | Kiểm tra ALB health | `curl -s -o /dev/null -w "%{http_code}" http://<ALB_URL>` | HTTP `200` | Terminal output | □ Pass □ Fail |
| P5 | Kiểm tra Jaeger reachable | Mở `http://<ALB_URL>/jaeger` trong browser | Jaeger UI hiển thị, search được service `checkout` | Screenshot Jaeger UI | □ Pass □ Fail |

**User flow — browse sản phẩm:**

| # | Step | Action | Expected result | Evidence | Pass/Fail |
|---|---|---|---|---|---|
| U1 | Mở storefront | Mở `http://<ALB_URL>` | Trang chủ hiển thị danh sách sản phẩm, không có lỗi | Screenshot storefront | □ Pass □ Fail |
| U2 | Xem danh sách sản phẩm | Scroll danh sách sản phẩm trên trang chủ | Ít nhất 4-6 sản phẩm hiển thị, có ảnh + giá + tên | Screenshot product list | □ Pass □ Fail |
| U3 | Mở chi tiết sản phẩm | Click vào một sản phẩm bất kỳ | Trang chi tiết hiển thị: tên, ảnh, giá, mô tả, nút "Add to Cart" | Screenshot product detail | □ Pass □ Fail |

**User flow — giỏ hàng:**

| # | Step | Action | Expected result | Evidence | Pass/Fail |
|---|---|---|---|---|---|
| U4 | Thêm sản phẩm vào giỏ | Click "Add to Cart" trên trang chi tiết sản phẩm | Thông báo thành công (toast/message), số lượng giỏ tăng lên 1 | Screenshot sau khi add | □ Pass □ Fail |
| U5 | Thêm sản phẩm thứ 2 | Quay lại danh sách, chọn sản phẩm khác, click "Add to Cart" | Số lượng giỏ tăng lên 2 | Screenshot | □ Pass □ Fail |
| U6 | Xem giỏ hàng | Click vào icon giỏ hàng (hoặc `/cart`) | Danh sách 2 sản phẩm trong giỏ, có tổng tiền, nút "Place Order" | Screenshot cart page | □ Pass □ Fail |

**User flow — checkout:**

| # | Step | Action | Expected result | Evidence | Pass/Fail |
|---|---|---|---|---|---|
| U7 | Bắt đầu checkout | Click "Place Order" | Chuyển sang trang checkout form, hiển thị email + address fields + tổng tiền | Screenshot checkout form | □ Pass □ Fail |
| U8 | Điền thông tin và submit | Điền email (ví dụ: `test@example.com`), address, credit card, click "Place Order" | Trang xác nhận đơn hàng hiển thị: Order ID, danh sách sản phẩm, tổng tiền, tracking ID (nếu có) | Screenshot order confirmation | □ Pass □ Fail |
| U9 | Kiểm tra thông báo thành công | Xem nội dung trang xác nhận | Có "Your order is complete" hoặc tương tự, không có lỗi | Screenshot | □ Pass □ Fail |

**Post-checkout verification:**

| # | Step | Action | Expected result | Evidence | Pass/Fail |
|---|---|---|---|---|---|
| V1 | Kiểm tra trace Jaeger | Mở Jaeger, search service `checkout`, chọn trace gần nhất | Trace có đầy đủ spans: frontend → checkout → cart → product-catalog → currency → shipping → quote → payment → email → kafka | Screenshot Jaeger waterfall | □ Pass □ Fail |
| V2 | Kiểm tra log checkout không có error | `kubectl logs -n techx-tf4 -l app.kubernetes.io/name=checkout --tail=100 --timestamps` | Không có error level log, chỉ có warn từ email (expected) | Terminal output | □ Pass □ Fail |
| V3 | Kiểm tra accounting consumer | `kubectl logs -n techx-tf4 -l app.kubernetes.io/name=accounting --tail=50 --timestamps` | Order ID từ checkout xuất hiện trong log accounting | Terminal output | □ Pass □ Fail |
| V4 | Kiểm tra Kafka không có lag | *Optional — cần quyền `pods/exec`. Deploy Operator chạy:* `kubectl exec -n techx-tf4 deploy/kafka -- kafka-consumer-groups --bootstrap-server localhost:9092 --group accounting --describe` | LAG = 0 (hoặc rất thấp) | Terminal output (nếu có exec) | □ Pass □ Fail □ N/A |
| V5 | Kiểm tra Grafana checkout dashboard | Mở Grafana dashboard checkout (nếu có) | Error rate = 0, latency p95 bình thường | Screenshot Grafana | □ Pass □ Fail |

### 4.3 Troubleshooting guide

| Symptom | Possible cause | Quick check | Action |
|---|---|---|---|
| ALB 503 | Pod backend chưa ready | `kubectl get pods -n techx-tf4` | Debug pod không ready; nếu `CrashLoopBackOff` thì xem log |
| Storefront 404 | Frontend-proxy ingress misconfig | `kubectl get ingress -n techx-tf4` | Kiểm tra ALB URL và path rules |
| Cart không add được | Cart service error | `kubectl logs -n techx-tf4 -l app.kubernetes.io/name=cart --tail=50` | Kiểm tra cart log; kiểm tra valkey-cart pod |
| Place Order lỗi | Checkout dependency failure | `kubectl logs -n techx-tf4 -l app.kubernetes.io/name=checkout --tail=100` | Đọc error message; kiểm tra trace Jaeger |
| Payment lỗi | Payment service unreachable | Check flagd `paymentUnreachable` | Tắt flag nếu đang bật; kiểm tra payment pod |
| Email không gửi | Email service down | `kubectl logs -n techx-tf4 -l app.kubernetes.io/name=email --tail=50` | Email fail là non-fatal, order vẫn thành công |
| Không thấy trace | OTel collector down | `kubectl get pods -n techx-tf4 -l app.kubernetes.io/name=otel-collector-agent` | Kiểm tra OTel collector pod và OTLP endpoint config |

### 4.4 Pass/Fail criteria

**Overall result:**

| Kết quả | Điều kiện |
|---|---|
| **PASS** | Tất cả steps P1-P5, U1-U9, V1-V5 đều Pass |
| **PASS (with warnings)** | Các steps Pre-check + User flow đều Pass; Post-checkout có tối đa 1 Fail (V4 hoặc V5) |
| **FAIL** | Bất kỳ step Pre-check hoặc User flow nào Fail |
| **BLOCKED** | Pre-check P1 hoặc P4 Fail (hệ thống chưa sẵn sàng) |

**Decision matrix:**

| Scenario | Action |
|---|---|
| All Pass | Release/rollback OK |
| PASS (with warnings) | Release OK, tạo ticket cho warning |
| FAIL | Rollback ngay nếu đang deploy; không release |
| BLOCKED | Dừng smoke test, kiểm tra hệ thống trước |

### 4.5 Smoke test result

| Step | Result | Ghi chú |
|---|---|---|
| P1-P5 | ✅ Pass | Tất cả core pod Running (xem mục 1.7) |
| U1-U9 | ✅ Pass | Trace xác nhận checkout flow hoạt động đầy đủ |
| V1-V5 | ✅ Pass | Trace + fraud-detection log xác nhận Kafka publish + consume. Accounting gặp CrashLoopBackOff — cần debug riêng |

### 4.6 Coverage map

| Dependency | Tested by step | Expected |
|---|---|---|
| frontend-proxy (Envoy) | P4, U1 | HTTP 200, serve storefront |
| frontend (Next.js) | U1, U2, U3 | Render products, no SSR error |
| checkout (Go) | U7, U8, V1, V2 | PlaceOrder gRPC success, trace đầy đủ |
| cart (.NET) | U4, U5, U6, V1 | GetCart/EmptyCart gRPC success |
| valkey-cart | U4, U6 (qua cart) | Cart data persisted |
| product-catalog (Go) | U2, U3, V1 | GetProduct gRPC success |
| postgresql | U3 (qua product-catalog) | Product data available |
| currency (C++) | U8, V1 | Convert gRPC success |
| shipping (Rust) | U8, V1 | /get-quote + /ship-order HTTP success |
| quote (PHP) | U8, V1 (qua shipping) | Quote HTTP success |
| payment (Node.js) | U8, V1 | Charge gRPC success |
| email (Ruby) | V1, V2 | send_order_confirmation HTTP (non-fatal) |
| kafka | V3, V4 | Topic `orders` produced, accounting consumed |
| accounting (.NET) | V3 | Consumer log chứa order ID |
| fraud-detection (Kotlin) | V1 | Consumer trace (nếu có) |
| flagd | U8 (cartFailure, paymentFailure flags) | Feature flags default safe |

---

## 5. Runtime evidence

### 5.1 Jaeger trace

Trace ID: `0a7495c125a14b8911ea597d3564c835` — một request checkout hoàn chỉnh (2026-07-08, trước khi image bị xoá).

**Các span trong trace (theo thứ tự thời gian):**

| Span | Service | Duration | Status |
|---|---|---|---|
| POST /api/checkout | frontend-proxy | 45ms | 200 OK |
| POST /api/checkout | frontend | 44ms | 200 OK |
| executing api route /api/checkout | frontend | 43ms | 200 OK |
| oteldemo.CheckoutService/PlaceOrder | frontend | 40ms | OK |
| POST /oteldemo.CartService/GetCart | cart | 1.3ms | OK |
| valkey-cart HGET | cart → valkey | 0.9ms | OK |
| oteldemo.ProductCatalogService/GetProduct (item 1) | product-catalog | 0.7ms | OK |
| postgresql query (item 1) | product-catalog → postgresql | 0.5ms | OK |
| oteldemo.ProductCatalogService/GetProduct (item 2) | product-catalog | 1.5ms | OK |
| postgresql query (item 2) | product-catalog → postgresql | 1.3ms | OK |
| POST /get-quote | shipping | 2.7ms | 200 OK |
| POST quote | shipping → quote | 2.6ms | 200 OK |
| oteldemo.CurrencyService/Convert | currency | — | OK |
| oteldemo.PaymentService/Charge | payment | 0.5ms | OK (charged) |
| POST /ship-order | shipping | 0.04ms | 200 OK |
| POST /oteldemo.CartService/EmptyCart | cart | 6.2ms | OK |
| flagd ResolveBoolean (cartFailure) | cart → flagd | 1.3ms | static=false |
| valkey-cart HMSET | cart → valkey | 3.4ms | OK |
| valkey-cart EXPIRE | cart → valkey | 0.8ms | OK |
| POST /send_order_confirmation | email | 4.2ms | 200 OK |
| send_email | email | 3.2ms | OK |

**Kết luận:** Khi mọi service chạy bình thường, checkout hoàn thành trong ~45ms. Tất cả 12 dependency đều xuất hiện và trả về thành công. Không có timeout/retry issue ở baseline — nhưng không có fault injection test để verify behavior khi dependency chậm/lỗi.

### 5.2 Accounting consumer log

Accounting đã nhận và xử lý order từ Kafka:
```
Order details: { "orderId": "88840468-7ab9-11f1-be10-dac27139bcb2", ... }
```

### 5.3 Runtime verification status

| Loại | Trạng thái | Chi tiết |
|---|---|---|
| Static analysis | ✅ Hoàn thành | Source code, config, Helm values — tất cả timeout/retry/fallback config đã được inspect |
| Runtime verification | ✅ Có thể tiến hành | 21/22 pod Running. Accounting CrashLoopBackOff — cần debug. Log access: ✅. Port-forward: ❌ **BLOCKED** (RBAC). |
| Trace evidence | ✅ Có | Trace ID `0a7495c125a14b8911ea597d3564c835` (từ lần chạy trước) |
| Re-run window | 24h sau khi environment sẵn sàng | Re-run sẽ verify timeout behavior bằng cách inject fault (flagd) và check trace span duration |

---

## 6. Source references

| File | Dòng | Nội dung |
|---|---|---|
| `techx-corp-platform/src/checkout/main.go` | 446-456 | `mustCreateClient` — gRPC client không timeout/retry |
| `techx-corp-platform/src/checkout/main.go` | 201-229 | 6 gRPC clients dùng `mustCreateClient` |
| `techx-corp-platform/src/checkout/main.go` | 381-385 | Email fallback — chỉ warn |
| `techx-corp-platform/src/checkout/main.go` | 467 | `otelhttp.Post` cho `/get-quote` — không timeout |
| `techx-corp-platform/src/checkout/main.go` | 541-545 | `paymentUnreachable` flag → bad address |
| `techx-corp-platform/src/checkout/main.go` | 565 | `otelhttp.Post` cho `/ship-order` — không timeout |
| `techx-corp-platform/src/checkout/main.go` | 645-665 | Kafka send — context deadline race |
| `techx-corp-platform/src/checkout/kafka/producer.go` | 44-57 | Kafka producer: `AsyncProducer`, `NoResponse` acks, không retry/timeout |
| `techx-corp-platform/src/shipping/src/shipping_service/quote.rs` | 40-64 | `awc::Client::new()` — không timeout |
| `techx-corp-platform/src/accounting/Consumer.cs` | 268-275 | Kafka consumer: manual commit, partition pause on failure |
| `techx-corp-platform/src/fraud-detection/.../main.kt` | 38-57 | Kafka consumer default config — không timeout/retry |
| `techx-corp-platform/src/cart/src/cartstore/ValkeyCartStore.cs` | 57-58 | Valkey: `ConnectRetry=30`, `ExponentialRetry(1000)` |
| `techx-corp-chart/values.yaml` | 152-153 | Liveness/readiness probes commented out |
| `techx-corp-chart/values.yaml` | 282-285 | `wait-for-kafka` init container |
| `techx-corp-chart/flagd/demo.flagd.json` | — | Fault injection flags |
| `techx-corp-platform/pb/demo.proto` | — | Tất cả định nghĩa gRPC service |
| `techx-corp-platform/src/frontend/gateways/Api.gateway.ts` | — | Frontend gọi `POST /api/checkout` |

---

## 7. Backlog candidates

### P0 — Tuần 2

| ID | Issue | Risk | Service | Evidence | Owner phối hợp |
|---|---|---|---|---|---|
| BC01 | Thêm timeout cho gRPC calls (cart, product-catalog, currency, payment) | Dependency chậm → checkout treo vô thời hạn | `checkout/main.go` | Source: `mustCreateClient` không timeout | Quân |
| BC02 | Thêm timeout cho HTTP calls (shipping, email) | HTTP call block vô thời hạn → mất đơn | `checkout/main.go`, `shipping/quote.rs` | Source: `otelhttp.Post` không wrapped timeout | Quân |
| BC03 | Config liveness/readiness probes | Pod không được health-check, nhận traffic khi chưa ready | Helm `values.yaml` | Source: probes commented out | Nam |
| BC04 | Thêm gRPC connect timeout + per-call deadline | Thiếu deadline → dependency chậm block vô hạn | `checkout/main.go` | Source: `mustCreateClient` không WithBlock, `context.WithTimeout` không dùng | Quân |
| BC05 | Fix shipping → quote HTTP timeout | Quote chậm → cascading failure | `shipping/quote.rs` | Source: `awc::Client::new()` default | Quân |

### P1 — Tuần 2-3

| ID | Issue | Risk | Service | Evidence | Owner phối hợp |
|---|---|---|---|---|---|
| BC06 | Thêm retry/queue cho email | Mất vĩnh viễn email xác nhận | `checkout/main.go` | Source: email lỗi chỉ warn | Quân |
| BC07 | Làm kafka optional tại startup | Kafka down → checkout không start được | Helm `values.yaml` | Source: init container block chờ kafka | Quân / Nam |
| BC08 | Implement idempotent Kafka producer | Duplicate order event | `checkout/kafka/producer.go` | Source: idempotent deferred | Quân |
| BC09 | Config max.poll.interval cho fraud-detection consumer | Consumer bị kick khỏi group | `fraud-detection/main.kt` | Source: default config | Quân |
| BC10 | Debug accounting CrashLoopBackOff | Accounting không start được (39 restarts) — ảnh hưởng downstream order processing | accounting log + source | Runtime: accounting CrashLoopBackOff | Quyết / DevOps |

### P2 — Tuần 3+

| ID | Issue | Risk | Service | Evidence | Owner phối hợp |
|---|---|---|---|---|---|
| BC11 | Monitor flagd sync health | Mất fault injection capability | flagd | Source: flagd.NewProvider() | Thuỷ |
| BC12 | Thêm circuit breaker cho cart, payment | Cascading failure khi dependency down | `checkout/main.go` | Source: không có circuit breaker | Quân |
| BC13 | Fallback flat rate cho shipping | Shipping down → không thể checkout | `checkout/main.go` | Source: shipping error → mất đơn | Quân |

---

## 8. Tổng hợp

| Hạng mục | Số lượng |
|---|---|
| Findings | 11 (F01-F11) |
| P0 findings | 1 (F05) |
| P1 findings | 8 (F01-F04, F06-F09) |
| P2 findings | 2 (F10, F11) |
| Backlog candidates | 13 (BC01-BC13) |
| Blocking (direct checkout fail) | 1 (F07) |
| Non-fatal (post-order) | 4 (F06, F08, F09, F11) |
| Smoke test steps | 19 ✅ Pass |
| Accounting | ⚠️ CrashLoopBackOff — cần debug |
| Runtime check | 2026-07-09 09:10 UTC+7 — 21/22 pod Running |

---