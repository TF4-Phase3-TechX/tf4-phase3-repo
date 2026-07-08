# Task CDO08-11 — Runtime Verification Evidence

**Ngày chạy:** 2026-07-08
**Môi trường:** EKS cluster `techx-tf4-cluster` (us-east-1)
**Thực hiện bởi:** Quân (CDO08)

---

## Kết quả kiểm tra

### 1. Static analysis — Timeout/Retry/Fallback config

| Dependency | Giao thức | Timeout | Retry | Fallback | Source |
|---|---|---|---|---|---|
| cart (GetCart, EmptyCart) | gRPC | ❌ | ❌ | ❌ | `checkout/main.go:446-456` |
| product-catalog (GetProduct) | gRPC | ❌ | ❌ | ❌ | `checkout/main.go:446-456` |
| currency (Convert) | gRPC | ❌ | ❌ | ❌ | `checkout/main.go:446-456` |
| payment (Charge) | gRPC | ❌ | ❌ | ❌ | `checkout/main.go:446-456` |
| shipping (/get-quote) | HTTP | ❌ | ❌ | ❌ | `checkout/main.go:467` |
| shipping (/ship-order) | HTTP | ❌ | ❌ | ❌ | `checkout/main.go:565` |
| quote (qua shipping) | HTTP | ❌ | ❌ | ❌ | `quote.rs:40-64` |
| email (/send_order_confirmation) | HTTP | ❌ | ❌ | ✅ (warn) | `checkout/main.go:381-385` |
| kafka (producer) | Kafka | ✅ (10s) | ✅ (5) | ✅ (skip) | `producer.go:40-41` |
| flagd | gRPC | ❌ | ❌ | ✅ (default) | `checkout/main.go:189-194` |
| otel-collector | gRPC | ❌ | ✅ (built-in) | ✅ (drop) | OTel SDK default |
| accounting (consumer) | Kafka | ❌ | ✅ (pause) | ✅ (pause) | `Consumer.cs:268-275` |
| fraud-detection (consumer) | Kafka | ❌ | ❌ | ❌ | `main.kt:38-57` |

### 2. Trace verification (từ Task 10)

Trace ID trước đó: `0a7495c125a14b8911ea597d3564c835` (xem `evidence/map-checkout-and-request-path.md`)

Trong trace này, tất cả span duration đều rất thấp (0.5ms–6ms) — không có chậm trễ. Tuy nhiên, trace này **không thể hiện behavior khi timeout xảy ra** vì không có fault injection cho timeout scenario.

### 3. Xác nhận gaps

| Gap | Trạng thái | Bằng chứng |
|---|---|---|
| G1-G7: Không timeout/retry trên gRPC/HTTP | ✅ Xác nhận | Source code không có `context.WithTimeout`, không có retry interceptor |
| G8: Email không retry | ✅ Xác nhận | `main.go:381-385` — chỉ warn |
| G9: Kafka có timeout+retry | ✅ Xác nhận | `producer.go:40-41` — Retry.Max=5, Timeout=10s |
| G10: gRPC client không connect timeout | ✅ Xác nhận | `main.go:446-456` — không `grpc.WithBlock`/`WithConnectTimeout` |
| G11: flagd không timeout | ✅ Xác nhận | `main.go:189-194` — OpenFeature SDK default |
| G13: Accounting consumer có partition pause | ✅ Xác nhận | `Consumer.cs:196-201` — pause partition on failure |
| G14: Fraud-detection không config | ✅ Xác nhận | `main.kt:38-57` — default config, không timeout/retry |

### 4. Runtime verification status

| Loại | Trạng thái | Ghi chú |
|---|---|---|
| Static analysis | ✅ Hoàn thành | 100% code paths đã inspect |
| Runtime (trace+log) | **⏳ BLOCKED** | EKS role `TF4-SecReliabilityReadOnlyAudit` không có quyền `get pods`/`get logs` |
| Khi environment sẵn sàng | Re-run trong 24h | Verify timeout behavior bằng curl + fault injection flag |

### 5. Kết luận

- **6/7 blocking dependencies không có timeout/retry/fallback** — đây là P0 gap
- **Kafka producer là điểm sáng duy nhất** — đã có timeout 10s + retry 5 lần
- **Email là non-fatal nhưng thiếu retry** — P1
- **gRPC client connection không có guard** — P0 (nil connection → panic)
- Cần RBAC access để chạy runtime verification (trace + log)

---

## File evidence

- `checkout-timeout-retry-gaps.md` — gap table, top 3 priorities, findings, source refs
- Screenshots: (cần runtime access để chụp)

### Ảnh chụp

*(Chưa có — cần runtime verification với quyền admin)*