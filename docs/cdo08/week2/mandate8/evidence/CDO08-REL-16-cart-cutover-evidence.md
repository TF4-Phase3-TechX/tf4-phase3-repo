# CDO08-REL-16 — Cart/Checkout Cutover Smoke Test & Evidence (Blue-Green + Online Migration)

| Field | Value |
|---|---|
| Task | `[CDO08-REL-16][Subtask] Verify cart and checkout behavior with ElastiCache` |
| Liên quan | `CDO08-REL-16-valkey-cutover-plan.md`, `../implementation/drafts/VALKEY-MIGRATION-PLAN.md`, `../implementation/drafts/COMMON-PREREQUISITES.md` |
| Trạng thái | **HOÀN TẤT cutover.** Cart chạy ổn định trên ElastiCache, 100% traffic đã xác nhận qua ElastiCache (xem §2). Bridge đã tắt. TLS pha 1-3 và REL-18 (xoá `valkey-cart`) còn lại, phụ thuộc điều kiện ngoài (xem §5). |
| Ngày thực hiện | 2026-07-21 |

## 1. Kết quả chạy từng bước

| # | Bước | Kết quả |
|---|---|---|
| 1 | Preflight check | PASS |
| 2 | Test kết nối bridge NLB | PASS |
| 3 | Bắt đầu Online Migration (`start-migration`) | PASS |
| 4 | Theo dõi replication lag | PASS — ổn định 0 |
| 5 | Cutover cart sang Rollout Blue-Green, trỏ ElastiCache | PASS |
| 6 | Freeze writes trên `valkey-cart` | PASS |
| 7 | Hoàn tất migration (`complete-migration`) | PASS |
| 8 | Promote rollout (chuyển traffic thật) | PASS |
| 9 | Data parity check + Smoke test | PASS (xem §2, §3) |
| 10 | Tắt migration bridge (BƯỚC 3.8) | PASS — gitops PR #78 |

## 2. Bằng chứng: 100% traffic đang đi qua ElastiCache

**Endpoint app đang dùng, xác nhận khớp với AWS:**
```
$ kubectl get rollout cart -n techx-tf4 -o jsonpath='{...env...}' | grep VALKEY
VALKEY_ADDR=techx-tf4-valkey-cart.pyo0mq.ng.0001.use1.cache.amazonaws.com:6379

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
Khớp chính xác từng ký tự với `PrimaryEndpoint` mà AWS trả về cho replication group thật.

**Không còn đường nào khác cho traffic — `Deployment/cart` cũ đã xoá:**
```
$ kubectl get deployment cart -n techx-tf4
Error from server (NotFound): deployments.apps "cart" not found

$ kubectl get pods -n techx-tf4 -l app.kubernetes.io/component=cart
cart-766c6b8f5c-2f6lf   1/1   Running   0   4h53m
cart-766c6b8f5c-r9svc   1/1   Running   0   4h53m

$ kubectl get endpoints cart -n techx-tf4
10.0.10.74  -> cart-766c6b8f5c-r9svc
10.0.11.238 -> cart-766c6b8f5c-2f6lf
```

**Ghi dữ liệu thật qua đúng Service `cart` (giống hệt cách frontend/checkout gọi), rồi verify trực tiếp bằng redis-cli dữ liệu rơi vào đâu:**
```
$ grpcurl AddItem(user_id=evidence-test-user, product=OLJCESPC7Z, qty=2) -> cart.techx-tf4.svc.cluster.local:8080
{}
$ grpcurl GetCart(evidence-test-user)
{"userId":"evidence-test-user","items":[{"productId":"OLJCESPC7Z","quantity":2}]}

$ redis-cli -h techx-tf4-valkey-cart.pyo0mq.ng.0001.use1.cache.amazonaws.com -p 6379 EXISTS evidence-test-user
1
$ redis-cli -h techx-tf4-valkey-cart.pyo0mq.ng.0001.use1.cache.amazonaws.com -p 6379 TTL evidence-test-user
3572

$ kubectl exec deploy/valkey-cart -- redis-cli EXISTS evidence-test-user
0
```
Key ghi qua Service `cart` **có mặt trên ElastiCache** (TTL hợp lệ) và **không có** trên `valkey-cart` cũ. Đã dọn key test sau khi verify.

**DBSIZE 2 bên tại thời điểm viết evidence:**
- `valkey-cart` (cũ, không còn nhận traffic): 2 keys — chỉ còn sót lại vài key TTL dài, đang tự hết hạn dần vì không còn ghi mới.
- ElastiCache (đang phục vụ traffic thật): 512 keys — dữ liệu sống, đúng như kỳ vọng cho hệ thống đang hoạt động.

## 3. Smoke Test Cart/Checkout

- [x] Add-to-cart (grpcurl `AddItem`) — PASS.
- [x] View cart (grpcurl `GetCart`) — PASS, trả đúng item vừa add.
- [x] TTL key mới trên ElastiCache trong khoảng (0, 3600] — PASS (3572s, 3571s ở các lần test).
- [x] Rollout status: `Healthy`, `stable/active`, 2/2 Ready, 0 restart — ổn định nhiều giờ liên tục.

## 4. Theo dõi SLO

- **Cart success rate: 100%** — xác nhận qua Locust (`GET /api/cart`, `POST /api/cart`: 0 fail trên toàn bộ request quan sát được).
- Checkout tổng thể từng có giai đoạn giảm SLO do các service khác (`currency`, `shipping`) — đã xác nhận **không liên quan tới cart/ElastiCache** (cart luôn 0% fail trong suốt giai đoạn đó) và đã được đội phụ trách `currency` fix (PR #443). Nằm ngoài phạm vi CDO-08/REL-16.

## 5. Còn lại (phụ thuộc điều kiện ngoài REL-16)

- **TLS 3 pha** (`07-enable-tls.sh`): pha 1 cần secret `password`/`tls_enabled` trong `techx/tf4/elasticache-valkey` — hiện `ExternalSecret` mới chỉ có key `valkey-address`, chưa có 2 key trên. **Block bởi SEC-13**, không thuộc REL-16.
- **REL-18** (xoá `valkey-cart`/PVC): cần bake ổn định 24-48h trước khi mở ticket riêng — chưa đủ thời gian tính từ lúc cutover.

## 6. Acceptance Criteria

- [x] Add-to-cart / view cart pass.
- [x] Data parity: dữ liệu ghi mới xác nhận đúng vị trí (ElastiCache), TTL hợp lệ.
- [x] Không có error spike do cart gây ra (100% success rate).
- [x] Không xoá `valkey-cart` — giữ nguyên cho REL-18.
- [x] `Deployment/cart` cũ (orphan sau convert sang Rollout) đã dọn.
- [x] Migration bridge đã tắt (PR #78).
- [ ] Bake 24-48h ổn định — đang trong giai đoạn theo dõi.
- [ ] TLS 3 pha — chờ SEC-13.
