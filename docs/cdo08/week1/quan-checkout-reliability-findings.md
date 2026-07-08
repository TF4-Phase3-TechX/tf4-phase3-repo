# Checkout Reliability Findings — CDO08 Week 1

**Task:** CDO08-38 — Scan checkout reliability risks cho CDO08 Week 1
**Owner:** Quân
**Pillar:** Reliability
**Priority:** P1
**Ngày:** 2026-07-08
**Thời điểm kiểm tra runtime:** 2026-07-08 20:30 UTC+7

---

## 1. Checkout baseline

### 1.1 Checkout dependency map

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

Chi tiết: xem `docs/cdo08/week1/checkout-dependency-map.md` (Task 10).

### 1.2 Service critical trong checkout path

| Service | Ngôn ngữ | Vai trò | Ảnh hưởng khi lỗi |
|---|---|---|---|
| frontend-proxy (Envoy) | Envoy | Cổng vào duy nhất | Không thể truy cập storefront |
| frontend (Next.js) | TypeScript | SSR, render UI | Storefront không hiển thị |
| checkout (Go) | Go | Điều phối PlaceOrder | Không thể đặt hàng |
| cart (.NET) | C# | Quản lý giỏ hàng | Không lấy được giỏ → mất đơn |
| product-catalog (Go) | Go | Thông tin sản phẩm | Không có giá/chi tiết SP → mất đơn |
| currency (C++) | C++ | Chuyển đổi tiền tệ | Không tính được tổng tiền → mất đơn |
| shipping (Rust) | Rust | Tính phí ship + giao hàng | Không có quote/tracking → mất đơn |
| quote (PHP) | PHP | Báo giá ship (qua shipping) | Shipping không quote được → mất đơn |
| payment (Node.js) | Node.js | Xử lý thanh toán | Không charge được thẻ → mất đơn |
| email (Ruby) | Ruby | Gửi email xác nhận | Không gây chết đơn — chỉ mất email |
| kafka | Kafka | Event bus sau checkout | Đơn thành công — downstream miss event |
| accounting (.NET) | C# | Consumer Kafka | Miss order event |
| fraud-detection (Kotlin) | Kotlin | Consumer Kafka | Miss order event |

### 1.3 Runtime status

Thời điểm kiểm tra: 2026-07-08 20:30 UTC+7 — namespace `techx-tf4`

| Pod | Ready | Status | Ghi chú |
|---|---|---|---|
| checkout | 0/1 | ImagePullBackOff | Chờ ECR image |
| cart | 0/1 | ImagePullBackOff | Chờ ECR image |
| currency | 0/1 | ImagePullBackOff | Chờ ECR image |
| email | 0/1 | ImagePullBackOff | Chờ ECR image |
| frontend | 0/1 | ImagePullBackOff | Chờ ECR image |
| frontend-proxy | 0/1 | ImagePullBackOff | Chờ ECR image |
| shipping | 1/1 | Running | |
| quote | 1/1 | Running | |
| payment | 1/1 | Running | |
| product-catalog | 1/1 | Running | 2 restarts |
| kafka | 1/1 | Running | |
| valkey-cart | 1/1 | Running | |
| postgresql | 1/1 | Running | |
| flagd | 1/1 | Running | |
| jaeger | 1/1 | Running | |
| grafana | 4/4 | Running | |
| accounting | 0/1 | ImagePullBackOff | Chờ ECR image |
| fraud-detection | 0/1 | ImagePullBackOff | Chờ ECR image |

**Kết luận:** Runtime verification bị BLOCKED do 10/18 pod core đang ImagePullBackOff (ECR image chưa được build). Trace ID từ Jaeger lần cuối cùng chạy được (Task 10): `0a7495c125a14b8911ea597d3564c835`.

---

## 2. Findings

### 2.1 Gọi sync (blocking — lỗi = mất đơn hàng)

#### F01: gRPC calls không có timeout/retry

