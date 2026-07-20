# CDO08-REL-16 — Cart Cutover to ElastiCache Valkey

| Field | Value |
|---|---|
| Task | `[CDO08-REL-16][P0][Valkey] Migrate cart state to ElastiCache and verify app behavior` |
| Owner | Quân |
| Mandate | 8 (Managed Services Migration) |
| Liên quan | `MANDATE-08-VALKEY-DECISIONS-Quan.md` (ADR VK-01..VK-05), `REL-14-managed-infra-handoff-evidence.md` (§3.4), `sec-13-managed-data-secret-contract.md` (§2) |
| Trạng thái | Đang chuẩn bị — **chưa cutover** |

## 1. Mục tiêu

Chuyển `cart` service từ Valkey self-hosted (`valkey-cart:6379`, in-cluster, không auth) sang
ElastiCache private endpoint (`techx-tf4-valkey-cart`), đảm bảo add-to-cart / view cart / checkout vẫn
hoạt động đúng. `checkout` phụ thuộc đồng bộ vào `cart` trên critical path — lỗi cutover ảnh hưởng trực
tiếp tới khách hàng, nên tài liệu này chốt rõ quyết định + gate trước khi bất kỳ ai được phép cutover thật.

## 2. Quyết định Cart State (Subtask 1)

Đã có ADR riêng do chính Quân điền: `../adr/proposals/quan/MANDATE-08-VALKEY-DECISIONS-Quan.md`. REL-16 kế
thừa trực tiếp các quyết định đó, không mở lại:

| Quyết định | Đã chọn | Tóm tắt lý do |
|---|---|---|
| VK-01 Cart Data Policy | **B — Cold Cutover** | Cart chỉ 1 field, TTL 60 phút mỗi lần ghi — ephemeral by design. Cold cutover không cần dual-write/migrate dữ liệu thật. |
| VK-02 ElastiCache sizing | 2-node Multi-AZ `cache.t4g.micro` | `checkout` đọc cart đồng bộ trên critical path — cần auto-failover. |
| VK-03 Migration technique | A — RDB export/import, chỉ dùng pre-flight/smoke-test | Không migrate cart thật; chỉ seed dữ liệu mẫu để test connectivity trước cutover. |
| VK-04 Rollback strategy | C — Big Bang Revert | Repoint env về Valkey cũ, chấp nhận mất cart ghi trong window cutover→rollback. |
| VK-05 Eviction alert | CloudWatch 80% memory | Cache chứa cart đang hoạt động — cần buffer phản ứng sớm. |

**Kết luận cart state: KHÔNG migrate dữ liệu cart đang hoạt động.** Cutover là cold cutover — user đang có
giỏ hàng tại thời điểm repoint sẽ thấy giỏ trống, phải add lại item.

### Cập nhật hướng cutover (REL-16, so với ADR gốc)

ADR gốc (VK-01/VK-03) viết "không sửa code `cart`" với ý là không cần dual-write/backfill cho migrate dữ
liệu — điều đó vẫn đúng. Nhưng REL-16 **chọn bật TLS + auth token trước khi cutover**, không đi đường
plaintext dù ElastiCache hiện ở `transit_encryption_mode=preferred` (chấp nhận cả client không TLS). Vì
vậy cart **có** đổi code ở phần kết nối (`ssl=true` + password) — xem Subtask 2. Đã cập nhật ghi chú tương
ứng trong file ADR để không mâu thuẫn với quyết định này.

> **Lưu ý về `VALKEY-MIGRATION-PLAN.md`:** file draft này (`../implementation/drafts/VALKEY-MIGRATION-PLAN.md`)
> mô tả một kịch bản Blue-Green/Argo Rollouts + Online Migration + riot-redis backfill — đây là kiến trúc cho
> hướng **Active Cart Migration (VK-01 phương án A)**, đã bị ADR loại bỏ. REL-16 đi theo cold cutover (repoint
> env đơn giản, không rollout/bridge/backfill sống). Không sửa file draft đó trong phạm vi REL-16; nêu ở đây
> để tránh nhầm giữa 2 tài liệu.

## 3. Impact & Risk (Customer / Checkout path)

