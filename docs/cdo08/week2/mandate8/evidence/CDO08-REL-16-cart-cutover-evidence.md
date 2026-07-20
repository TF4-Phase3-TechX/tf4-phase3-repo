# CDO08-REL-16 — Cart/Checkout Cutover Smoke Test & Evidence

| Field | Value |
|---|---|
| Task | `[CDO08-REL-16][Subtask] Verify cart and checkout behavior with ElastiCache` |
| Liên quan | `CDO08-REL-16-valkey-cutover-plan.md`, `MANDATE-08-VALKEY-DECISIONS-Quan.md` (VK-03), `D8-PERF-03-cutover-contract.md` |
| Trạng thái | **CHƯA CHẠY** — đây là runbook + evidence skeleton, chưa có kết quả thật. Cutover chưa được phép thực hiện (xem gate ở `CDO08-REL-16-valkey-cutover-plan.md` §4, §7). |

## 1. Runbook thực thi từng bước (Operator) — bắt buộc theo đúng thứ tự

### Bước 0 — Review & merge chuẩn bị (chưa cutover)
1. Review 4 commit trên nhánh `cdo08-rel-16-valkey-elasticache` (app repo) + 1 commit ở gitops repo (PR).
2. Xin **PM approval** cho cold cutover (mất active cart) — cập nhật `CDO08-REL-16-valkey-cutover-plan.md`
   §4 từ PENDING → APPROVED kèm người duyệt + thời điểm.
3. Quyền `secretsmanager:DescribeSecret`/`CreateSecret`/`PutSecretValue` trên `techx/tf4/elasticache-valkey`
   cho role SSO `TF4-SecurityIAMSSOManager` — đã cấp.
4. Tạo GitHub secret `TF_VALKEY_AUTH_TOKEN` (repo settings) — cần trước khi `terraform apply` chạy được
   với `auth_token` thật.
5. Merge PR app repo sau khi CI xanh + CDO-04 review phần `elasticache.tf`.
6. PR gitops repo (thêm key `password`/`tls_enabled` vào ExternalSecret) — merge ngay hoặc giữ tới sát
   Bước 2 đều được, nhưng nếu ArgoCD sync PR này **trước khi** ASM secret có đủ 3 property, ExternalSecret
   `elasticache-valkey-secret` sẽ ở trạng thái `Ready=False`/Degraded cho tới khi Bước 2 hoàn tất (không
   phải lỗi cố định — tự hết khi ASM có đủ value, nhưng nên biết trước để không hoảng khi thấy Degraded).

### Bước 1 — Sinh auth token
7. Sinh 1 chuỗi ngẫu nhiên ≥16 ký tự, ví dụ:
   ```powershell
   openssl rand -base64 32
   ```
   Dùng **cùng 1 giá trị** cho cả Bước 2 và Bước 3 — không được lệch nhau.

### Bước 2 — Nạp ASM secret

8. Tạo secret `techx/tf4/elasticache-valkey` (secret chưa tồn tại — dùng `create-secret`, không phải
   `put-secret-value`). Endpoint dùng đúng giá trị đã handoff ở REL-14
   (`REL-14-managed-infra-handoff-evidence.md` §3.4), primary endpoint hiện tại không đổi khi chỉ
   update `transit_encryption_mode`/`auth_token` (in-place, không destroy/recreate):
   ```powershell
   aws secretsmanager create-secret --name techx/tf4/elasticache-valkey `
     --secret-string '{"host":"<endpoint>","port":"6379","address":"<endpoint>:6379","tls_enabled":"true","password":"<auth_token_vừa_sinh>"}'
   ```
   **Không** dán giá trị thật vào PR/Slack/Jira. Nếu cần cập nhật lại sau khi secret đã tồn tại (ví dụ
   xoay `auth_token`), dùng `put-secret-value` với cùng `--secret-id`.

### Bước 3 — Terraform apply (bật TLS required + auth_token)
9. Set GitHub secret `TF_VALKEY_AUTH_TOKEN` = auth token ở Bước 1 (**phải khớp** giá trị `password` ở
   Bước 2).
10. Sau khi PR merge, pipeline `terraform-apply.yaml` tự chạy → xác nhận output chỉ update in-place RG
    `techx-tf4-valkey-cart`, không destroy/recreate.
11. **Verify runtime AWS đã áp dụng đúng config, không chỉ chờ ở hàng đợi** — `apply_immediately = false`
    trên RG này, nghĩa là thay đổi có thể bị xếp vào maintenance window (`sun:19:00-sun:20:00`) thay vì có
    hiệu lực ngay:
    ```powershell
    aws elasticache describe-replication-groups --replication-group-id techx-tf4-valkey-cart `
      --query 'ReplicationGroups[0].[Status,TransitEncryptionMode,PendingModifiedValues]'
    ```
    Kỳ vọng `TransitEncryptionMode` = `required` và `PendingModifiedValues` **rỗng** (không còn thay đổi
    nào đang chờ áp dụng) trước khi đi tiếp Bước 4 trở đi. Nếu vẫn còn pending và cần có hiệu lực ngay
    trong change window hiện tại (không chờ tới maintenance window kế tiếp) — **phải xin CDO-04/PM approve
    trước** khi chạy `aws elasticache modify-replication-group --replication-group-id techx-tf4-valkey-cart
    --apply-immediately` (có thể gây gián đoạn ngắn do failover).

