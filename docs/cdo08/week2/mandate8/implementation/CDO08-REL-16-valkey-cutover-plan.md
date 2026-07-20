# CDO08-REL-16 — Cart Cutover to ElastiCache Valkey (Blue-Green + Online Migration)

| Field | Value |
|---|---|
| Task | `[CDO08-REL-16][P0][Valkey] Migrate cart state to ElastiCache and verify app behavior` |
| Owner | Quân |
| Mandate | 8 (Managed Services Migration) |
| Approach | **Argo Rollouts Blue-Green + AWS ElastiCache Online Migration** — follows `../implementation/drafts/VALKEY-MIGRATION-PLAN.md` and `../implementation/drafts/COMMON-PREREQUISITES.md` exactly, per explicit instruction. Supersedes the earlier Cold Cutover approach (see superseded notes in `../adr/proposals/quan/MANDATE-08-VALKEY-DECISIONS-Quan.md` VK-01/03/04). |
| Trạng thái | Đang chuẩn bị — **chưa cutover, chưa chạy script nào** |

## 1. Mục tiêu

Chuyển `cart` từ Valkey self-hosted (`valkey-cart:6379`) sang ElastiCache Valkey (`techx-tf4-valkey-cart`)
**bảo toàn dữ liệu cart đang hoạt động** (không cold cutover) — dùng AWS ElastiCache Online Migration để
replicate dữ liệu sống, và Argo Rollouts Blue-Green để chuyển traffic có kiểm soát, có thể revert tức thì
nếu lỗi trước khi promote.

## 2. Vì sao đổi hướng so với ADR gốc

ADR gốc (VK-01/03/04, do Quân tự điền) chọn Cold Cutover vì cho rằng cart là dữ liệu ephemeral không đáng
công sức bảo toàn. Task hiện tại yêu cầu follow đúng `VALKEY-MIGRATION-PLAN.md` — tài liệu này giả định
Active Migration ngay từ đầu. Đã cập nhật ADR để đánh dấu rõ VK-01/03/04 là **đã bị supersede**, không xoá
phân tích gốc (giữ lịch sử quyết định). VK-02 (sizing) và VK-05 (eviction alert) không đổi — độc lập với
kỹ thuật di trú.

## 3. Prerequisites (theo COMMON-PREREQUISITES.md, chưa hoàn tất)

| # | Việc cần làm | Trạng thái |
|---|---|---|
| P1 | Cài Argo Rollouts controller (Helm) + CRD | Application đã commit (`argocd/root-resources/applications.yaml`), **chưa sync** |
| P2 | Cấp quyền ArgoCD ClusterRole cho CRD `rollouts.argoproj.io`/`rolloutmanager` | AppProject `namespaceResourceWhitelist` đã thêm `argoproj.io/Rollout` — cần verify ArgoCD ServiceAccount ClusterRole riêng nếu chưa đủ |
| P3 | NLB bridge `valkey-migration-bridge` reach được `valkey-cart` | Template đã commit (`valkeyMigrationBridge.enabled=false` mặc định) — **chưa bật, chưa có NLB thật** |
| P4 | IAM quyền `elasticache:StartMigration`/`CompleteMigration`/`DescribeReplicationGroups` cho người vận hành | **Chưa verify** — cần check trước khi chạy `02-start-migration.sh` |
| P5 | SG cho phép ElastiCache reach bridge | Đã verify: egress rule có sẵn từ REL-14 (`elasticache_valkey_to_vpc_redis`), khớp đúng pattern REL-15 Postgres bridge đã dùng — không cần sửa Terraform |

## 4. PM Approval Gate

| Field | Value |
|---|---|
| Cần approval cho | Đổi kiến trúc cutover (Active Migration + Argo Rollouts thay vì Cold Cutover đã review trước đó) |
| Trạng thái | **PENDING** — chưa xin lại approval cho hướng mới này |
| Gate | Không chạy bất kỳ script nào trong `scripts/valkey/` cho tới khi có approval + đủ Prerequisites ở §3 |

## 5. Runbook (tham chiếu, không lặp lại chi tiết)

Xem `docs/cdo08/week2/mandate8/scripts/valkey/` (11 script, đánh số theo thứ tự chạy) và
`CDO08-REL-16-cart-cutover-evidence.md` cho checklist đầy đủ + data parity checks (theo
`VALKEY-MIGRATION-PLAN.md` §5).

## 6. Rollback

Hai trường hợp theo `VALKEY-MIGRATION-PLAN.md` §4:

- **Trước khi có ghi mới trên ElastiCache (RPO=0):** `rollback-01-abort-rollout.sh` (abort Blue-Green,
  active Service tự quay về ReplicaSet cũ trỏ `valkey-cart`) + `rollback-02-unlock-source.sh`.
- **Sau khi đã có ghi mới:** bật `riotRedisBackfill.enabled=true` (Job VAP-compliant, FLUSHALL +
  backfill ElastiCache→`valkey-cart` bằng `riot-redis`) → sau đó mới `rollback-01`/`rollback-02`.

## 7. Retention Boundary

Không xoá `valkey-cart`/PVC cho tới khi bake ổn định 24–48h trên ElastiCache (gate cho REL-18, giống mọi
migration khác trong Mandate 8). `08-cleanup.sh` chỉ tắt NLB bridge, không đụng tới `valkey-cart` component.

## 8. Chưa làm (explicitly out of scope lượt này)

Không sync ArgoCD (chưa cài Argo Rollouts thật), không bật `valkeyMigrationBridge`/`riotRedisBackfill`,
không chạy script nào, không đụng AWS/ElastiCache live, không tạo PR (hỏi riêng khi code sẵn sàng).
