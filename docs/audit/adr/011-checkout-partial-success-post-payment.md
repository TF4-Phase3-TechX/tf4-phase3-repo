# ADR-011: Checkout Partial-Success sau Payment — Không có Idempotency

**Ngày:** 2026-07-09
**Trạng thái:** Accepted — Deferred fix Week 2-3 (P1)
**Người quyết định:** CDO-08 (Reliability)
**Người review:** CDO-07 (Audit)
**Pillar liên quan:** Reliability, Auditability
**Source:** `techx-corp-platform/src/checkout/main.go`

---

## 1. Bối cảnh (Context)

CDO-08 scan (REL-07) phát hiện luồng checkout có khả năng partial-success sau khi payment đã thành công.

---

## 2. Luồng checkout hiện tại (Confirmed từ main.go)

```
PlaceOrder():
  1. chargeCard()        ← TIỀN ĐÃ BỊ TRỪ
  2. shipOrder()         ← Nếu fail → return Unavailable (tiền đã trừ, không có đơn ship)
  3. emptyUserCart()     ← Error bị ignore: _ = cs.emptyUserCart(...)
  4. sendOrderConfirmation() ← Failure chỉ log warning
  5. sendToPostProcessor()   ← Kafka publish, có thể fail sau khi payment/ship đã xong
```

**Không có idempotency key:** `orderID, _ = uuid.NewUUID()` — mỗi retry tạo UUID mới → double charge risk.

---

## 3. Kafka producer — đã được fix (REL-01)

`kafka/producer.go` hiện tại:
```go
saramaConfig.Producer.RequiredAcks = sarama.WaitForAll  // Fixed từ NoResponse
saramaConfig.Producer.Retry.Max = 5
saramaConfig.Producer.Timeout = 10 * time.Second
```

**Còn lại chưa fix:** Idempotency key, compensation cho shipping failure sau charge.

---

## 4. Rủi ro đã ghi nhận

| Risk | Impact | Scenario |
|---|---|---|
| Double charge | Critical | Payment OK → Ship fail → User retry → Payment charged again |
| Ghost order | High | Ship OK nhưng Kafka fail → Accounting không có record |
| Cart không empty | Medium | emptyUserCart error bị ignore silently |

**CDO-07 audit note:** Checkout có thể tạo ra inconsistency giữa payment records, shipping records, và Kafka events. Không thể audit trail đầy đủ một đơn hàng khi 3 nguồn này không đồng bộ.

---

## 5. Lý do deferred (Rationale)

| Lý do | Giải thích |
|---|---|
| Complexity cao | Idempotency cần persistent order state store |
| Cần outbox pattern | Safe retry cần outbox + transactional publish |
| Scope lớn | Ảnh hưởng checkout, payment, shipping — cần design trước |
| Week 1 focus | Ưu tiên baseline deploy và Kafka producer fix trước |

---

## 6. Tham chiếu (References)

- `techx-corp-platform/src/checkout/main.go:328-392` — PlaceOrder sequence
- `techx-corp-platform/src/checkout/kafka/producer.go` — WaitForAll fix
- `docs/evidence/epic-01/001-rel-01-checkout-kafka-order-event-integrity.md`
- `docs/epic-01-addressing-system-gap/PHASE3-IMPLEMENTATION-GAP-ASSESSMENT.md` — REL-03
