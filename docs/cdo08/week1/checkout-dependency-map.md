# Checkout Dependency Map

**Task:** CDO08-10 — Map checkout request path và dependencies
**Owner:** Quân
**Pillar:** Reliability
**Priority:** P0
**Ngày:** 2026-07-08

---

## 1. Luồng request checkout

```mermaid
graph TD
    User["User (Browser)"] --> FP["frontend-proxy (Envoy) :8080"]
    FP --> FE["frontend (Next.js) :8080"]

    FE -->|"POST /api/checkout"| Checkout["checkout (Go) :8080"]

    Checkout -->|"gRPC GetCart"| Cart["cart (.NET) :8080"]
    Cart -->|"TCP :6379"| Valkey["valkey-cart :6379"]

    Checkout -->|"gRPC GetProduct<br/>(per item)"| PC["product-catalog (Go) :8080"]
    PC -->|"TCP :5432"| PG["postgresql :5432"]

    Checkout -->|"gRPC Convert<br/>(per item + shipping)"| Currency["currency (C++) :8080"]

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

---

## 2. Thứ tự thực thi PlaceOrder (tuần tự)

`PlaceOrder` trong `checkout/main.go` chạy các bước sau **theo thứ tự**:

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

---

## 3. Bảng dependency chi tiết

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

---

## 4. Phân loại Sync vs Async

### Đồng bộ (blocking — lỗi = mất đơn hàng)

Tất cả các gọi trong `PlaceOrder` trước `sendOrderConfirmation` đều **đồng bộ và blocking**. Nếu bất kỳ cái nào lỗi, toàn bộ đơn hàng bị từ chối:

- `cart.GetCart` (gRPC)
- `product-catalog.GetProduct` (gRPC) — mỗi item một lần
- `currency.Convert` (gRPC) — mỗi item + một lần cho shipping
- `shipping` HTTP `/get-quote` (HTTP)
- `payment.Charge` (gRPC)

### Bất đồng bộ (non-blocking — lỗi không mất đơn)

- `sendToPostProcessor` → Kafka topic `orders` → `accounting` và `fraud-detection` consume

### Bán đồng bộ (lỗi được log nhưng đơn vẫn thành công)

- `sendOrderConfirmation` → `email` HTTP — lỗi chỉ warn, **đơn đã được commit**
- `emptyUserCart` → `cart.EmptyCart` — chạy sau ship, lỗi được log

---

## 5. Điểm lỗi nguy hiểm nhất (Risk Assessment)

| Rủi ro | Bước ảnh hưởng | Tác động | Mức độ | Đề xuất giảm thiểu |
|---|---|---|---|---|
| **Cart service down** | Bước 1 | Không lấy được giỏ → mất đơn | **P0** | Thêm retry + circuit breaker; cân nhắc cart HA |
| **Product catalog down** | Bước 2 | Không lấy được thông tin SP → mất đơn | **P0** | Thêm retry; cân nhắc cache local cho sản phẩm phổ biến |
| **Currency service down** | Bước 3, 6 | Không đổi được tiền → mất đơn | **P0** | Thêm retry + timeout guard |
| **Shipping/quote down** | Bước 4, 5, 8 | Không có phí ship → mất đơn | **P0** | Thêm retry; cân nhắc fallback flat rate |
| **Payment service down** | Bước 7 | Không charge được thẻ → mất đơn | **P0** | Thêm retry; payment gateway timeout phải có giới hạn |
| **Email service down** | Bước 10 | Đơn thành công nhưng khách không nhận email | **P1** | Outbox pattern hoặc retry queue |
| **Kafka broker down** | Bước 11 | Đơn thành công nhưng accounting/fraud miss event | **P1** | Thêm retry + circuit breaker; cân nhắc outbox pattern |
| **flagd down** | Tất cả | Feature flags mặc định safe → hệ thống chạy nhưng mất fault injection | **P2** | flagd là dependency bắt buộc; monitor sync health |
| **Không có timeout/retry trên gRPC calls** | Bước 1-7 | Cascading failure nếu dependency chậm | **P0** | Audit timeout/retry config cho từng service call |

---

## 6. Chuỗi dependency tóm tắt

```
Frontend (HTTP POST /api/checkout)
  └── checkout (gRPC server :8080)
       ├── [SYNC] cart (gRPC) → valkey-cart (TCP :6379)
       ├── [SYNC] product-catalog (gRPC) → postgresql (TCP :5432)
       ├── [SYNC] currency (gRPC)
       ├── [SYNC] shipping (HTTP) → quote (HTTP)
       ├── [SYNC] payment (gRPC)
       ├── [SYNC] email (HTTP)       ← non-fatal
       └── [ASYNC] kafka (topic: orders)
            ├── accounting (consumer)
            └── fraud-detection (consumer)
