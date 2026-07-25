# CDO08 Mandate 08 - Evidence tổng hợp managed data migration

**Thời điểm kiểm tra:** 2026-07-22 10:02 ICT  
**Namespace ứng dụng:** `techx-tf4`  
**Phạm vi:** PostgreSQL, Valkey cart, Kafka orders

## 1. Kết luận

Mandate 08 đã hoàn tất ở mức runtime cutover:

- PostgreSQL application traffic đã chuyển sang Amazon RDS PostgreSQL.
- Cart/checkout data path đã chuyển sang Amazon ElastiCache for Valkey.
- Checkout producer và accounting/fraud-detection consumers đã chuyển sang Amazon MSK.
- Các pod/service self-hosted data plane cũ không còn chạy trong namespace `techx-tf4`.
- PVC cũ vẫn được giữ lại để rollback/data-retention tạm thời, không phục vụ traffic hiện tại.

Argo CD `techx-corp` hiện vẫn hiển thị `OutOfSync` do `OrphanedResourceWarning` cho các resource được giữ lại sau cleanup. Runtime health vẫn `Healthy`; đây là trạng thái chấp nhận được cho giai đoạn post-cutover vì PVC rollback chưa bị xóa.

## 2. Evidence tham chiếu

| Data store | Evidence chi tiết | Trạng thái |
|---|---|---|
| PostgreSQL -> RDS | `docs/cdo08/week2/mandate8/evidence/REL-15-postgresql-rds-cutover-evidence.md` | Cutover xong |
| Valkey cart -> ElastiCache | `docs/cdo08/week2/mandate8/evidence/CDO08-REL-16-cart-cutover-evidence.md` | Cutover xong |
| Kafka -> MSK | `docs/cdo08/week2/mandate8/evidence/REL-17-kafka-msk-cutover-evidence.md` | Cutover xong |

## 3. Runtime state sau cleanup

Lệnh kiểm tra:

```sh
kubectl -n techx-tf4 get pods
kubectl -n techx-tf4 get svc
kubectl -n techx-tf4 get pvc
kubectl -n argocd get application techx-corp
```

Kết quả runtime:

- Không còn pod `postgresql`.
- Không còn pod `valkey-cart`.
- Không còn pod `kafka`.
- Không còn pod `orders-mirrormaker2`.
- Không còn service `postgresql`.
- Không còn service `valkey-cart`.
- Không còn service `kafka`.
- Không còn service `orders-mirrormaker2-*`.
- Không còn service `postgresql-migration-bridge`.

PVC còn lại:

| PVC | Status | Capacity | StorageClass | Mục đích hiện tại |
|---|---|---:|---|---|
| `postgresql-pvc` | Bound | 10Gi | gp2 | Giữ lại tạm thời cho rollback/data-retention |
| `valkey-cart-pvc` | Bound | 5Gi | gp2 | Giữ lại tạm thời cho rollback/data-retention |
| `kafka-pvc` | Bound | 10Gi | gp2 | Giữ lại tạm thời cho rollback/data-retention |

## 4. PostgreSQL -> RDS

Runtime application không còn dùng service `postgresql` nội cluster. Workload liên quan lấy connection từ `rds-postgres-secret`.

Evidence từ runtime:

```text
accounting:
  DB_CONNECTION_STRING:
    secretKeyRef:
      name: rds-postgres-secret
      key: dotnet-conn-string
```

RDS secret contract được quản lý qua ASM/ExternalSecrets theo SEC-13. Secret application path:

```text
techx/tf4/rds-postgres -> techx-tf4/rds-postgres-secret
```

## 5. Valkey cart -> ElastiCache

Rollout `cart` đang Healthy:

```text
Rollout: cart
Status: Healthy
Desired: 2
Ready: 2
Available: 2
Stable/active ReplicaSet: cart-6c7785fd7
```

Runtime `cart` lấy Valkey endpoint và credential từ `elasticache-valkey-secret`:

```text
VALKEY_ADDR:
  secretKeyRef:
    name: elasticache-valkey-secret
    key: valkey-address

VALKEY_TLS:
  secretKeyRef:
    name: elasticache-valkey-secret
    key: tls_enabled

VALKEY_PASSWORD:
  secretKeyRef:
    name: elasticache-valkey-secret
    key: password
```

Secret application path:

```text
techx/tf4/elasticache-valkey -> techx-tf4/elasticache-valkey-secret
```

## 6. Kafka -> MSK

Rollout `checkout` đang Healthy:

```text
Rollout: checkout
Status: Healthy
Desired: 2
Ready: 2
Available: 2
Stable/active ReplicaSet: checkout-6bfcbcdb7d
```

`checkout` producer lấy Kafka endpoint và auth từ `msk-kafka-secret`:

```text
KAFKA_ADDR:
  secretKeyRef:
    name: msk-kafka-secret
    key: kafka-address

KAFKA_SECURITY_PROTOCOL:
  secretKeyRef:
    name: msk-kafka-secret
    key: security-protocol

KAFKA_SASL_MECHANISM:
  secretKeyRef:
    name: msk-kafka-secret
    key: sasl-mechanism

KAFKA_USERNAME:
  secretKeyRef:
    name: msk-kafka-secret
    key: username

KAFKA_PASSWORD:
  secretKeyRef:
    name: msk-kafka-secret
    key: password
```

`accounting` và `fraud-detection` consumers cũng lấy endpoint/auth từ `msk-kafka-secret`.

Secret application path:

```text
techx/tf4/msk-kafka -> techx-tf4/msk-kafka-secret
```

## 7. Acceptance Criteria

| Check | Kết quả |
|---|---|
| App không còn phụ thuộc service `postgresql` nội cluster | PASS |
| App không còn phụ thuộc service `valkey-cart` nội cluster | PASS |
| App không còn phụ thuộc service `kafka` nội cluster | PASS |
| MirrorMaker2 đã tắt sau Kafka cutover | PASS |
| Migration bridge PostgreSQL đã tắt sau cutover | PASS |
| Rollout `cart` Healthy | PASS |
| Rollout `checkout` Healthy | PASS |
| `accounting` Ready với MSK secret | PASS |
| `fraud-detection` Ready với MSK secret | PASS |
| PVC cũ được giữ lại để rollback/data-retention tạm thời | PASS |

## 8. Follow-up sau cutover

Các việc sau không chặn Mandate 08 runtime cutover, nhưng cần đóng sau observation window:

1. Chốt thời điểm xóa hoặc archive PVC cũ: `postgresql-pvc`, `valkey-cart-pvc`, `kafka-pvc`.
2. Ghi lại owner và change window nếu xóa PVC/backup cũ.
3. Theo dõi SLO checkout/cart và consumer lag MSK trong observation window.
4. Xác nhận chi phí recurring sau khi self-hosted pods đã tắt và temporary migration workload đã được cleanup.
5. Nếu rollback window kết thúc, cập nhật Argo/GitOps để hết `OrphanedResourceWarning` liên quan resource cũ.