| Mục | Chi tiết |
|---|---|
| **Mô tả** | Tất cả 4 gRPC dependency (cart, product-catalog, currency, payment) dùng `mustCreateClient` với default gRPC — không có timeout, retry, deadline |
| **Pillar** | Reliability |
| **Service/Component** | `checkout/main.go:446-456`, `checkout/main.go:201-229` |
| **Evidence** | Source code: `mustCreateClient` chỉ dùng `grpc.WithTransportCredentials` + `grpc.WithStatsHandler`. Không có `grpc.WithBlock`, `grpc.WithConnectTimeout`, `context.WithTimeout` trước bất kỳ gRPC call nào |
| **Impact** | Dependency chậm → checkout treo vô thời hạn → cascading failure, p95 latency tăng vọt, connection pool exhaustion |
| **Priority** | **P0** |
| **Phối hợp** | — |
| **Đề xuất** | Thêm `context.WithTimeout` (cart 5s, product-catalog 3s, currency 3s, payment 10s) + gRPC retry interceptor |

#### F02: HTTP calls không có timeout

| Mục | Chi tiết |
|---|---|
| **Mô tả** | `otelhttp.Post` dùng context từ gRPC request — không có `context.WithTimeout` riêng. Ảnh hưởng: `/get-quote`, `/ship-order` (shipping) và `/send_order_confirmation` (email) |
| **Pillar** | Reliability |
| **Service/Component** | `checkout/main.go:467`, `checkout/main.go:565` |
| **Evidence** | `otelhttp.Post(ctx, ...)` không wrapped trong `context.WithTimeout`. Shipping gọi quote qua `awc::Client::new()` — không có timeout config |
| **Impact** | HTTP call block vô thời hạn → mất đơn. Quote (PHP) là service đơn giản nhất, dễ treo nhất |
| **Priority** | **P0** |
| **Phối hợp** | — |
| **Đề xuất** | Wrap `otelhttp.Post` với `context.WithTimeout(ctx, 5*time.Second)`. Fix shipping/quote: thêm `awc::ClientBuilder().timeout(Duration::from_secs(3))` |

#### F03: Shipping → quote HTTP không timeout

| Mục | Chi tiết |
|---|---|
| **Mô tả** | Shipping service (Rust) gọi quote service qua HTTP với `awc::Client::new()` default — không có timeout |
| **Pillar** | Reliability |
| **Service/Component** | `shipping/src/shipping_service/quote.rs:40-64` |
| **Evidence** | `awc::Client::new()` không dùng `ClientBuilder().timeout()` |
| **Impact** | Quote chậm → shipping treo → checkout treo → cascading failure |
| **Priority** | **P0** |
| **Phối hợp** | — |
| **Đề xuất** | Fix `awc::ClientBuilder().timeout(Duration::from_secs(3))`. Tuần 2 |

#### F04: gRPC client connection không có connect timeout

| Mục | Chi tiết |
|---|---|
| **Mô tả** | `mustCreateClient` không dùng `grpc.WithBlock` hoặc `grpc.WithConnectTimeout`. Connection được tạo async — nếu connect fail, chỉ log error, không panic, nhưng connection object có thể nil |
| **Pillar** | Reliability |
| **Service/Component** | `checkout/main.go:446-456` |
| **Evidence** | `mustCreateClient` không có `grpc.WithBlock` hoặc `grpc.WithConnectTimeout`. Gọi RPC trên nil connection → panic |
| **Impact** | Gọi RPC trên connection lỗi → panic. gRPC resolver mặc định retry forever nhưng không có timeout |
| **Priority** | **P0** |
| **Phối hợp** | — |
| **Đề xuất** | Thêm `grpc.WithConnectTimeout(5s)` + health check. Tuần 2 |

#### F05: Liveness/readiness probes không được config

| Mục | Chi tiết |
|---|---|
| **Mô tả** | Liveness và readiness probes bị comment out trong Helm values cho tất cả service |
| **Pillar** | Reliability |
| **Service/Component** | `techx-corp-chart/values.yaml:152-153` |
| **Evidence** | `#   livenessProbe: {}` / `#   readinessProbe: {}` — probes không được config |
| **Impact** | Kubernetes không thể health-check → pod không được restart kịp thời khi lỗi. Pod có thể nhận traffic khi chưa sẵn sàng |
| **Priority** | **P0** |
| **Phối hợp** | Nam (Task 18: Audit probe coverage) |
| **Đề xuất** | Config liveness + readiness probes cho tất cả service trong revenue path. Tuần 2 |