### Bước 4 — Verify secret sync
12. ```powershell
    kubectl get externalsecret elasticache-valkey-secret -n techx-tf4 -o jsonpath='{.status.conditions}'
    ```
    Kỳ vọng `Ready=True`.
13. ```powershell
    kubectl get secret elasticache-valkey-secret -n techx-tf4 -o jsonpath='{range $k,$v := .data}{$k}{"`n"}{end}'
    ```
    Kỳ vọng đủ 3 key: `valkey-address`, `password`, `tls_enabled`. **Không** decode giá trị ra ngoài.

### Bước 5 — Rebuild image cart
14. Sau khi PR code TLS (commit `7cd84df`) merge vào main → CI tự build image `cart` mới.
15. Cập nhật tag mới trong `environments/production/image-revisions.yaml` (gitops repo).

### Bước 6 — Pre-flight connectivity test (bắt buộc trước khi flip toggle)
16. Chạy test kết nối TLS+auth theo §2 bên dưới — phải thấy `PONG` mới đi tiếp.

### Bước 7 — Chọn low-traffic window & flip toggle
17. Đặt `managedData.enabled=true` + `managedData.valkey.enabled=true` trong
    `environments/production/app-values.yaml` (gitops repo), commit + push.
18. Force ArgoCD sync `techx-corp` Application.
19. ```powershell
    kubectl rollout status deployment/cart -n techx-tf4
    ```
    Chờ rollout xong, giữ `2/2 Ready`.

### Bước 8 — Smoke test
20. Chạy add-to-cart / view cart / checkout theo §3 bên dưới.
21. Kiểm tra trace Jaeger — xác nhận span Redis trỏ ElastiCache endpoint, không lỗi (§3.4).
22. Theo dõi Grafana checkout success rate + p95 latency theo §4 trong ít nhất vài phút đầu.

### Bước 9 — Quyết định giữ hay rollback
23. Nếu bất kỳ ngưỡng nào ở Bước 8 fail → rollback ngay theo `CDO08-REL-16-valkey-cutover-plan.md` §8.1
    (tắt toggle → sync → rolling restart → verify lại trên Valkey cũ) — không debug trên production
    trước.
24. Nếu pass → điền evidence thật vào §5 bên dưới (screenshot + thời điểm), giữ nguyên Valkey in-cluster
    **không xoá** trong 24–48h tiếp theo.

### Bước 10 — Sau 24-48h bake ổn định
25. Nếu không rollback trong suốt window → ghi lại timestamp cutover + xác nhận không rollback vào §5 —
    đây là input để REL-18 được phép decommission `valkey-cart`/PVC (xem
    `CDO08-REL-16-valkey-cutover-plan.md` §8.2).

## 2. Pre-flight connectivity test (trước khi flip toggle thật, theo VK-03)

Chạy từ 1 Job/debug pod ngắn hạn trong `techx-tf4` (VAP-compliant: non-root, pinned digest, resource
limits, drop ALL capabilities) để xác nhận kết nối TLS+auth thông trước khi đụng traffic thật:

```bash
# Cần grpcurl/redis-cli trong image debug pod, không có sẵn trên máy vận hành hiện tại.
redis-cli -h <elasticache_endpoint> -p 6379 --tls -a "<auth_token>" PING
# Expected: PONG
```

Không repoint traffic thật (bước 6 ở §1) khi bước này chưa PASS.

## 3. Smoke test Cart/Checkout (sau khi cutover, trong observation window)

### 3.1. Add-to-cart

```bash
grpcurl -plaintext -d '{"user_id":"smoke-test-user","item":{"product_id":"OLJCESPC7Z","quantity":1}}' \
  cart.techx-tf4.svc.cluster.local:8080 oteldemo.CartService/AddItem
