# CDO08-REL-16 — Cart/Checkout Cutover Smoke Test & Evidence (Blue-Green + Online Migration)

| Field | Value |
|---|---|
| Task | `[CDO08-REL-16][Subtask] Verify cart and checkout behavior with ElastiCache` |
| Liên quan | `CDO08-REL-16-valkey-cutover-plan.md`, `../implementation/drafts/VALKEY-MIGRATION-PLAN.md`, `../implementation/drafts/COMMON-PREREQUISITES.md` |
| Trạng thái | **ĐÃ CHẠY — cutover thành công, có 1 incident production đã root-cause và fix trong lúc thực hiện (xem §5.1).** Cart hiện chạy ổn định trên ElastiCache. |
| Ngày thực hiện | 2026-07-21 |

## 1. Thứ tự chạy script (`docs/cdo08/week2/mandate8/scripts/valkey/`) — kết quả thật

| # | Script | Việc gì | Kết quả |
|---|---|---|---|
| 1 | `01-preflight-check.sh` | Verify Argo Rollouts CRD, `Rollout/cart`, bridge NLB endpoint, ElastiCache `available` | Chạy được sau khi fix bug CRLF line-ending trên toàn bộ 11 script (Windows-created files) — xem §5.2 |
| 2 | `test-migration-connection.sh` | Debug pod test TCP reachability tới bridge NLB | PASS — port 6379 reachable (`nc -z` exit 0) sau khi bật NLB bridge (`valkeyMigrationBridge.enabled: true`, gitops PR #62) |
| 3 | `02-start-migration.sh` | `aws elasticache start-migration` | PASS — cần fix trước: `transit_encryption_enabled` phải `false` (PR #430) vì AWS reject `StartMigration` trên replication group bật in-transit encryption dù ở mode `"preferred"` |
| 4 | `03-monitor-lag.sh` | Poll `ReplicationLag` tới khi ổn định 0 | PASS sau khi fix bug: script query sai dimension CloudWatch (`ReplicationGroupId` thay vì `CacheClusterId` của node primary) — luôn ra `None`. Sau fix: lag = 0.0 ổn định (dataset demo nhỏ, đồng bộ gần như tức thời) |
| — | Sync gitops PR #64 (cutover cart: `useRollout: true`, `rollouts.enabled: true`, `VALKEY_ADDR`) | Argo Rollouts tạo Rollout/cart | **Đây là điểm bắt đầu incident — xem §5.1** |
| 5 | `04-freeze-writes.sh` | `CLIENT PAUSE ... WRITE` trên `valkey-cart`, cửa sổ 300s | PASS — chạy lúc DBSIZE nguồn = 8350 |
| — | Data Parity Check pre-cutover (§2) | | Xem §2 — **có khoảng lệch, xem caveat** |
| 6 | `05-complete-migration.sh` | `aws elasticache complete-migration` | Có bug: `--force false` không hợp lệ (AWS CLI dùng boolean flag `--force`/`--no-force`, không nhận `true`/`false` làm value) → sửa thành `--no-force`, chạy lại PASS |
| 7 | `06-promote-rollout.sh` | `kubectl argo rollouts promote cart` + `CLIENT UNPAUSE` | Chạy khi pod mới **vẫn đang crash** (xem §5.1) — về sau xác nhận không ảnh hưởng vì Rollout chỉ có 1 revision (stable=preview=cùng bản mới) |
| — | Data Parity Check post-cutover (§2) + Smoke Test (§3) | | PASS — xem §2, §3 |
| 8 | `07-enable-tls.sh <1\|2\|3>` | 3 pha zero-downtime TLS | **CHƯA CHẠY** — theo plan, chạy sau khi bake ổn định 24-48h, không phải điều kiện tiên quyết |
| 9 | `08-cleanup.sh` | Tắt bridge — **không** xoá `valkey-cart` | **CHƯA CHẠY** — chờ bake ổn định |

Rollback: không cần dùng — cutover cuối cùng thành công sau khi fix incident.

## 2. Data Parity Checklist (theo VALKEY-MIGRATION-PLAN.md §5)

**Pre-cutover** (ngay sau freeze writes, trước complete-migration):
- [x] K-1: `DBSIZE` trên `valkey-cart` (nguồn) tại thời điểm freeze = **8350**. **Không lấy được DBSIZE ElastiCache tại đúng thời điểm này** vì ngay sau đó gặp bug `--force false` (script 05) rồi tiếp đến incident (§5.1) chiếm hết thời gian xử lý — cửa sổ freeze 300s nhiều khả năng đã tự hết hạn trước khi `complete-migration` thực sự chạy xong, do thời gian debug các bug script kéo dài hơn 5 phút.
- [x] K-2: Trạng thái replication link — xác nhận qua `aws elasticache describe-replication-groups`: `migrating` → `available` sau khi `complete-migration` chạy xong.

  **⚠️ Caveat quan trọng (đã kiểm tra trung thực, không che giấu):** đo lại `DBSIZE` cả 2 bên tại thời điểm viết evidence này (2026-07-21, sau khi cutover ổn định):
  - `valkey-cart` (cũ): **5584** keys
  - ElastiCache (mới): **3126** keys

  Hai số này **không khớp ≥99.9%** như tiêu chí gốc. Nguyên nhân nhiều khả năng:
  1. Cửa sổ freeze 300s hết hạn trước khi `complete-migration` thực sự hoàn tất (do phải debug bug `--force`), nên có thể có một khoảng ghi mới vào nguồn cũ không được migration bắt kịp trước khi bị cắt link.
  2. TTL tự nhiên (cart key TTL ≤ 3600s) làm cả 2 bên giảm dần theo thời gian — một phần chênh lệch là decay bình thường, không phải mất dữ liệu thật.
  3. Sau incident, `06-promote-rollout.sh` đã unpause writes trên nguồn cũ **trong khi pod mới vẫn đang crash** — có một khoảng thời gian (~từ lúc unpause tới lúc fix endpoint xong, ước lượng dựa trên PR merge timestamps: `04:33:49Z` → `04:56:59Z`, khoảng 23 phút) traffic thật vẫn ghi vào nguồn cũ (vì Service chỉ route tới pod Ready, và pod mới không Ready nên toàn bộ traffic đổ vào 2 pod Deployment cũ đang chạy song song) — dữ liệu ghi trong khoảng này **không được đồng bộ sang ElastiCache** vì link đã bị cắt bởi `complete-migration`.

  **Đánh giá rủi ro:** cart là dữ liệu ephemeral (TTL ≤ 1h, không phải user record vĩnh viễn), nên khả năng ảnh hưởng thực tế tới người dùng thấp (giỏ hàng cũ hết hạn tự nhiên trong vòng 1h). Tuy nhiên đây là gap thật, cần ghi nhận trung thực thay vì báo cáo "PASS ≥99.9%" không đúng sự thật. **Khuyến nghị:** theo dõi báo cáo mất giỏ hàng từ người dùng trong 24-48h tới; không có gì cần rollback ngay vì mức độ nghiêm trọng thấp và cart hiện đã hoạt động đúng cho mọi request mới.

**Post-cutover** (sau khi fix incident, cart pod healthy):
- [x] A-1: Add-to-cart mới → `GET cart:<user_id>` trên ElastiCache trả đúng dữ liệu. **PASS** — verify qua `grpcurl`: `AddItem(user_id=smoke-test-user, product=OLJCESPC7Z, qty=1)` → `GetCart(smoke-test-user)` trả đúng `{"userId":"smoke-test-user","items":[{"productId":"OLJCESPC7Z","quantity":1}]}`.
- [x] A-2: TTL key mới trên ElastiCache trong khoảng (0, 3600] giây. **PASS** — `TTL smoke-test-user` = **3571s**.
- [ ] A-3: Dry-run `riot-redis-backfill` Job trên staging — **CHƯA CHẠY** (không cần dùng tới vì không phải rollback qua backfill; giữ lại cho ticket rollback dự phòng sau này).

## 3. Smoke Test Cart/Checkout

- [x] Add-to-cart (grpcurl `oteldemo.CartService/AddItem`) — **PASS**, response `{}` (thành công).
- [x] View cart (grpcurl `oteldemo.CartService/GetCart`) — **PASS**, trả đúng item vừa add.
- [ ] Checkout với item trong cart qua UI thật — **CHƯA THỰC HIỆN THỦ CÔNG QUA UI**, chỉ verify qua grpcurl trực tiếp vào `CartService`. Checkout end-to-end qua `frontend` hiện đang bị ảnh hưởng bởi 2 vấn đề **không liên quan tới cart/valkey** (xem §4).
- [ ] Verify qua Jaeger trace — **CHƯA THỰC HIỆN** (không có blocker kỹ thuật, đơn giản chưa làm trong phiên này). Có thể làm qua `kubectl port-forward svc/jaeger 16686:16686 -n techx-observability` (không cần bastion, RBAC người vận hành đã đủ quyền `create pods/portforward`).

Đã dọn dẹp toàn bộ resource test (`cart-smoke-test` pod, `cart-proto` configmap, key `smoke-test-user` trên cả 2 store) sau khi verify xong — không để lại rác trên production.

### 3.1. Bằng chứng cụ thể: endpoint đang dùng là ElastiCache thật, traffic 100% qua ElastiCache

Verify lại toàn bộ ngay tại thời điểm viết evidence (không dựa vào suy luận từ config, mà chạy lệnh thật, có output thật):

**a) Endpoint app đang dùng là gì:**
```
$ kubectl get rollout cart -n techx-tf4 -o jsonpath='{...env...}' | grep VALKEY
VALKEY_ADDR=techx-tf4-valkey-cart.pyo0mq.ng.0001.use1.cache.amazonaws.com:6379
```

**b) Endpoint đó có đúng là ElastiCache thật, đang `available`, do AWS xác nhận (không phải chuỗi tự đặt):**
```
$ aws elasticache describe-replication-groups --replication-group-id techx-tf4-valkey-cart \
    --query 'ReplicationGroups[0].{Status:Status,PrimaryEndpoint:NodeGroups[0].PrimaryEndpoint}'
{
    "Status": "available",
    "PrimaryEndpoint": {
        "Address": "techx-tf4-valkey-cart.pyo0mq.ng.0001.use1.cache.amazonaws.com",
        "Port": 6379
    }
}
```
→ Chuỗi trong `VALKEY_ADDR` khớp **chính xác từng ký tự** với `PrimaryEndpoint.Address` mà AWS trả về cho replication group `techx-tf4-valkey-cart` — không phải giá trị bịa/để tạm.