### 2.2 Gọi bán sync (non-fatal — đơn vẫn thành công)

#### F06: Email không có retry/queue

| Mục | Chi tiết |
|---|---|
| **Mô tả** | Email lỗi chỉ log `Warn` — không retry, không queue. Email service down → mất vĩnh viễn email xác nhận |
| **Pillar** | Reliability |
| **Service/Component** | `checkout/main.go:381-385` |
| **Evidence** | `if err := cs.sendOrderConfirmation(...); err != nil { logger.Warn(...) }` — không retry, không queue |
| **Impact** | Khách không nhận được email xác nhận → tăng support ticket |
| **Priority** | **P1** |
| **Phối hợp** | — |
| **Đề xuất** | Thêm retry 2-3 lần + async queue. Hoặc outbox pattern. Tuần 2-3 |

#### F07: Init container checkout chờ kafka nhưng kafka là async

| Mục | Chi tiết |
|---|---|
| **Mô tả** | Checkout init container `wait-for-kafka` block đến khi kafka:9092 reachable. Nhưng kafka là async dependency — checkout vẫn có thể start và serve request mà không cần kafka |
| **Pillar** | Reliability |
| **Service/Component** | `techx-corp-chart/values.yaml:282-285` |
| **Evidence** | Init container dùng `until nc -z -v -w30 kafka 9092`. Kafka producer có fallback (skip nếu `KAFKA_ADDR` rỗng) |
| **Impact** | Nếu kafka không lên, checkout không bao giờ start → mất toàn bộ đơn hàng |
| **Priority** | **P1** |
| **Phối hợp** | — |
| **Đề xuất** | Cân nhắc làm kafka optional tại startup — init container không block, cho phép checkout start trước |

#### F08: Kafka producer thiếu idempotent

| Mục | Chi tiết |
|---|---|
| **Mô tả** | Kafka producer dùng `WaitForAll` + `Retry.Max=5` + `Timeout=10s` — at-least-once semantics. Thiếu idempotent producer → duplicate message nếu retry thành công |
| **Pillar** | Reliability |
| **Service/Component** | `checkout/kafka/producer.go:42` |
| **Evidence** | Comment trong code: `// Idempotent producer deferred to REL-03` |
| **Impact** | Downstream (accounting, fraud-detection) có thể nhận duplicate order event |
| **Priority** | **P1** |
| **Phối hợp** | — |
| **Đề xuất** | Implement idempotent producer (REL-03). Tuần 3 |

#### F09: Fraud-detection consumer không config max.poll.interval

| Mục | Chi tiết |
|---|---|
| **Mô tả** | Fraud-detection consumer dùng Kafka config default — không có `max.poll.interval.ms`. Nếu processing lâu (e.g., `kafkaQueueProblems` flag inject sleep), consumer có thể bị kick khỏi group |
| **Pillar** | Reliability |
| **Service/Component** | `fraud-detection/.../main.kt:38-57` |
| **Evidence** | Consumer config chỉ có key/value deserializer + group ID + bootstrap servers — không có timeout/retry/max.poll.interval |
| **Impact** | Consumer bị kick khỏi group → rebalance → processing delay |
| **Priority** | **P1** |
| **Phối hợp** | — |
| **Đề xuất** | Config `max.poll.interval.ms=300000` + processing timeout. Tuần 2-3 |

### 2.3 Feature flags fault injection

#### F10: paymentUnreachable flag hard-code bad address

