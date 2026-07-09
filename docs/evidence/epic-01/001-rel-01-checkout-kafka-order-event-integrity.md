# EPIC-01 Evidence — REL-01: Checkout Kafka order event integrity

EVIDENCE UPDATE

## Đã làm gì?

**Vòng 1 — Core fix:**

- Đã đổi checkout Kafka producer từ async fire-and-observe sang `sarama.SyncProducer` để publish trả về lỗi trực tiếp cho checkout flow.
- Đã đổi Kafka ack từ `sarama.NoResponse` sang `sarama.WaitForAll` và thêm retry producer baseline (`Producer.Retry.Max = 5`).
- Đã đổi `PlaceOrder` để trả `codes.Unavailable` khi publish order event fail, thay vì checkout vẫn success silently.
- Đã giữ telemetry span/log cho publish success/failure, gồm partition/offset khi Kafka acknowledge thành công.

**Vòng 2 — QA Opus fixes (H2, H3, M2, M3):**

- **H2 (Context-bound SendMessage):** `SendMessage` không có context parameter → wrap trong goroutine + `select` race với `ctx.Done()` để respect gRPC client deadline. Nếu context cancelled trong lúc chờ Kafka, checkout trả lỗi ngay thay vì block.
- **H3 (Fail-fast startup):** Kafka producer creation fail → `panic` thay vì log + continue. Tránh tình trạng service chạy nhưng mọi order fail sau khi đã charge/ship.
- **M2 (kafkaQueueProblems async):** Overload simulation dùng `go func()` thay vì sequential sync `SendMessage` → không block checkout response.
- **M3 (Producer Close):** Thêm `defer svc.KafkaProducerClient.Close()` sau khi tạo producer thành công.
- **Config:** Thêm `saramaConfig.Producer.Timeout = 10s` và comment note về at-least-once semantics.

**Deferred sang REL-03:**

- **H1:** Kafka publish fail sau charge/shipping/cart clear → client retry = duplicate side effects. Cần idempotency key/outbox trước khi safe retry.
- **M1:** `WaitForAll` + retries = at-least-once, không idempotent producer. Cần idempotent producer config hoặc downstream idempotency.

## Kết quả hiện tại

- Checkout không còn bỏ qua kết quả publish Kafka khi `KAFKA_ADDR` được cấu hình.
- Order event publish failure hiện trả lỗi gRPC `Unavailable` tại checkout response path.
- `SendMessage` giờ respect context deadline (goroutine + select pattern).
- Kafka producer fail lúc startup → panic (service không start nếu Kafka required mà không reachable).
- Producer được `Close()` khi shutdown.
- `kafkaQueueProblems` flag overload chạy async không block checkout.
- `Producer.Timeout = 10s` explicit, không rely vào Sarama default.
- Chưa live-verified vì hệ thống chưa Go live.
- Validation: `go build ./...` pass, `go vet ./...` pass, `go test ./...` pass.

## Bằng chứng nằm ở đâu?

- Link/file diagram: N/A
- Source code (paths relative to repo root):
  - `techx-corp-platform/src/checkout/kafka/producer.go:31` — `CreateKafkaProducer` returns `SyncProducer`
  - `techx-corp-platform/src/checkout/kafka/producer.go:38` — `RequiredAcks = sarama.WaitForAll`
  - `techx-corp-platform/src/checkout/kafka/producer.go:39` — `Retry.Max = 5`
  - `techx-corp-platform/src/checkout/kafka/producer.go:40` — `Producer.Timeout = 10s`
  - `techx-corp-platform/src/checkout/main.go:143` — struct field `sarama.SyncProducer`
  - `techx-corp-platform/src/checkout/main.go:234-238` — fail-fast panic + `defer Close()`
  - `techx-corp-platform/src/checkout/main.go:388-391` — `PlaceOrder` returns `Unavailable` on publish fail
  - `techx-corp-platform/src/checkout/main.go:645-655` — context-bounded `SendMessage` via goroutine + select
  - `techx-corp-platform/src/checkout/main.go:689-694` — async `kafkaQueueProblems` goroutines
- QA report (Opus): inline trong session transcript — 7 findings, 4 fixed, 2 deferred, 1 pre-existing
- Screenshot: N/A
- Command output/log:
  - `go build ./...`: pass
  - `go vet ./...`: pass
  - `go test ./...`: pass (`ok github.com/open-telemetry/techx-corp/src/checkout/money`)
  - Pre-existing vet warning `main.go:316` fixed: `err.Error()` → `"%s", err.Error()`
- PR/commit/link nếu có: N/A
- Folder lưu evidence: `docs/evidence/epic-01`

## Ghi chú / Follow-up

- **Cần recheck khi Go live:** Kafka outage/failure test, checkout response, topic offset/log, context cancellation test.
- **Deferred sang REL-03:**
  - H1: Kafka publish fail sau charge/shipping → partial-success không rollback được. Cần idempotency key + order state + outbox pattern trước khi safe retry.
  - M1: `WaitForAll` + retries không idempotent producer → at-least-once duplicate possible. Cần `Producer.Idempotent = true` + `Net.MaxOpenRequests = 1` hoặc downstream idempotency.
- **Pre-existing (REL-05):** `main` graceful shutdown code unreachable — `srv.Serve(lis)` blocks trước signal handler setup. Sẽ fix trong REL-05.

