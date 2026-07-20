# CDO08-REL-16 — Cart/Checkout Cutover Smoke Test & Evidence (Blue-Green + Online Migration)

| Field | Value |
|---|---|
| Task | `[CDO08-REL-16][Subtask] Verify cart and checkout behavior with ElastiCache` |
| Liên quan | `CDO08-REL-16-valkey-cutover-plan.md`, `../implementation/drafts/VALKEY-MIGRATION-PLAN.md`, `../implementation/drafts/COMMON-PREREQUISITES.md` |
| Trạng thái | **CHƯA CHẠY** — runbook cross-reference + evidence skeleton. Chưa có kết quả thật. |

## 1. Thứ tự chạy script (`docs/cdo08/week2/mandate8/scripts/valkey/`)

| # | Script | Việc gì |
|---|---|---|
| 1 | `01-preflight-check.sh` | Verify Argo Rollouts CRD, `Rollout/cart`, bridge NLB endpoint, ElastiCache `available` |
| 2 | `test-migration-connection.sh` | Debug pod test TCP reachability tới bridge NLB |
| 3 | `02-start-migration.sh` | `aws elasticache start-migration` |
| 4 | `03-monitor-lag.sh` | Poll `ReplicationLag` tới khi ổn định 0 |
| — | Đẩy connection string cart sang ElastiCache qua Git (managedData.valkey toggle) → Argo Rollouts tạo Green ReplicaSet, `Paused` | |
| 5 | `04-freeze-writes.sh` | `CLIENT PAUSE ... WRITE` trên `valkey-cart` |
| — | Chạy Data Parity Check §2 bên dưới (pre-cutover) | |
| 6 | `05-complete-migration.sh` | `aws elasticache complete-migration` |
| 7 | `06-promote-rollout.sh` | `kubectl argo rollouts promote cart` + `CLIENT UNPAUSE` |
| — | Chạy Data Parity Check §2 bên dưới (post-cutover) + Smoke Test §3 | |
| 8 | `07-enable-tls.sh <1\|2\|3>` | 3 pha zero-downtime TLS, chạy sau khi cutover đã ổn định (không phải điều kiện tiên quyết) |
| 9 | `08-cleanup.sh` | Tắt bridge — **không** xoá `valkey-cart` |

Rollback: `rollback-01-abort-rollout.sh` (+`riotRedisBackfill` Job nếu đã có ghi mới) → `rollback-02-unlock-source.sh`.

## 2. Data Parity Checklist (theo VALKEY-MIGRATION-PLAN.md §5)

**Pre-cutover** (ngay sau freeze writes, bước 5, trước bước 6):
- [ ] K-1: `DBSIZE`/`INFO keyspace` khớp ≥99.9% giữa `valkey-cart` và ElastiCache.
- [ ] K-2: Trạng thái replication link trên AWS Console = `synchronizing`/`active`, `ReplicationLag`=0.

**Post-cutover** (sau bước 7):
- [ ] A-1: Add-to-cart mới → `GET cart:<user_id>` trên ElastiCache trả đúng dữ liệu.
- [ ] A-2: TTL key mới trên ElastiCache trong khoảng (0, 3600] giây.
- [ ] A-3: Dry-run `riot-redis-backfill` Job trên staging (không phải production) để xác nhận script hoạt
      động trước khi cần dùng thật cho rollback.

## 3. Smoke Test Cart/Checkout

- [ ] Add-to-cart (grpcurl `oteldemo.CartService/AddItem`).
- [ ] View cart (grpcurl `oteldemo.CartService/GetCart`).
- [ ] Checkout với item trong cart — order xác nhận thành công.
- [ ] Verify qua Jaeger trace: span Redis trỏ ElastiCache endpoint, không lỗi.

## 4. Theo dõi SLO

Checkout success rate ≥99% (sliding 1 phút), p95 latency theo threshold Stop Condition đã dùng ở
`D8-PERF-03-cutover-contract.md` §4/§6 — áp dụng chung cho mọi migration Mandate 8.

## 5. Evidence (điền sau khi chạy thật)

- **Đã làm gì?** _(chưa chạy)_
- **Kiểm chứng bằng cách nào?** _(chưa chạy)_
- **Evidence nằm ở đâu?** _(chưa chạy)_

## 6. Acceptance Criteria

- [ ] Add-to-cart / view cart / checkout pass.
- [ ] Data parity check (pre + post cutover) pass.
- [ ] Không có error spike rõ trong logs/dashboard.
- [ ] Không xoá `valkey-cart` cho tới khi bake 24-48h ổn định (gate REL-18).