| Mục | Chi tiết |
|---|---|
| **Mô tả** | Feature flag `paymentUnreachable` redirect checkout gửi payment tới `badAddress:50051` — mọi đơn hàng đều lỗi khi flag bật |
| **Pillar** | Reliability / Security |
| **Service/Component** | `checkout/main.go:541-545` |
| **Evidence** | Source code: `paymentUnreachable` flag → `mustCreateClient("badAddress:50051")` |
| **Impact** | P0 nếu flag bật accidently — toàn bộ checkout ngừng hoạt động |
| **Priority** | **P0** (risk), flagd fault injection là tính năng có chủ đích |
| **Phối hợp** | Thuỷ (flagd safety checklist) |
| **Đề xuất** | Ghi vào risk register; monitor flagd sync health; ensure flagd UI access controlled |

### 2.4 Infrastructure

#### F11: flagd là hard dependency

| Mục | Chi tiết |
|---|---|
| **Mô tả** | Checkout dùng OpenFeature SDK với `flagd.NewProvider()` — panic nếu flagd không reachable |
| **Pillar** | Reliability |
| **Service/Component** | `checkout/main.go:189-194` |
| **Evidence** | Source code: `flagd.NewProvider()` gọi trong `main()`, nếu lỗi → log error nhưng không panic. Feature flags mặc định safe value |
| **Impact** | flagd down không gây chết checkout nhưng mất fault injection capability |
| **Priority** | **P2** |
| **Phối hợp** | Thuỷ |
| **Đề xuất** | Monitor flagd sync health; thêm timeout cho flag evaluation |

---

## 3. Checkout smoke / SLO evidence

### 3.1 Smoke test checklist

File: `docs/cdo08/week1/checkout-smoke-test-checklist.md` (Task 12)

Checklist gồm 19 steps:
- **Pre-check (5 steps):** pod status, ALB health, Jaeger reachable
- **User flow (9 steps):** browse → add cart → checkout → confirmation
- **Post-checkout (5 steps):** Jaeger trace, log, accounting consumer, Kafka lag, Grafana

### 3.2 Smoke test result

| Step | Result | Ghi chú |
|---|---|---|
| P1-P5 | ⏳ BLOCKED | Core pod ImagePullBackOff — ECR image chưa build |
| U1-U9 | ⏳ BLOCKED | Cần pod checkout + cart + payment running |
| V1-V5 | ⏳ BLOCKED | Cần trace + log từ checkout request thật |

### 3.3 Trace evidence từ Task 10

Trace ID: `0a7495c125a14b8911ea597d3564c835` — một request checkout hoàn chỉnh (2026-07-08, trước khi image bị xoá).

Các span duration:
- cart.GetCart: 1.3ms
- product-catalog.GetProduct (item 1): 0.7ms
- product-catalog.GetProduct (item 2): 1.5ms
- shipping /get-quote: 2.7ms
- payment.Charge: 0.5ms
- email /send_order_confirmation: 4.2ms

**Kết luận:** Khi mọi service chạy bình thường, checkout hoàn thành trong ~45ms. Không có timeout/retry issue ở baseline — nhưng không có fault injection test để verify behavior khi dependency chậm/lỗi.

### 3.4 Gap / Blocker

| Gap | Mô tả | Ảnh hưởng |
|---|---|---|
| Core pod ImagePullBackOff | 10/18 pod revenue path không start được | Không thể run smoke test, không thể verify runtime behavior |
| RBAC limited | Role `TF4-SecReliabilityReadOnlyAudit` không có quyền trên namespace `techx-corp` (cần binding) | Không thể lấy log/trace từ EKS nếu cần troubleshoot |
| Thiếu fault injection test | Chưa có test nào verify checkout behavior khi dependency chậm hoặc timeout | Chưa thể xác nhận proposed mitigation đúng |

---

## 4. Backlog candidates

Dưới đây là danh sách issue đề xuất cho Hải đánh giá bằng rubric và đưa vào `cdo08-week1-backlog.md`.

### P0 — Tuần 2