```

**Luồng doanh thu quan trọng (lỗi = mất đơn):** `cart → product-catalog → currency → shipping/quote → payment`

**Luồng sau đặt hàng (đơn thành công nhưng ảnh hưởng downstream):** `email → kafka → accounting + fraud-detection`

---

## 7. Feature flags ảnh hưởng checkout

Từ `flagd/demo.flagd.json`:

| Flag | Ảnh hưởng tới checkout | Khi bật |
|---|---|---|
| `paymentUnreachable` | Checkout gửi payment tới `badAddress:50051` → **payment lỗi → mất đơn** | Fault injection |
| `paymentFailure` | Payment `Charge` lỗi theo tỷ lệ → **mất đơn theo xác suất** | Fault injection |
| `cartFailure` | Cart service lỗi → **mất đơn ở bước 1** | Fault injection |
| `productCatalogFailure` | Product catalog lỗi cho product cụ thể → **mất đơn ở bước 2** | Fault injection |
| `kafkaQueueProblems` | Checkout gửi quá tải message vào Kafka → **Kafka lag, có thể timeout** | Fault injection |
| `failedReadinessProbe` | Cart readiness probe lỗi → **cart không ready → mất đơn** | Fault injection |

---

## 8. Tham chiếu service port & protocol

| Service | Ngôn ngữ | Port | Giao thức | Ghi chú |
|---|---|---|---|---|
| frontend-proxy | Envoy | 8080 | HTTP/1.1 | Cổng vào duy nhất |
| frontend | TypeScript/Next.js | 8080 | HTTP/1.1 | Server-side rendering |
| checkout | Go | 8080 | gRPC | Điều phối đơn hàng |
| cart | C# (.NET) | 8080 | gRPC | Dùng valkey làm storage |
| product-catalog | Go | 8080 | gRPC | Dùng postgresql |
| currency | C++ | 8080 | gRPC | Stateless |
| shipping | Rust | 8080 | HTTP | Gọi quote bên trong |
| quote | PHP | 8080 | HTTP | Stateless |
| payment | Node.js | 8080 | gRPC | Stateless |
| email | Ruby | 8080 | HTTP | Stateless |
| kafka | Kafka | 9092 | Kafka TCP | Internal listener |
| accounting | C# (.NET) | - | Kafka consumer | Consume topic `orders` |
| fraud-detection | Kotlin | - | Kafka consumer | Consume topic `orders` |
| valkey-cart | Valkey | 6379 | Redis TCP | Lưu trạng thái giỏ hàng |
| postgresql | PostgreSQL | 5432 | PostgreSQL TCP | DB quan hệ chính |
| flagd | flagd | 8013 | gRPC | Feature flag provider |
| otel-collector | OTel Collector | 4317 | gRPC | OTLP telemetry |

---

## 9. Tham chiếu file nguồn

| File | Nội dung |
|---|---|
| `techx-corp-platform/src/checkout/main.go` | Luồng PlaceOrder đầy đủ, tất cả env var, gRPC/HTTP calls |
| `techx-corp-platform/src/checkout/kafka/producer.go` | Kafka topic `orders`, cấu hình producer |
| `techx-corp-chart/values.yaml` (dòng 246-285) | Env var checkout, port, init containers |
| `techx-corp-chart/values.yaml` (dòng 537-562) | Env var payment |
| `techx-corp-chart/values.yaml` (dòng 686-700) | Env var shipping (gọi quote) |
| `techx-corp-platform/pb/demo.proto` | Tất cả định nghĩa gRPC service |
| `techx-corp-platform/src/frontend/gateways/Api.gateway.ts` | Frontend gọi `POST /api/checkout` |
| `techx-corp-chart/flagd/demo.flagd.json` | Feature flags ảnh hưởng checkout |
| `docs/requirements/onboarding/ARCHITECTURE.md` | Tổng quan kiến trúc |

---

## 10. Tổng hợp findings

| # | Finding | Dependency | Rủi ro | Mức độ | Service/File ảnh hưởng | Bằng chứng | Follow-up đề xuất |
|---|---|---|---|---|---|---|---|
| F1 | Tất cả gRPC calls **không có timeout/retry tường minh** | cart, product-catalog, currency, payment | Dependency chậm làm cascading failure | **P0** | `checkout/main.go` dòng 446-456 (`mustCreateClient` dùng default gRPC) | Source code: không có `grpc.WithTimeout` hoặc retry interceptor | Task 11: Audit timeout/retry gaps |
| F2 | **payment** có feature flag `paymentUnreachable` hard-code `badAddress:50051` | payment | Nếu flag bật, mọi đơn hàng đều lỗi | **P0** | `checkout/main.go` dòng 541-545 | Source code: `paymentUnreachable` flag redirect tới bad address | Ghi vào risk register; monitor flagd |
| F3 | **email** lỗi chỉ **warn** — không retry, không queue | email | Khách không nhận được email xác nhận | **P1** | `checkout/main.go` dòng 381-384 | Source code: `log.Warn` khi lỗi, order vẫn trả về success | Thêm email retry hoặc outbox |
| F4 | Kafka producer dùng `WaitForAll` + 5 retries + 10s timeout | kafka | At-least-once semantics; downstream phải idempotent | **P1** | `checkout/kafka/producer.go` dòng 37-41 | Source code: config thể hiện at-least-once | Verify accounting/fraud-detection idempotency |
| F5 | **cart** init container chờ valkey-cart nhưng **không có readiness probe** | cart, valkey-cart | Pod có thể nhận traffic trước khi valkey sẵn sàng | **P0** | `values.yaml` dòng 240-244 (init container), `checkout/main.go` | Init container chờ nhưng cart không có readiness probe | Task 18: Audit probe coverage |
| F6 | **checkout** init container chờ kafka nhưng kafka là **async** | kafka | Nếu kafka không lên, checkout không bao giờ start | **P1** | `values.yaml` dòng 283-285 | Init container block đến khi kafka:9092 reachable | Cân nhắc làm kafka optional tại startup |
| F7 | **shipping** gọi **quote** qua HTTP không có timeout tường minh | shipping, quote | Cascading failure nếu quote chậm | **P0** | `shipping` source (Rust) | Quote là downstream dependency của shipping | Verify timeout trong shipping → quote call |
| F8 | **flagd** là hard dependency qua OpenFeature SDK | flagd | Nếu flagd down, feature flags mặc định off | **P2** | `checkout/main.go` dòng 189-194 | Source code: `flagd.NewProvider()` panic nếu lỗi | Monitor flagd sync health |

---

## 11. Hướng dẫn runtime verification (khi EKS sẵn sàng)

### Mục tiêu
Xác nhận luồng checkout thực tế bằng trace và log, bổ sung evidence vào file này.

### Điều kiện
- EKS cluster đang chạy, namespace `techx-tf4` có pod checkout và các dependency
- `kubectl` đã cấu hình đúng context
- frontend-proxy có thể truy cập được (port-forward hoặc load balancer)

### Các bước thực hiện

#### Bước 1: Kiểm tra pod checkout và dependency
```powershell
kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=checkout
kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=cart
kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=product-catalog
kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=payment
kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=shipping
kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=email
kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=kafka
```

#### Bước 2: Kiểm tra log checkout
```powershell
kubectl -n techx-tf4 logs -l app.kubernetes.io/component=checkout --tail=50
```

#### Bước 3: Đặt thử một đơn hàng
```powershell
# Port-forward frontend-proxy
kubectl -n techx-tf4 port-forward svc/frontend-proxy 8080:8080
```
Mở browser tại `http://localhost:8080` → chọn sản phẩm → thêm vào giỏ → checkout → điền thông tin → Place Order.