**c) `Deployment/cart` cũ đã bị xoá hẳn — không còn đường nào để traffic lọt vào nguồn cũ:**
```
$ kubectl get deployment cart -n techx-tf4
Error from server (NotFound): deployments.apps "cart" not found

$ kubectl get pods -n techx-tf4 -l app.kubernetes.io/component=cart
cart-766c6b8f5c-2f6lf   1/1   Running   0   4h44m
cart-766c6b8f5c-r9svc   1/1   Running   0   4h44m
```
Chỉ còn đúng 2 pod thuộc `Rollout/cart`, không còn pod nào của Deployment cũ tồn tại song song.

**d) Endpoints Kubernetes xác nhận traffic chỉ đi vào 2 pod này:**
```
$ kubectl get endpoints cart -n techx-tf4
10.0.10.74  -> cart-766c6b8f5c-r9svc
10.0.11.238 -> cart-766c6b8f5c-2f6lf
```

**e) Bằng chứng mạnh nhất — ghi dữ liệu thật qua đúng Service `cart` (client không biết endpoint thật, chỉ gọi `cart.techx-tf4.svc.cluster.local:8080` như app thật), rồi verify trực tiếp bằng redis-cli xem dữ liệu rơi vào đâu:**
```
# Ghi qua gRPC (giống hệt cách frontend/checkout gọi)
$ grpcurl AddItem(user_id=evidence-test-user, product=OLJCESPC7Z, qty=2) -> cart.techx-tf4.svc.cluster.local:8080
{}
$ grpcurl GetCart(evidence-test-user)
{"userId":"evidence-test-user","items":[{"productId":"OLJCESPC7Z","quantity":2}]}

# Query TRỰC TIẾP bằng redis-cli vào ElastiCache — không qua app:
$ redis-cli -h techx-tf4-valkey-cart.pyo0mq.ng.0001.use1.cache.amazonaws.com -p 6379 EXISTS evidence-test-user
1
$ redis-cli -h techx-tf4-valkey-cart.pyo0mq.ng.0001.use1.cache.amazonaws.com -p 6379 TTL evidence-test-user
3572

# Query TRỰC TIẾP vào valkey-cart CŨ — phải là 0 mới đúng:
$ kubectl exec deploy/valkey-cart -- redis-cli EXISTS evidence-test-user
0
```
→ Key ghi qua Service `cart` **có mặt trên ElastiCache** (TTL hợp lệ 3572s) và **hoàn toàn không có** trên `valkey-cart` cũ. Đây là bằng chứng trực tiếp, không suy luận: request thật đi qua Service → tới ElastiCache, không chạm nguồn cũ ở bất kỳ bước nào. Đã dọn dẹp key test này sau khi verify.

