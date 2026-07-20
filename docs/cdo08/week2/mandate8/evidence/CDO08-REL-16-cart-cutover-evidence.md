# CDO08-REL-16 — Cart/Checkout Cutover Smoke Test & Evidence

| Field | Value |
|---|---|
| Task | `[CDO08-REL-16][Subtask] Verify cart and checkout behavior with ElastiCache` |
| Liên quan | `CDO08-REL-16-valkey-cutover-plan.md`, `MANDATE-08-VALKEY-DECISIONS-Quan.md` (VK-03), `D8-PERF-03-cutover-contract.md` |
| Trạng thái | **CHƯA CHẠY** — đây là runbook + evidence skeleton, chưa có kết quả thật. Cutover chưa được phép thực hiện (xem gate ở `CDO08-REL-16-valkey-cutover-plan.md` §4, §7). |

## 1. Thứ tự Gate trước khi cutover (bắt buộc, không được đảo)

1. **Nạp ASM secret** `techx/tf4/elasticache-valkey` (host/port/address/tls_enabled/password) — do người có quyền `secretsmanager:PutSecretValue` thực hiện, không phải qua PR này.
2. Verify `ExternalSecret elasticache-valkey-secret` (`techx-tf4`) chuyển `Ready=True`:
   ```powershell
   kubectl get externalsecret elasticache-valkey-secret -n techx-tf4 -o jsonpath='{.status.conditions}'
   ```
3. Verify K8s Secret tồn tại — **chỉ liệt kê tên key, không in giá trị**:
   ```powershell
   kubectl get secret elasticache-valkey-secret -n techx-tf4 -o jsonpath='{range $k,$v := .data}{$k}{"`n"}{end}'
   ```
   Kỳ vọng thấy đủ 3 key: `valkey-address`, `password`, `tls_enabled`. Không chạy lệnh nào giải mã base64 giá trị ra evidence/PR/Slack.
4. `terraform apply` để bật `transit_encryption_mode=required` + `auth_token` trên `techx-tf4-valkey-cart` (qua pipeline `terraform-apply.yaml`, cần `TF_VALKEY_AUTH_TOKEN` secret đã tạo ở GitHub và khớp giá trị `password` đã nạp ở bước 1).
5. Merge PR code TLS (Subtask 2) → CI build lại image `cart` → cập nhật tag trong
   `environments/production/image-revisions.yaml` (gitops repo).
6. **Flip `managedData.enabled=true` + `managedData.valkey.enabled=true`** trong
   `environments/production/app-values.yaml` (gitops repo) — chỉ sau khi PM approval ở
   `CDO08-REL-16-valkey-cutover-plan.md` §4 chuyển APPROVED.
7. ArgoCD sync trong **low-traffic window**, theo dõi rollout `cart` (`replicas: 2`, rolling).

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