#### Bước 4: Xem trace trên Jaeger
```powershell
# Port-forward Jaeger
kubectl -n techx-tf4 port-forward svc/jaeger 16686:16686
```
Mở `http://localhost:16686` → chọn service `checkout` → tìm trace vừa tạo → chụp ảnh màn hình.

**Cần chụp:**
- Trace waterfall checkout: thấy tất cả span gọi tới cart, product-catalog, currency, shipping, payment, email, kafka
- Span chi tiết từng dependency (duration, status, error nếu có)

#### Bước 5: Kiểm tra Grafana dashboard
```powershell
kubectl -n techx-tf4 port-forward svc/grafana 3000:80
```
Mở `http://localhost:3000` → dashboard service health → kiểm tra checkout latency, error rate, request rate.

#### Bước 6: Cập nhật evidence vào file
Sau khi có trace screenshot, thêm vào section này:

```markdown
## 12. Runtime Verification Evidence

**Ngày chạy:** [ngày]
**Môi trường:** [cluster name]

### Trace screenshot
![Checkout trace - Jaeger](path/to/screenshot.png)

### Kết quả
- [ ] Tất cả dependency xuất hiện trong trace waterfall
- [ ] Order đặt thành công
- [ ] Email log hiển thị gửi thành công
- [ ] Kafka event published (kiểm tra accounting/fraud-detection log)

### Khác biệt so với static analysis
- [ ] Không có khác biệt
- [ ] Có khác biệt (ghi rõ): ...
```

