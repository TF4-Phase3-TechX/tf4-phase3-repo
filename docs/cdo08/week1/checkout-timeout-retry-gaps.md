# Checkout Timeout, Retry & Fallback Gaps

**Task:** CDO08-11 — Xác định timeout và retry gaps của checkout
**Owner:** Quân
**Pillar:** Reliability
**Priority:** P0
**Ngày:** 2026-07-08

---

## 1. Tổng quan

**Mục tiêu:** Với mỗi dependency trong checkout revenue path, ghi timeout hiện tại, retry hiện tại, fallback hiện tại, failure behavior, và proposed mitigation.

**Phạm vi kiểm tra:**
- Static analysis: source code checkout, kafka producer, Helm values, proto definitions
- Runtime verification: **BLOCKED** — EKS role `TF4-SecReliabilityReadOnlyAudit` không có quyền `get pods`/`get logs` trên namespace `techx-corp` (xem `evidence/map-checkout-and-request-path.md` cho trace từ lần trước)

---

## 2. Gap table

### 2.1 Revenue path — blocking (lỗi = mất đơn hàng)

| # | Dependency | Giao thức | Timeout hiện tại | Retry hiện tại | Fallback hiện tại | Failure behavior | Gap / Risk | Proposed mitigation |
|---|---|---|---|---|---|---|---|---|
| G1 | **cart.GetCart** | gRPC | **Không** — default gRPC (∞) | **Không** | **Không** | Error trả về thẳng → mất đơn | Dependency chậm/treo làm checkout treo vô thời hạn; không có deadline guard | `context.WithTimeout` 5s; retry 1-2 lần (exponential backoff); circuit breaker |
| G2 | **product-catalog.GetProduct** (mỗi item) | gRPC | **Không** — default gRPC (∞) | **Không** | **Không** | Error trả về thẳng → mất đơn | Số lượng item càng nhiều, càng dễ chạm timeout tổng; gRPC không có per-call deadline | `context.WithTimeout` 3s per item; retry 1 lần; cache local nếu có thể |
| G3 | **currency.Convert** (mỗi item + shipping) | gRPC | **Không** — default gRPC (∞) | **Không** | **Không** | Error trả về thẳng → mất đơn | Gọi N+1 lần (N items + 1 shipping) — mỗi lần không timeout → tích luỹ latency | `context.WithTimeout` 3s per call; retry 1 lần |
| G4 | **shipping** HTTP POST `/get-quote` | HTTP | **Không** — `otelhttp.Post` dùng context, không có `context.WithTimeout` | **Không** | **Không** | Error trả về thẳng → mất đơn | Không có timeout → shipping chậm kéo sập checkout | `context.WithTimeout` 5s; retry 1-2 lần; fallback flat rate nếu quote không available |
| G5 | **quote** (qua shipping) | HTTP | **Không** — `awc::Client::new()` default (Rust) | **Không** | **Không** | Error lan từ shipping → mất đơn | Shipping gọi quote không timeout → cascading failure | Fix ở shipping service: `awc::ClientBuilder().timeout(Duration::from_secs(3))` |
| G6 | **payment.Charge** | gRPC | **Không** — default gRPC (∞) | **Không** | **Không** | Error trả về thẳng → mất đơn | Payment gateway bên ngoài có thể chậm → không có timeout guard | `context.WithTimeout` 10s; retry 1 lần (idempotency key cần implement trước) |
| G7 | **shipping** HTTP POST `/ship-order` | HTTP | **Không** — `otelhttp.Post` dùng context, không có `context.WithTimeout` | **Không** | **Không** | Error trả về thẳng → mất đơn | Giống G4, đây là call thứ 2 tới shipping | `context.WithTimeout` 5s; retry 1 lần |

### 2.2 Post-order path — non-fatal (đơn vẫn thành công)

| # | Dependency | Giao thức | Timeout hiện tại | Retry hiện tại | Fallback hiện tại | Failure behavior | Gap / Risk | Proposed mitigation |
|---|---|---|---|---|---|---|---|---|
| G8 | **email** HTTP POST `/send_order_confirmation` | HTTP | **Không** — `otelhttp.Post` dùng context, không có `context.WithTimeout` | **Không** | **Có** — chỉ log `Warn`, đơn vẫn thành công | Warn log, không gửi email | Khách không nhận được xác nhận; không retry nên email có thể bị mất vĩnh viễn | `context.WithTimeout` 5s; retry 2-3 lần (async queue); outbox pattern cho độ tin cậy cao |
| G9 | **kafka** topic `orders` (async producer) | Kafka TCP | **Có** — `Producer.Timeout = 10s` | **Có** — `Producer.Retry.Max = 5` | **Có** — skip nếu `KAFKA_ADDR` rỗng | Error trả về từ `SendMessage`, đơn vẫn thành công | Retry 5 lần + timeout 10s là reasonable; nhưng thiếu idempotent producer (at-least-once) | Implement idempotent producer (REL-03); thêm circuit breaker nếu broker down kéo dài |