- **Ảnh hưởng khách hàng:** user đang thao tác giỏ hàng đúng lúc cutover mất cart, phải add lại item.
  Không ảnh hưởng trực tiếp tới **checkout success rate** (SLO chính) trừ vài giây đang repoint.
- **Giảm blast radius:** cutover trong **low-traffic window**; vì TTL cart là 60 phút, chỉ user thao tác
  trong ~1 giờ trước cutover bị ảnh hưởng.
- **Checkout trên critical path:** nếu ElastiCache endpoint/TLS/auth sai cấu hình, `cart` không kết nối
  được → mọi request `AddItem`/`GetCart` lỗi `FailedPrecondition` (xem `ValkeyCartStore.cs`) → checkout
  không lấy được cart → fail toàn bộ, không chỉ user đang online lúc cutover. Đây là lý do bắt buộc pre-flight
  connectivity test (§5.2) trước khi flip toggle production.

## 4. PM Approval Gate

| Field | Value |
|---|---|
| Cần approval cho | Cold cutover — chấp nhận mất cart đang hoạt động tại thời điểm cutover |
| Trạng thái | **PENDING** — chưa nhận được sign-off |
| Gate | **Không được cutover production (flip `managedData.enabled`/`managedData.valkey.enabled=true`) cho tới khi mục này chuyển thành APPROVED, kèm người duyệt + thời điểm.** |

## 5. Phạm vi REL-16 (bao gồm scope bổ sung)

REL-16 không chỉ cutover config — còn chịu trách nhiệm mảnh cuối của secret contract mà SEC-13 đã chuẩn
bị nhưng chưa nạp value thật:

1. Nạp value thật cho AWS Secrets Manager path `techx/tf4/elasticache-valkey` theo schema mở rộng
   (`host`, `port`, `address`, `tls_enabled`, `password` — password chỉ có khi ElastiCache bật `auth_token`).
2. Verify `ExternalSecret elasticache-valkey-secret` (namespace `techx-tf4`) chuyển `Ready=True`.
3. Verify K8s Secret `elasticache-valkey-secret` tồn tại — chỉ kiểm tra **metadata/key names**, không bao
   giờ in giá trị secret ra log/terminal output được lưu vào Git/Jira/Slack.
4. Chỉ bật `managedData.enabled=true` + `managedData.valkey.enabled=true` sau khi: cart hỗ trợ TLS (Subtask
   2), cart/checkout smoke test pass (Subtask 3), rollback path sẵn sàng (Subtask 4), và PM approval ở §4
   chuyển APPROVED.

**Không commit secret value vào Git/Jira/Slack dưới bất kỳ hình thức nào** (bao gồm cả trong evidence,
commit message, hay log dán vào PR).

## 6. Acceptance Criteria (Subtask 1)

- [x] Không cutover khi chưa chốt cart state decision — đã chốt ở §2 (kế thừa ADR VK-01/VK-04).
- [ ] PM approval có nếu chọn cold cutover — **PENDING**, xem §4.
- [x] Risk được ghi rõ cho customer/checkout path — xem §3.

## 7. Prerequisites / Blockers trước khi cutover thật

1. **PM approval** (§4) — PENDING.
2. **Quyền AWS Secrets Manager**: role SSO hiện tại (`TF4-SecurityIAMSSOManager`) không có quyền
   `secretsmanager:DescribeSecret`/`PutSecretValue` trên path `techx/tf4/elasticache-valkey` — cần role
   migration-operator/admin để thực hiện §5 mục 1.
3. **Auth token**: phải sinh 1 giá trị và đồng bộ vào cả Terraform (`var.valkey_auth_token`) lẫn ASM secret
   (`password`) — hai bên phải khớp nhau.
4. **CI rebuild `cart` image** sau khi merge code TLS (Subtask 2) → cập nhật tag trong
   `environments/production/image-revisions.yaml` trước khi flip toggle.
5. `infra/terraform/elasticache.tf` thuộc REL-14/CDO-04 — PR đổi file này cần CDO-04 review.

## 8. Rollback & Retention Boundary

_Xem Subtask 4 (bổ sung ở commit riêng)._