```
- **Tiêu chuẩn đạt:** RPC trả về thành công (không lỗi `FailedPrecondition`/`Can't access cart storage`).

### 3.2. View cart

```bash
grpcurl -plaintext -d '{"user_id":"smoke-test-user"}' \
  cart.techx-tf4.svc.cluster.local:8080 oteldemo.CartService/GetCart
```
- **Tiêu chuẩn đạt:** Trả về đúng item vừa add ở 3.1 (`OLJCESPC7Z`, quantity 1).

### 3.3. Checkout với item trong cart

- Thực hiện qua `frontend`/`checkout` service (UI hoặc gRPC `PlaceOrder`) với cùng `user_id`.
- **Tiêu chuẩn đạt:** Checkout trả về thành công (order xác nhận), cart được clear sau khi checkout xong
  (theo hành vi `EmptyCartAsync` hiện có).

### 3.4. Xác nhận qua Jaeger trace (theo VK-03)

Tìm trace của cùng `user_id` trên Jaeger, xác nhận span `cart` → Redis/Valkey client thực sự trỏ tới
ElastiCache endpoint (không phải `valkey-cart:6379` cũ), và không có span lỗi (`error=true`).

## 4. Theo dõi SLO trong cutover window

| Gate | Ngưỡng | Nguồn |
|---|---|---|
| Checkout success rate | ≥ 99% (sliding 1 phút) | Prometheus/Grafana (theo `D8-PERF-03-cutover-contract.md` §4.1) |
| p95 checkout latency | Stop condition nếu > 1000ms cảnh báo, > 2000ms rollback | `D8-PERF-03-cutover-contract.md` §6.1 |
| Log lỗi `cart` | Không có `Wasn't able to connect to redis` / `Can't access cart storage` sau thời điểm cutover | `kubectl logs` / log aggregator |

Nếu chạm bất kỳ ngưỡng nào ở trên → thực hiện rollback ngay theo
`CDO08-REL-16-valkey-cutover-plan.md` §8 (Subtask 4), điều tra sau.

## 5. Evidence (điền sau khi chạy thật)

> Theo format 3 câu hỏi chuẩn của team: **Đã làm gì? / Kiểm chứng bằng cách nào? / Evidence nằm ở đâu?**

- **Đã làm gì?** _(chưa chạy)_
- **Kiểm chứng bằng cách nào?** _(chưa chạy)_
- **Evidence nằm ở đâu?** _(chưa chạy — khi có, đặt screenshot/log tại
  `docs/cdo08/week2/mandate8/evidence/images/rel-16/` và link vào đây)_

| Screenshot # | Lệnh | Thời điểm (UTC) | File |
|---|---|---|---|
| 1 | ExternalSecret Ready=True | _(pending)_ | _(pending)_ |
| 2 | K8s secret key list (metadata-only) | _(pending)_ | _(pending)_ |
| 3 | Pre-flight TLS+auth connectivity PASS | _(pending)_ | _(pending)_ |
| 4 | Add-to-cart PASS | _(pending)_ | _(pending)_ |
| 5 | View cart PASS | _(pending)_ | _(pending)_ |
| 6 | Checkout PASS | _(pending)_ | _(pending)_ |
| 7 | Jaeger trace trỏ ElastiCache endpoint | _(pending)_ | _(pending)_ |
| 8 | Grafana checkout success rate trong window | _(pending)_ | _(pending)_ |

## 6. Acceptance Criteria (Subtask 3)

- [ ] Add-to-cart pass.
- [ ] View cart pass.
- [ ] Checkout pass.
- [ ] Không có error spike rõ trong logs/dashboard.

Tất cả 4 mục trên đang **CHƯA THỰC HIỆN** — chỉ là runbook chuẩn bị. Cutover thật do owner (Quân) tự
drive sau khi PR được review và các gate ở §1 hoàn tất.