### 2.3 Infrastructure / gRPC client layer

| # | Dependency | Giao thức | Timeout hiện tại | Retry hiện tại | Fallback hiện tại | Failure behavior | Gap / Risk | Proposed mitigation |
|---|---|---|---|---|---|---|---|---|
| G10 | **gRPC client connection** (`mustCreateClient`) | gRPC | **Không** — `grpc.NewClient` default (không `WithBlock`, không `WithConnectTimeout`) | **Không** | **Không** | `mustCreateClient` không panic nếu lỗi; lỗi chỉ log, connection có thể nil | Gọi RPC trên connection lỗi → panic; gRPC resolver mặc định retry forever nhưng không có timeout | Thêm `grpc.WithConnectTimeout(5s)`; thêm retry interceptor hoặc `grpc.WithDefaultCallOptions(grpc.MaxCallRecvMsgSize(...))` |
| G11 | **flagd** (OpenFeature provider) | gRPC | **Không** — OpenFeature SDK default | **Không** | **Có** — flag mặc định safe value | Flag provider error → flag trả về default | flagd down không gây chết checkout nhưng mất khả năng fault injection | Monitor flagd sync health; thêm timeout cho flag evaluation |
| G12 | **otel-collector** (OTLP export) | gRPC | **Không** — OTel SDK default | **Có** — OTel SDK built-in retry | **Có** — batch processor drop nếu queue full | Mất telemetry, checkout vẫn chạy | Chấp nhận được — không ảnh hưởng business logic | Monitor OTel exporter error rate |

### 2.4 Kafka consumer — downstream của checkout

| # | Dependency | Giao thức | Timeout hiện tại | Retry hiện tại | Fallback hiện tại | Failure behavior | Gap / Risk | Proposed mitigation |
|---|---|---|---|---|---|---|---|---|
| G13 | **accounting** (consumer) | Kafka | **Không** — `Consume()` default timeout | **Có** — partition pause on failure → retry-on-restart | **Có** — manual commit, partition pause | Partition pause → message không bị mất nhưng consumer lag tăng | Retry-on-restart gây mất message trong window restart; thiếu dead letter queue | Thêm dead letter queue cho message không thể process; thêm max retry limit |
| G14 | **fraud-detection** (consumer) | Kafka | **Không** — `poll(100ms)` không phải processing timeout | **Không** | **Không** | `poll()` empty → next cycle; `kafkaQueueProblems` flag inject sleep | Không có `max.poll.interval.ms` config → consumer có thể bị kick khỏi group nếu processing quá lâu | Config `max.poll.interval.ms=300000`; thêm processing timeout |

---

## 3. Top 3 gaps prioritized

### P0-G1: gRPC calls không có timeout (cart, product-catalog, currency, payment)

| Mục | Mô tả |
|---|---|
| **Risk** | Tất cả 4 gRPC dependency trong revenue path đều dùng `mustCreateClient` với default gRPC — không có timeout, không có retry, không có deadline. Nếu bất kỳ service nào chậm hoặc treo, toàn bộ goroutine `PlaceOrder` bị block vô thời hạn → p95 latency tăng vọt, connection pool exhaustion, cascading failure. |
| **Affected service/file** | `checkout/main.go:446-456` (`mustCreateClient`), `checkout/main.go:201-229` (6 gRPC clients) |
| **Evidence** | `mustCreateClient` chỉ dùng `grpc.WithTransportCredentials` + `grpc.WithStatsHandler` — không có `grpc.WithBlock`, `grpc.WithConnectTimeout`, hoặc call option timeout. Source code không có `context.WithTimeout`/`context.WithDeadline` trước bất kỳ gRPC call nào. |
| **Proposed follow-up** | Tuần 2: Implement `context.WithTimeout` cho mỗi gRPC call: cart 5s, product-catalog 3s, currency 3s, payment 10s. Thêm gRPC retry interceptor (1-2 lần, exponential backoff). |
| **Test idea** | Unit test: inject slow gRPC server (response sau 10s) → verify timeout sau 5s. Integration test: dùng flagd fault injection `paymentUnreachable` → verify `context.WithTimeout` trả về `DeadlineExceeded`. |
| **Rollback idea** | Revert commit chứa timeout config; deploy lại checkout. |
| **Priority** | **P0** |