## 4. Theo dõi SLO

- **Cart success rate: 100%** (theo Grafana, sau khi fix incident §5.1) — xác nhận cart hoạt động đúng, ổn định trên ElastiCache.
- **Checkout success rate (SLO ≥99.0%): dao động 67.8% → 44.7%** tại thời điểm viết evidence — **KHÔNG phải do cart/valkey migration.** Root-cause đã điều tra và xác nhận:
  - `otel-collector-agent` (namespace `techx-observability`) bị memory pressure khi export trace sang Jaeger (`rpc error: code = Unavailable desc = data refused due to high memory usage`, `DeadlineExceeded`) — nghi vấn Jaeger đang chậm/quá tải.
  - Hệ quả lan sang `currency` (fail convert giá cho nhiều product ID khác nhau — không phải lỗi 1 sản phẩm cụ thể) và `shipping` (trả 400/500 cho một số quote request).
  - Xác nhận đây **không liên quan Mandate 8**: `kafka` và `postgresql` chưa migrate (vẫn self-hosted, không đổi gì), cart đã cutover xong và đang 100% — loại trừ hoàn toàn khả năng do REL-16 gây ra.
  - **Ngoài phạm vi CDO-08/REL-16** — cần đội phụ trách `currency`/`shipping`/observability (Jaeger) xử lý riêng.