### Nếu EKS chưa sẵn sàng
Task này hiện tại **BLOCKED-BY: TF4 deployment readiness**. Static analysis đã hoàn thành. Khi môi trường sẵn sàng, chạy lại runtime verification trong vòng 24h.

---

## 12. Hướng dẫn tạo follow-up tasks cho findings P0/P1 (Tuần 2-3)

### Quy tắc
Theo task description: "Nếu finding là P0/P1, tạo hoặc đề xuất task Tuần 2-3 có đủ: risk, fix, test, rollback, evidence, dependency CDO04/CDO07 nếu có."

### Danh sách findings cần tạo task

#### F1: Thiếu timeout/retry trên gRPC calls (P0)
- **Task đề xuất:** `[Checkout] Add gRPC timeout and retry interceptor`
- **Risk:** Dependency chậm làm cascading failure, mất đơn hàng
- **Fix:** Thêm `grpc.WithTimeout` và retry interceptor vào `mustCreateClient`
- **Test:** Unit test timeout behaviour; smoke test khi dependency chậm
- **Rollback:** Revert code, redeploy
- **Evidence:** `checkout/main.go` dòng 446-456
- **Dependency:** Không

#### F2: paymentUnreachable flag có thể kill mọi đơn hàng (P0)
- **Task đề xuất:** `[Checkout] Document paymentUnreachable flag risk and monitoring`
- **Risk:** Nếu BTC bật flag, mọi order fail
- **Fix:** Thêm alert khi flag `paymentUnreachable` được bật; document trong runbook
- **Test:** Kích hoạt flag → verify order fail → tắt → verify order OK
- **Rollback:** Tắt flag
- **Evidence:** `checkout/main.go` dòng 541-545, `demo.flagd.json`
- **Dependency:** Không

#### F3: Email lỗi không retry (P1)
- **Task đề xuất:** `[Checkout] Add email notification retry mechanism`
- **Risk:** Khách đặt hàng thành công nhưng không nhận email xác nhận
- **Fix:** Thêm retry queue hoặc outbox pattern cho email
- **Test:** Tắt email service → đặt hàng → bật lại → verify email được gửi
- **Rollback:** Revert code, redeploy
- **Evidence:** `checkout/main.go` dòng 381-384
- **Dependency:** Có thể cần CDO04 nếu thêm queue ảnh hưởng cost

#### F5: Cart thiếu readiness probe (P0)
- **Task đề xuất:** `[Runtime] Add readiness probe for cart service`
- **Risk:** Cart nhận traffic trước khi valkey sẵn sàng → order fail
- **Fix:** Thêm readiness probe kiểm tra kết nối valkey-cart
- **Test:** Deploy → verify probe pass → kill valkey → verify probe fail
- **Rollback:** Revert Helm values, redeploy
- **Evidence:** `values.yaml` dòng 240-244
- **Dependency:** CDO04 nếu tăng resource cho probe

#### F7: Shipping → quote HTTP không có timeout (P0)
- **Task đề xuất:** `[Shipping] Add HTTP timeout for quote service call`
- **Risk:** Quote chậm → cascading failure → mất đơn
- **Fix:** Thêm HTTP client timeout trong shipping service
- **Test:** Mock quote chậm → verify timeout → verify fallback
- **Rollback:** Revert code, redeploy
- **Evidence:** `shipping` source (Rust)
- **Dependency:** Không

#### F6: Checkout init container chờ kafka (P1)
- **Task đề xuất:** `[Checkout] Make kafka dependency optional at startup`
- **Risk:** Kafka không lên → checkout không start được → mất đơn
- **Fix:** Bỏ init container chờ kafka; khởi tạo KafkaProducer async
- **Test:** Deploy không kafka → verify checkout start → verify order thành công (không có post-processing)
- **Rollback:** Revert Helm values, redeploy
- **Evidence:** `values.yaml` dòng 283-285
- **Dependency:** Không

#### F4: Verify accounting/fraud-detection idempotency (P1)
- **Task đề xuất:** `[Data] Verify Kafka consumer idempotency for accounting and fraud-detection`
- **Risk:** Kafka at-least-once → duplicate events → sai số liệu
- **Fix:** Verify consumer xử lý duplicate message đúng
- **Test:** Publish duplicate message → verify accounting/fraud chỉ ghi 1 lần
- **Rollback:** Không có thay đổi code
- **Evidence:** `checkout/kafka/producer.go` dòng 37-41
- **Dependency:** CDO07 (audit trail)

---

*Reviewed by: [chờ Nguyên review]*
*Status: Draft*