### P0-G4/G7: HTTP calls không có timeout (shipping /get-quote, /ship-order)

| Mục | Mô tả |
|---|---|
| **Risk** | `otelhttp.Post` dùng context từ gRPC request — không có `context.WithTimeout` riêng. Nếu shipping hoặc quote chậm, HTTP call block vô thời hạn. Quote (PHP) là service đơn giản nhất, dễ treo nhất. |
| **Affected service/file** | `checkout/main.go:467` (`/get-quote`), `checkout/main.go:565` (`/ship-order`), `shipping/src/shipping_service/quote.rs:40-64` (`awc::Client` default) |
| **Evidence** | `otelhttp.Post(ctx, ...)` không wrapped trong `context.WithTimeout`. Shipping gọi quote qua `awc::Client::new()` — không có timeout config (Rust `awc::ClientBuilder::timeout` chưa dùng). |
| **Proposed follow-up** | Tuần 2: Wrap `otelhttp.Post` với `context.WithTimeout(ctx, 5*time.Second)`. Fix shipping/quote: thêm `awc::ClientBuilder().timeout(Duration::from_secs(3))`. |
| **Test idea** | Integration test: start quote service với response delay 10s → verify checkout timeout sau 5s. |
| **Rollback idea** | Revert timeout change; deploy lại checkout + shipping. |
| **Priority** | **P0** |

### P1-G8: Email không có retry

| Mục | Mô tả |
|---|---|
| **Risk** | Email lỗi chỉ log `Warn` — không retry, không queue. Email service down đồng nghĩa với mất vĩnh viễn email xác nhận cho đơn hàng đó. Khách hàng không nhận được xác nhận → tăng support ticket. |
| **Affected service/file** | `checkout/main.go:381-385` |
| **Evidence** | `if err := cs.sendOrderConfirmation(...); err != nil { logger.Warn(...) }` — không retry, không queue, không fallback khác. |
| **Proposed follow-up** | Tuần 2-3: Thêm retry 2-3 lần với exponential backoff + async retry queue. Hoặc implement outbox pattern: lưu email event vào DB → worker process. |
| **Test idea** | Integration test: start email service với lỗi 500, verify checkout still success và sau 3 retry email được gửi thành công. |
| **Rollback idea** | Revert retry logic; deploy lại checkout. |
| **Priority** | **P1** |

---

## 4. Source references

| File | Dòng | Nội dung |
|---|---|---|
| `techx-corp-platform/src/checkout/main.go` | 446-456 | `mustCreateClient` — gRPC client không timeout/retry |
| `techx-corp-platform/src/checkout/main.go` | 201-229 | 6 gRPC clients dùng `mustCreateClient` |
| `techx-corp-platform/src/checkout/main.go` | 381-385 | Email fallback — chỉ warn |
| `techx-corp-platform/src/checkout/main.go` | 467 | `otelhttp.Post` cho `/get-quote` — không timeout |
| `techx-corp-platform/src/checkout/main.go` | 565 | `otelhttp.Post` cho `/send_order_confirmation` — không timeout |
| `techx-corp-platform/src/checkout/main.go` | 645-665 | Kafka send — context deadline race (chỉ có) |
| `techx-corp-platform/src/checkout/kafka/producer.go` | 36-43 | Kafka producer config: `Retry.Max=5`, `Timeout=10s`, `WaitForAll` |
| `techx-corp-platform/src/shipping/src/shipping_service/quote.rs` | 40-64 | `awc::Client::new()` — không timeout |
| `techx-corp-platform/src/accounting/Consumer.cs` | 268-275 | Kafka consumer: manual commit, partition pause on failure |
| `techx-corp-platform/src/fraud-detection/.../main.kt` | 38-57 | Kafka consumer: default config, không timeout/retry |
| `techx-corp-platform/src/cart/src/cartstore/ValkeyCartStore.cs` | 57-58 | Valkey: `ConnectRetry=30`, `ExponentialRetry(1000)` |
| `techx-corp-chart/values.yaml` | 282-285 | `wait-for-kafka` init container — `nc -z -w30`, retry loop |
| `techx-corp-chart/values.yaml` | 152-153 | liveness/readiness probes — **commented out** |
| `docs/cdo08/week1/checkout-dependency-map.md` | 86-101 | Dependency table (đầy đủ 12 dependencies) |
| `docs/cdo08/week1/checkout-dependency-map.md` | 130-141 | Risk assessment (từ Task 10) |

---

## 5. Tổng hợp gaps

### Sync (blocking — lỗi = mất đơn)

