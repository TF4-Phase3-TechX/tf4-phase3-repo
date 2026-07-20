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
| P1 | Cài Argo Rollouts controller (Helm) + CRD | **Xong** — Application `argo-rollouts` đã merge+sync qua PR #56/#396 (gitops), verify trực tiếp trên cluster: `kubectl get application argo-rollouts -n argocd` → `Synced`/`Healthy`, CRD `rollouts.argoproj.io` tồn tại, controller pod `1/1 Running`. |
| P2 | Cấp quyền ArgoCD ClusterRole cho CRD `rollouts.argoproj.io` | **Xong** — verify trực tiếp: `kubectl auth can-i create rollouts.argoproj.io --as=system:serviceaccount:argocd:argocd-application-controller` → `yes`. |
| P3 | NLB bridge `valkey-migration-bridge` reach được `valkey-cart` | Template đã merge (PR #397, dùng nguyên bản không tự viết lại), `valkeyMigrationBridge.enabled=false` mặc định — **chưa bật, chưa có NLB thật**. Selector `opentelemetry.io/name: valkey-cart` đã verify khớp label pod thật. |
| P4 | IAM quyền `elasticache:StartMigration`/`CompleteMigration`/`DescribeReplicationGroups` cho người vận hành | **Xong** — verify lại bằng `aws iam simulate-principal-policy` trên role `TF4-SecurityIAMSSOManager`: cả 3 action đều `allowed` (trước đó `StartMigration`/`CompleteMigration` là `implicitDeny`, đã được cấp thêm). |
| P5 | SG cho phép ElastiCache reach bridge | Đã verify: egress rule có sẵn từ REL-14 (`elasticache_valkey_to_vpc_redis`), khớp đúng pattern REL-15 Postgres bridge đã dùng — không cần sửa Terraform |
| P6 | `redis-cli` có trong image `valkey-cart` không (dùng bởi `04-freeze-writes.sh`/`06-promote-rollout.sh`/`rollback-02-unlock-source.sh`) | **Xong** — verify trực tiếp: `kubectl exec deploy/valkey-cart -- which redis-cli` → `/usr/local/bin/redis-cli` tồn tại (cả `valkey-cli` cũng có). |

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

Argo Rollouts controller đã live (P1/P2 xong, do nhóm khác cài chung cho Mandate 8) — nhưng vẫn không tự
bật `valkeyMigrationBridge`/`riotRedisBackfill`/`rollouts.enabled`+`useRollout` cho `cart`, không chạy
script nào trong `scripts/valkey/`, không đụng AWS/ElastiCache live. Blocker thật còn lại trước khi chạy
thật: PM approval (§4, PENDING) + quyền IAM `StartMigration`/`CompleteMigration` (P4, chưa đủ).
