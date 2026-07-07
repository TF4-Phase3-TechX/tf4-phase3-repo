# EPIC-01 Evidence — REL-02: Accounting consumer manual commit after DB write

EVIDENCE UPDATE

## Đã làm gì?

- Đã tắt `EnableAutoCommit = true` → `EnableAutoCommit = false` + `EnableAutoOffsetStore = false` trong `BuildConsumer()`.
- Đã đổi `ProcessMessage` nhận `ConsumeResult` thay vì raw `Message` để có offset cho manual commit.
- Đã thêm `CommitOffset()` helper: gọi `_consumer.Commit(consumeResult)` chỉ sau khi DB write thành công.
- Đã wrapper DB write trong explicit EF Core transaction (`BeginTransaction` / `SaveChanges` / `Commit`).
- Đã đổi shared `_dbContext` singleton → per-message `using var dbContext` để tránh stale tracking state.
- Đã thêm `OrderAlreadyPersisted()` idempotency check: kiểm tra cả `Orders` + `Shipping` trước khi insert, để tránh duplicate replay gây lỗi primary key và mất dữ liệu.
- Đã thêm `PausePartition()` strategy: khi parse/persist/commit fail, pause partition để ngăn consumer đọc thêm message từ partition đó, tránh việc commit offset sau bỏ qua message bị fail.
- Nếu `PausePartition()` fail, set `_isListening = false` để dừng consumer thay vì tiếp tục xử lý và risk mất message.

## Kết quả hiện tại

- Kafka offset chỉ được commit SAU KHI DB transaction thành công. Không còn auto-commit background timer.
- Parse failure: không commit offset, partition bị pause → message không bị mất.
- Persist failure: transaction rollback, offset không commit, partition pause → message retry on restart.
- DB down: `BeginTransaction` bên trong `try` → được catch, offset không commit, partition pause.
- Commit failure sau DB success: idempotency check + partition pause xử lý duplicate replay.
- Chưa live-verified vì hệ thống chưa Go live và máy không có .NET SDK (`dotnet build` không chạy được).

## Bằng chứng nằm ở đâu?

- Source code:
  - `C:/Users/thanh/Desktop/workspace/FINAL-PHASE/tf4-phase3-repo/techx-corp-platform/src/accounting/Consumer.cs:270` — `EnableAutoCommit = false`
  - `C:/Users/thanh/Desktop/workspace/FINAL-PHASE/tf4-phase3-repo/techx-corp-platform/src/accounting/Consumer.cs:271` — `EnableAutoOffsetStore = false`
  - `C:/Users/thanh/Desktop/workspace/FINAL-PHASE/tf4-phase3-repo/techx-corp-platform/src/accounting/Consumer.cs:129` — per-message `using var dbContext`
  - `C:/Users/thanh/Desktop/workspace/FINAL-PHASE/tf4-phase3-repo/techx-corp-platform/src/accounting/Consumer.cs:142` — explicit `BeginTransaction()`
  - `C:/Users/thanh/Desktop/workspace/FINAL-PHASE/tf4-phase3-repo/techx-corp-platform/src/accounting/Consumer.cs:183` — `CommitOffset()` after `SaveChanges` + `transaction.Commit()`
  - `C:/Users/thanh/Desktop/workspace/FINAL-PHASE/tf4-phase3-repo/techx-corp-platform/src/accounting/Consumer.cs:208` — `OrderAlreadyPersisted()` idempotency check
  - `C:/Users/thanh/Desktop/workspace/FINAL-PHASE/tf4-phase3-repo/techx-corp-platform/src/accounting/Consumer.cs:246` — `PausePartition()` with return bool
  - `C:/Users/thanh/Desktop/workspace/FINAL-PHASE/tf4-phase3-repo/techx-corp-platform/src/accounting/Consumer.cs:111,195,234` — `_isListening = false` khi pause fail
- Screenshot: N/A
- Command output/log:
  - `dotnet build`: failed — No .NET SDK installed (Runtime 8.0.28 only, project targets net10.0)
  - Grep confirmed all key symbols present: `EnableAutoCommit=false`, `EnableAutoOffsetStore=false`, `PausePartition`, `OrderAlreadyPersisted`, `CommitOffset`, `BeginTransaction`, `using var dbContext`
- PR/commit/link nếu có: N/A
- Folder lưu evidence: `C:/Users/thanh/Desktop/workspace/FINAL-PHASE/tf4-phase3-repo/docs/evidence/epic-01`

## Ghi chú / Follow-up

- Cần cài .NET 10.0 SDK để verify build (`winget install Microsoft.DotNet.SDK.10` hoặc [https://dotnet.microsoft.com/en-us/download/dotnet/10.0](https://dotnet.microsoft.com/en-us/download/dotnet/10.0)).
- Cần live-verify khi Go live: broken DB connection test, consumer offset behavior, accounting table.
- DLQ/quarantine cho poison message chưa implement — hiện tại partition pause yêu cầu manual intervention.
- Partition pause strategy không có auto-resume trong cùng session (không có `Seek` backward) — restart consumer sẽ re-read từ committed offset.
- REL-02 đã address core gap (offset commit sau DB write + không mất message khi DB fail).
- REL-03 (idempotency/outbox design) sẽ cover thêm retry/backoff và DLQ path.