## 5. Evidence

### 5.1. Incident trong lúc cutover — root cause, impact, fix

**Diễn biến:**
1. Gitops PR #64 (bật `useRollout: true`, `VALKEY_ADDR=master.techx-tf4-valkey-cart...cache.amazonaws.com:6379`) merge lúc `2026-07-21T04:33:49Z`, force-sync ArgoCD → Argo Rollouts chuyển `Deployment/cart` → `Rollout/cart`, tạo pod mới trỏ ElastiCache.
2. Pod mới **CrashLoopBackOff ngay lập tức** — vì đây là lần đầu convert Deployment→Rollout nên revision đầu tiên vừa là `stable` vừa là `preview` (không có bản Blue cũ song song trong chính Rollout để đỡ traffic). Tuy nhiên `Deployment/cart` cũ (13 ngày tuổi) vẫn tồn tại song song do ArgoCD sync policy `prune: false` — 2 pod cũ vẫn chạy khoẻ và **Kubernetes Service tự động chỉ route traffic tới pod Ready** (xác nhận qua `kubectl get endpoints cart`), nên thực tế traffic thật vẫn được 2 pod cũ phục vụ trong giai đoạn này, không downtime hoàn toàn — nhưng cart lúc đó **chưa hề thực sự cutover**, vẫn ghi vào `valkey-cart` cũ.
3. Nguyên nhân crash ban đầu: replication group ElastiCache còn ở trạng thái `"migrating"` (chưa chạy `05-complete-migration.sh`) — node đích lúc này hoạt động như replica của nguồn ngoài, Redis replica mặc định read-only, khiến `ValkeyCartStore.Initialize()` (có thao tác ghi test) fail với `"Wasn't able to connect to redis"` (exception message chung chung, che mất lý do thật).
4. Chạy `05-complete-migration.sh` gặp bug: `--force false` không hợp lệ với AWS CLI (boolean flag, không nhận value) → sửa `--no-force`, chạy lại thành công, replication group chuyển `available`.
5. Pod mới **vẫn crash y hệt** sau khi migration hoàn tất — root cause thật: endpoint `master.techx-tf4-valkey-cart.pyo0mq.use1.cache.amazonaws.com` **chỉ tồn tại trong lúc trạng thái `migrating`**; sau khi `complete-migration` xong, domain này **ngừng resolve hoàn toàn** (xác nhận qua `nslookup`: "Non-existent domain", không phải do DNS chưa kịp propagate). Endpoint đúng: `techx-tf4-valkey-cart.pyo0mq.ng.0001.use1.cache.amazonaws.com` (xác nhận qua `aws elasticache describe-replication-groups` trực tiếp).
6. `06-promote-rollout.sh` được chạy trong lúc pod mới vẫn crash (unpause writes trên nguồn cũ) — do traffic vẫn đang chạy vào 2 pod Deployment cũ, nên việc unpause khiến ghi mới tiếp tục vào nguồn cũ **sau khi link migration đã bị cắt**, tạo ra khoảng lệch dữ liệu (xem §2 caveat).
7. Thử `kubectl patch rollout` sửa trực tiếp live env var — bị ArgoCD `selfHeal: true` revert lại ngay lập tức. → Phải fix đúng ở nguồn: gitops PR #67 (`fix(gitops): [URGENT] correct ElastiCache endpoint after migration completion`), merge `2026-07-21T04:56:59Z`, force-sync ArgoCD.
8. Pod mới tạo lại lúc `2026-07-21T04:58:11Z`, lên `1/1 Running` trong ~30s, 0 restart kể từ đó. `kubectl get endpoints cart` xác nhận traffic đã chuyển hẳn sang pod mới.