| ID | Issue | Risk | Service | Evidence | Owner phối hợp |
|---|---|---|---|---|---|
| BC01 | Thêm timeout cho gRPC calls (cart, product-catalog, currency, payment) | Dependency chậm → checkout treo vô thời hạn | `checkout/main.go` | Source: `mustCreateClient` không timeout | Quân |
| BC02 | Thêm timeout cho HTTP calls (shipping, email) | HTTP call block vô thời hạn → mất đơn | `checkout/main.go`, `shipping/quote.rs` | Source: `otelhttp.Post` không wrapped timeout | Quân |
| BC03 | Config liveness/readiness probes | Pod không được health-check, nhận traffic khi chưa ready | Helm `values.yaml` | Source: probes commented out | Nam |
| BC04 | Thêm gRPC connect timeout | Nil connection → panic | `checkout/main.go` | Source: `mustCreateClient` không WithBlock | Quân |

### P1 — Tuần 2-3

| ID | Issue | Risk | Service | Evidence | Owner phối hợp |
|---|---|---|---|---|---|
| BC05 | Thêm retry/queue cho email | Mất vĩnh viễn email xác nhận | `checkout/main.go` | Source: email lỗi chỉ warn | Quân |
| BC06 | Làm kafka optional tại startup | Kafka down → checkout không start được | Helm `values.yaml` | Source: init container block chờ kafka | Quân / Nam |
| BC07 | Implement idempotent Kafka producer | Duplicate order event | `checkout/kafka/producer.go` | Source: idempotent deferred | Quân |
| BC08 | Config max.poll.interval cho fraud-detection consumer | Consumer bị kick khỏi group | `fraud-detection/main.kt` | Source: default config | Quân |
| BC09 | Build ECR image và deploy | Core pod ImagePullBackOff — không thể verify runtime | ECR + Helm | Runtime: 10/18 pod không start | Quyết / DevOps |

### P2 — Tuần 3+

| ID | Issue | Risk | Service | Evidence | Owner phối hợp |
|---|---|---|---|---|---|
| BC10 | Monitor flagd sync health | Mất fault injection capability | flagd | Source: flagd.NewProvider() | Thuỷ |
| BC11 | Thêm circuit breaker cho cart, payment | Cascading failure khi dependency down | `checkout/main.go` | Source: không có circuit breaker | Quân |
| BC12 | Fallback flat rate cho shipping | Shipping down → không thể checkout | `checkout/main.go` | Source: shipping error → mất đơn | Quân |

---

## 5. Source references

| File | Dòng | Nội dung |
|---|---|---|
| `techx-corp-platform/src/checkout/main.go` | 446-456 | `mustCreateClient` — gRPC không timeout |
| `techx-corp-platform/src/checkout/main.go` | 201-229 | 6 gRPC clients dùng `mustCreateClient` |
| `techx-corp-platform/src/checkout/main.go` | 381-385 | Email fallback — chỉ warn |
| `techx-corp-platform/src/checkout/main.go` | 467 | `otelhttp.Post` cho `/get-quote` — không timeout |
| `techx-corp-platform/src/checkout/main.go` | 541-545 | `paymentUnreachable` flag → bad address |
| `techx-corp-platform/src/checkout/kafka/producer.go` | 36-43 | Kafka producer: `Retry.Max=5`, `Timeout=10s` |
| `techx-corp-platform/src/shipping/src/shipping_service/quote.rs` | 40-64 | `awc::Client::new()` — không timeout |
| `techx-corp-platform/src/fraud-detection/.../main.kt` | 38-57 | Kafka consumer default config |
| `techx-corp-chart/values.yaml` | 152-153 | Liveness/readiness probes commented out |
| `techx-corp-chart/values.yaml` | 282-285 | `wait-for-kafka` init container |
| `techx-corp-chart/flagd/demo.flagd.json` | — | Fault injection flags |

---

## 6. Tổng hợp

| Hạng mục | Số lượng |
|---|---|
| Findings | 11 (F01-F11) |
| P0 findings | 5 (F01-F05) |
| P1 findings | 4 (F06-F09) |
| P2 findings | 2 (F10-F11) |
| Backlog candidates | 12 (BC01-BC12) |
| Blocking (direct checkout fail) | 7 (F01-F05, F07, F10) |
| Non-fatal (post-order) | 4 (F06, F08, F09, F11) |
| Smoke test steps | 19 (chưa chạy được) |

---

*Reviewed by: [chờ Nguyên review]*
*Status: Draft*