| Dependency | Timeout | Retry | Fallback | Gap ID | Mức |
|---|---|---|---|---|---|
| cart (gRPC) | ❌ | ❌ | ❌ | G1 | P0 |
| product-catalog (gRPC) | ❌ | ❌ | ❌ | G2 | P0 |
| currency (gRPC) | ❌ | ❌ | ❌ | G3 | P0 |
| shipping /get-quote (HTTP) | ❌ | ❌ | ❌ | G4 | P0 |
| quote qua shipping (HTTP) | ❌ | ❌ | ❌ | G5 | P0 |
| payment (gRPC) | ❌ | ❌ | ❌ | G6 | P0 |
| shipping /ship-order (HTTP) | ❌ | ❌ | ❌ | G7 | P0 |

### Async / non-fatal

| Dependency | Timeout | Retry | Fallback | Gap ID | Mức |
|---|---|---|---|---|---|
| email (HTTP) | ❌ | ❌ | ✅ (warn) | G8 | P1 |
| kafka producer (async) | ✅ (10s) | ✅ (5) | ✅ (skip) | G9 | P1 |
| gRPC client connection | ❌ | ❌ | ❌ | G10 | P0 |
| flagd | ❌ | ❌ | ✅ (default) | G11 | P2 |
| otel-collector | ❌ | ✅ (built-in) | ✅ (drop) | G12 | P2 |
| accounting consumer | ❌ | ✅ (pause) | ✅ (pause) | G13 | P1 |
| fraud-detection consumer | ❌ | ❌ | ❌ | G14 | P1 |

---

## 6. Findings

| # | Finding | Affected | Failure mode | Evidence | Mức | Proposed follow-up |
|---|---|---|---|---|---|---|
| F1 | **Tất cả gRPC calls không có timeout/retry** | cart, product-catalog, currency, payment | Dependency chậm → checkout treo vô thời hạn → cascading failure | `main.go:446-456` — `mustCreateClient` không có timeout config | **P0** | Thêm `context.WithTimeout` + retry interceptor. Tuần 2. |
| F2 | **HTTP calls không có timeout** | shipping (/get-quote, /ship-order) | HTTP call block vô thời hạn → mất đơn | `main.go:467` — `otelhttp.Post` không wrapped timeout | **P0** | Wrap `context.WithTimeout` 5s. Tuần 2. |
| F3 | **Shipping → quote gọi HTTP không timeout** | quote (qua shipping) | Shipping gọi quote không timeout → cascading | `quote.rs:40-64` — `awc::Client::new()` default | **P0** | Fix `awc::ClientBuilder().timeout(3s)`. Tuần 2. |
| F4 | **Email không có retry/queue** | email | Email lỗi → mất vĩnh viễn email xác nhận | `main.go:381-385` — chỉ warn | **P1** | Thêm retry + async queue. Tuần 2-3. |
| F5 | **Kafka producer thiếu idempotent** | kafka | At-least-once → duplicate message nếu retry thành công | `producer.go:42` — comment deferred | **P1** | Implement idempotent producer (REL-03). Tuần 3. |
| F6 | **gRPC client connection không có connect timeout** | tất cả gRPC dependencies | `mustCreateClient` không block → nil connection → panic | `main.go:446-456` | **P0** | Thêm `grpc.WithConnectTimeout` + health check. Tuần 2. |
| F7 | **Fraud-detection consumer không config max.poll.interval** | fraud-detection | Consumer có thể bị kick khỏi group nếu processing lâu | `main.kt:38-57` — default config | **P1** | Config `max.poll.interval.ms=300000`. Tuần 2-3. |
| F8 | **Liveness/readiness probes không được config** | checkout, cart, product-catalog, currency, payment, email, shipping | Kubernetes không thể health-check → pod không được restart kịp thời | `values.yaml:152-153` — commented out | **P0** | Config liveness + readiness probes cho tất cả service. Tuần 2. |

---

## 7. Runtime verification status

| Loại | Trạng thái | Chi tiết |
|---|---|---|
| Static analysis | ✅ Hoàn thành | Source code, config, Helm values — tất cả timeout/retry/fallback config đã được inspect |
| Runtime verification | ⏳ **BLOCKED** | EKS role `TF4-SecReliabilityReadOnlyAudit` không có quyền `get pods`/`get logs` trên namespace `techx-corp`. Cần Quyết cấp RBAC hoặc switch role admin. |
| Trace evidence | ✅ Có từ Task 10 | Trace ID `0a7495c125a14b8911ea597d3564c835` — xem `evidence/map-checkout-and-request-path.md` |
| Re-run window | 24h sau khi environment sẵn sàng | Re-run sẽ verify timeout behavior bằng cách inject fault và check trace span duration |

---

*Reviewed by: [chờ Nguyên review]*
*Status: Draft*