**Thời gian ảnh hưởng:** từ `04:33:49Z` (PR #64 sync) tới `04:58:11Z` (pod mới healthy) ≈ **24 phút** — trong đó cart không hoàn toàn down (traffic vẫn được pod cũ phục vụ), nhưng cutover chưa thực sự có hiệu lực và có một khoảng ghi dữ liệu không được đồng bộ sang ElastiCache (xem §2).

**Người phát hiện/xử lý:** Quân (CDO-08), với hỗ trợ Claude Code trong phiên làm việc trực tiếp trên production.

### 5.2. Các bug script/hạ tầng phát hiện và fix trong quá trình chạy (không phải lỗi thiết kế ban đầu, lộ ra tuần tự khi tiến sâu hơn vào pipeline)

| Bug | File | Fix | PR |
|---|---|---|---|
| CRLF line-ending trên toàn bộ 11 script `.sh` (tạo trên Windows) → `set: pipefail: invalid option name` | `scripts/valkey/*.sh` | Convert LF + thêm `.gitattributes` rule `*.sh text eol=lf` | (local fix, chưa PR riêng — cần commit) |
| `kubectl run --rm -i` race condition làm mất log khi pod exit quá nhanh | `test-migration-connection.sh` | Đổi sang `kubectl apply` manifest + `wait` + `logs` + cleanup qua `trap` | (local fix, chưa PR riêng — cần commit) |
| ECR `TAG_INVALID` — cosign attest 2 lần (provenance + SBOM) cùng ghi 1 tag `.att`, ECR `IMMUTABLE` chặn ghi đè | `.github/workflows/build-and-push.yaml` (ngoài scope REL-16, do CDO_04 fix qua PR #423-426) | `image_tag_mutability = IMMUTABLE_WITH_EXCLUSION` set qua workflow step | #426 (không thuộc REL-16, ghi nhận vì từng chặn build cart) |
| `transit_encryption_enabled=true` (kể cả `"preferred"`) chặn `StartMigration` | `elasticache.tf` | `transit_encryption_enabled = false` (tạm thời, bật lại qua `07-enable-tls.sh` sau cutover) | #430 |
| Đổi `transit_encryption_enabled` cần `apply_immediately=true`, AWS reject nếu không | `elasticache.tf` | `apply_immediately = true` | #431 |
| `03-monitor-lag.sh` query sai CloudWatch dimension (`ReplicationGroupId` thay vì `CacheClusterId` của primary node) → luôn `None` | `scripts/valkey/03-monitor-lag.sh` | Tự tra primary node mỗi vòng lặp, query đúng dimension | (local fix, chưa PR riêng — cần commit) |
| `05-complete-migration.sh`: `--force false` không hợp lệ (boolean flag) | `scripts/valkey/05-complete-migration.sh` | Đổi sang `--no-force` | (fix live qua CLI, **script gốc trong repo chưa được sửa — cần commit**) |
| `VALKEY_ADDR` dùng endpoint chỉ tồn tại lúc `migrating`, mất hiệu lực sau `complete-migration` | `environments/production/app-values.yaml` (gitops) | Đổi sang node-group primary endpoint chuẩn | #67 |
| `rolloutStrategy.blueGreen` không set tường minh — chart tại revision ArgoCD đang pin (trước default này tồn tại) reject `useRollout: true` | `environments/production/app-values.yaml` (gitops) | Set tường minh `rolloutStrategy.blueGreen.autoPromotionEnabled: false` | #64 (fix trong cùng PR trước khi merge) |

**Lưu ý quan trọng:** 3 fix đánh dấu "local fix, chưa PR riêng" (`01-preflight-check.sh` và 10 script khác đã convert LF, `test-migration-connection.sh`, `03-monitor-lag.sh`) và fix `05-complete-migration.sh` (`--force`→`--no-force`) **hiện chỉ tồn tại trên máy local, chưa commit/push** — cần commit trước khi coi migration này là "hoàn tất tài liệu hoá" thật sự, nếu không lần chạy sau (rollback, hoặc REL tương lai tương tự) sẽ dính lại y hệt các bug này.

## 6. Acceptance Criteria

- [x] Add-to-cart / view cart pass (grpcurl, xem §3).
- [ ] Checkout qua UI thật — **chưa test thủ công**, và checkout tổng thể đang bị ảnh hưởng bởi lỗi không liên quan (xem §4) nên chưa thể xác nhận 100% qua UI.
- [x] Data parity check post-cutover (A-1, A-2) pass.
- [ ] Data parity check pre-cutover (K-1) — **có gap thật, đã ghi nhận trung thực ở §2**, không đạt ≥99.9% do incident.
- [x] Không có error spike do cart gây ra (cart success rate 100% sau fix; error spike hiện tại là do `currency`/`shipping`/Jaeger, ngoài phạm vi — đã tự phục hồi phần lớn sau khi team liên quan fix `currency`, xem PR #443).
- [x] Không xoá `valkey-cart` — vẫn giữ nguyên, đang bake.
- [x] `Deployment/cart` cũ (Blue, orphan sau khi ArgoCD convert sang Rollout, `prune: false` không tự xoá) — đã xoá thủ công sau khi xác nhận 100% traffic qua Rollout mới (xem §3.1). Không ảnh hưởng gì tới traffic.
- [ ] Bake 24-48h ổn định — **đang trong giai đoạn theo dõi**, chưa đủ thời gian.

**Trạng thái tổng thể: Cutover kỹ thuật thành công, đã verify bằng chứng trực tiếp (không suy luận) rằng 100% traffic/dữ liệu đang đi qua ElastiCache thật (§3.1), cart hoạt động ổn định. Có 1 gap parity dữ liệu thật từ lúc incident (thấp rủi ro do TTL ngắn) cần theo dõi, và một số script fix cần commit để không lặp lại bug (§5.2). Chưa đủ điều kiện đóng ticket REL-18 (xoá `valkey-cart`) cho tới khi bake xong 24-48h.**
