# CDO08 - Mandate 20 Backup/Restore Evidence Summary

**Mandate:** [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md)  
**Ngày tổng hợp:** 2026-07-27  
**AWS account:** `511825856493`  
**Region:** `us-east-1`  
**Kết luận hiện tại:** **Đủ evidence để đóng Mandate 20 cho phạm vi CDO08.**

Mandate 20 đã có evidence mạnh cho phần trọng tâm: RDS PITR restore drill thật và MSK orders archive replay drill đều PASS. Theo xác nhận PM/owner ngày 2026-07-27:

1. ADR RPO/RTO đã được chốt/ký về mặt quyết định, dù file ADR cũ còn dòng `DRAFT - CHƯA KÝ` chưa được sửa metadata.
2. Các app Argo CD `OutOfSync` không được tính là blocker cho Mandate 20 vì không làm thay đổi evidence backup/restore dữ liệu.
3. Valkey/cart được chốt là `Reconstructable`; dữ liệu cart có thể mất, không cần restore drill riêng.

## 0. Evidence chính

Evidence chính dùng để nộp Mandate 20:

- [CDO08-REL-26-RDS-ACCOUNTING-CONTROLLED-RESTORE-DRILL-EVIDENCE.md](CDO08-REL-26-RDS-ACCOUNTING-CONTROLLED-RESTORE-DRILL-EVIDENCE.md)

Các file khác trong thư mục này là evidence tham khảo thêm để chứng minh các phần hỗ trợ: MSK replay, backup baseline, retention, deletion guardrail, inventory và config reconstructability.

## 1. Requirement mapping

| Mandate 20 requirement | Evidence hiện có | Trạng thái |
|---|---|---|
| Không sót stateful store trên luồng ra tiền | Inventory liệt kê RDS, ElastiCache Valkey, MSK orders, Terraform state, GitOps, ExternalSecrets/ASM | **PASS** |
| RPO/RTO rõ ràng, cadence tương xứng | Có RPO/RTO matrix và backup policy matrix; PM/owner xác nhận ADR đã chốt | **PASS** |
| Point-in-time restore chứng minh được | REL-26 RDS drill restore bằng PITR ra RDS tách biệt | **PASS** |
| Tested restore drill thật | REL-26 gây xóa dữ liệu có kiểm soát trên RDS temp, restore đúng marker; REL-25 MSK replay archive vào topic drill | **PASS** |
| Backup an toàn: encryption, retention, tách quyền xoá | RDS/Valkey/MSK archive encrypted; S3 archive versioning/lifecycle; REL-24 negative delete tests PASS | **PASS** |
| Không phá production khi drill | REL-26 dùng 2 RDS tạm; REL-25 dùng topic drill riêng; production topic/RDS không bị ghi/xóa | **PASS** |
| Cluster/config có thể dựng lại từ repo | Terraform + GitOps + ESO references đã có; live ExternalSecrets synced | **PASS** |

## 2. Stateful store coverage

| Store / config state | Cơ chế bảo vệ | Restore / replay evidence | Trạng thái |
|---|---|---|---|
| RDS PostgreSQL `techx-tf4-postgresql` / schema `accounting` | RDS automated backup + PITR 7 ngày, AWS Backup recovery point 35 ngày, encryption, deletion protection | [CDO08-REL-26-RDS-ACCOUNTING-CONTROLLED-RESTORE-DRILL-EVIDENCE.md](CDO08-REL-26-RDS-ACCOUNTING-CONTROLLED-RESTORE-DRILL-EVIDENCE.md) | **PASS** |
| MSK Kafka topic `orders` | MSK Connect S3 Sink archive vào S3, bucket versioning/lifecycle 35 ngày, delete guard | [CDO08-REL-25-MSK-ORDERS-REPLAY-DEMO-EVIDENCE.md](CDO08-REL-25-MSK-ORDERS-REPLAY-DEMO-EVIDENCE.md) | **PASS** |
| ElastiCache Valkey `techx-tf4-valkey-cart` | Snapshot retention 7 ngày, at-rest encryption, in-transit TLS, AUTH, Multi-AZ enabled | Live AWS check trong file này; dữ liệu cart được classify `Reconstructable` | **PASS cho backup baseline** |
| App PVC/EBS trên namespace `techx-tf4` | Không còn PVC app trong namespace `techx-tf4` | `kubectl -n techx-tf4 get pvc` trả về `No resources found` | **N/A** |
| Terraform state | Remote S3 state + DynamoDB lock; inventory ghi nhận versioning/encryption | [CDO08-REL-20-stateful-store-inventory.md](../scan/CDO08-REL-20-stateful-store-inventory.md) | **PASS theo thiết kế** |
| GitOps manifests / Argo CD desired state | GitOps repo + Argo CD root app | Live Argo check trong file này; OutOfSync hiện tại không phải blocker Mandate 20 | **PASS** |
| Secret references | ExternalSecrets -> AWS Secrets Manager | Live `kubectl get externalsecret -A`: all `SecretSynced=True` | **PASS** |

## 3. RDS evidence

Evidence chính:

- [CDO08-REL-26-RDS-ACCOUNTING-CONTROLLED-RESTORE-DRILL-EVIDENCE.md](CDO08-REL-26-RDS-ACCOUNTING-CONTROLLED-RESTORE-DRILL-EVIDENCE.md)

Tham khảo thêm:

- [CDO08-REL-22-rds-pitr-retention-evidence.md](CDO08-REL-22-rds-pitr-retention-evidence.md)
- [CDO08-REL-23-object-inventory-evidence.md](CDO08-REL-23-object-inventory-evidence.md)
- [CDO08-REL-25-INTERNAL-DRY-RUN-EVIDENCE.md](CDO08-REL-25-INTERNAL-DRY-RUN-EVIDENCE.md)

Live check ngày 2026-07-27:

```json
{
  "Status": "available",
  "Public": false,
  "Encrypted": true,
  "BackupRetention": 7,
  "BackupWindow": "18:00-19:00",
  "LatestRestorableTime": "2026-07-27T08:42:32+00:00",
  "DeletionProtection": true,
  "MultiAZ": true,
  "Endpoint": "techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com"
}
```

AWS Backup recovery point:

```text
ResourceType: RDS
CreationDate: 2026-07-23T15:19:58.948000+07:00
DeleteAt: 2026-08-27T15:19:58.948000+07:00
RecoveryPointArn: arn:aws:rds:us-east-1:511825856493:snapshot:awsbackup:job-193efb00-b004-4b95-96e2-194b6e3c6885
```

REL-26 drill result:

```text
rel26_completed production_modified=false temp_source_corrupted=true marker_restored=true marker_order_id=rel26-20260727-controlled-delete-order drill_setup_seconds=1965 recovery_rto_seconds=789
cleanup_complete_no_drill_resources_remaining
```

Interpretation:

- `production_modified=false`: production RDS không bị sửa.
- `temp_source_corrupted=true`: có mô phỏng xóa nhầm thật trên RDS temp.
- `marker_restored=true`: dữ liệu marker bị xóa đã được restore lại.
- `recovery_rto_seconds=789`: RTO recovery đo được là `13m09s`.

## 4. MSK orders archive/replay evidence

Tham khảo thêm:

- [CDO08-REL-22-msk-orders-s3-archive-evidence.md](CDO08-REL-22-msk-orders-s3-archive-evidence.md)
- [CDO08-REL-22-msk-orders-s3-sink-runtime-evidence.md](CDO08-REL-22-msk-orders-s3-sink-runtime-evidence.md)
- [CDO08-REL-22-msk-archive-readability-evidence.md](CDO08-REL-22-msk-archive-readability-evidence.md)
- [CDO08-REL-25-MSK-ORDERS-REPLAY-DEMO-EVIDENCE.md](CDO08-REL-25-MSK-ORDERS-REPLAY-DEMO-EVIDENCE.md)

Live S3 archive check ngày 2026-07-27:

```text
Latest observed archive objects:
2026-07-27T05:24:59+00:00  orders/orders/topic=orders/year=2026/month=07/day=27/hour=05/orders+2+0000000049.bin
2026-07-27T05:24:59+00:00  orders/orders/topic=orders/year=2026/month=07/day=27/hour=05/orders+2+0000000048.bin
2026-07-27T05:24:59+00:00  orders/orders/topic=orders/year=2026/month=07/day=27/hour=05/orders+2+0000000047.bin
```

S3 archive bucket controls:

```json
{
  "Versioning": "Enabled",
  "Lifecycle": {
    "ID": "orders-archive-7-day-standard-35-day-retention",
    "Status": "Enabled",
    "Prefix": "orders/",
    "TransitionDays": 7,
    "TransitionClass": "STANDARD_IA",
    "ExpirationDays": 35,
    "NoncurrentDays": 35
  }
}
```

REL-25 MSK replay drill result:

```text
REL25_MSK_REPLAY_DRILL=PASS
drill_id=rel25-20260727-msk-demo
target_topic=orders-replay-drill-rel25-20260727-msk-demo
source_window=2026-07-27T05:00:00Z->2026-07-27T06:00:00Z
validation=PASS
failed=0
replayed=53
drill_topic_present=false
production_topic_present=true
```

Interpretation:

- S3 archive có object thật trong window.
- Replay đã chạy vào topic drill riêng, không vào `orders`.
- 53 records được replay và verify thành công.
- Topic drill đã bị cleanup.
- Production topic `orders` vẫn tồn tại.

## 5. ElastiCache Valkey evidence

Valkey được classify là `Reconstructable` vì dữ liệu cart là dữ liệu tạm, có TTL và khách có thể thêm lại. Tuy vậy backup baseline vẫn đã bật.

Live check ngày 2026-07-27:

```json
{
  "Status": "available",
  "AtRestEncryptionEnabled": true,
  "TransitEncryptionEnabled": true,
  "AuthTokenEnabled": true,
  "MultiAZ": "enabled",
  "SnapshotRetentionLimit": 7,
  "SnapshotWindow": "18:00-19:00",
  "AutomaticFailover": "enabled"
}
```

Kết luận:

- Snapshot retention 7 ngày đã bật.
- At-rest encryption, in-transit encryption và AUTH đã bật.
- Multi-AZ/automatic failover đã bật.
- Không cần RPO chặt cho cart vì đây không phải source of truth.

## 6. PVC/EBS app data evidence

Live check namespace app:

```text
kubectl -n techx-tf4 get pvc
No resources found in techx-tf4 namespace.
```

Các deployment in-cluster stateful cũ không còn tồn tại:

```text
deployments.apps "kafka" not found
deployments.apps "valkey-cart" not found
deployments.apps "postgresql" not found
```

Kết luận:

- Revenue path hiện không còn app PVC/EBS cần backup trong namespace `techx-tf4`.
- Stateful data chính đã nằm ở managed services: RDS, ElastiCache, MSK + S3 archive.

## 7. Secret/config reconstructability evidence

ExternalSecrets live check ngày 2026-07-27:

```text
cloudflare-access/cloudflare-tunnel-token      SecretSynced True
techx-observability/alertmanager-slack-secret SecretSynced True
techx-observability/alertmanager-smtp-secret  SecretSynced True
techx-observability/grafana-admin-secret      SecretSynced True
techx-tf4/elasticache-valkey-secret           SecretSynced True
techx-tf4/flagd-bearer-secret                 SecretSynced True
techx-tf4/msk-kafka-secret                    SecretSynced True
techx-tf4/openai-api-secret                   SecretSynced True
techx-tf4/postgres-db-secret                  SecretSynced True
techx-tf4/rds-postgres-secret                 SecretSynced True
```

Runtime application secret references:

```text
accounting: DB_CONNECTION_STRING <- rds-postgres-secret/dotnet-conn-string
accounting: Kafka SASL + bootstrap <- msk-kafka-secret
checkout: Kafka SASL + bootstrap <- msk-kafka-secret
fraud-detection: Kafka SASL + bootstrap <- msk-kafka-secret
cart: VALKEY_ADDR/TLS/PASSWORD <- elasticache-valkey-secret
```

Kết luận:

- Secret values không cần nằm trong Git.
- GitOps chỉ quản lý ExternalSecret references.
- AWS Secrets Manager là source of truth cho runtime secrets.

## 8. GitOps/IaC reconstructability evidence

Nền tảng reconstructability hiện có:

- Terraform quản lý managed data resources và guardrails.
- GitOps/Argo CD quản lý runtime manifests.
- ExternalSecrets tái tạo Kubernetes Secrets từ AWS Secrets Manager.

Live Argo CD check ngày 2026-07-27:

```text
argo-rollouts            Synced        Healthy
argocd-redis-placement   Synced        Healthy
external-secrets         Synced        Healthy
kyverno                  OutOfSync     Healthy
platform-admission       Synced        Healthy
platform-secrets         Synced        Healthy
root-bootstrap           Synced        Healthy
strimzi-operator         Synced        Healthy
techx-corp               Synced        Healthy
techx-observability      OutOfSync     Progressing
techx-raw                OutOfSync     Healthy
```

Kết luận:

- Runtime chính `techx-corp`, `platform-secrets`, `external-secrets`, `root-bootstrap` đang `Synced/Healthy`.
- `kyverno`, `techx-observability`, `techx-raw` còn `OutOfSync`/`Progressing` tại thời điểm chụp, nhưng PM/owner xác nhận đây không phải blocker cho Mandate 20 vì Mandate 20 chấm backup/restore dữ liệu và khả năng dựng lại config từ repo, không yêu cầu mọi app Argo phải sạch tuyệt đối tại snapshot.
- Terraform + GitOps + ExternalSecrets/ASM đủ làm evidence reconstructability cho cluster/config state trong phạm vi Mandate 20.

## 9. Backup safety evidence

Evidence chính:

- [CDO08-REL-24-backup-deletion-separation-of-duties.md](../adr/CDO08-REL-24-backup-deletion-separation-of-duties.md)
- [CDO08-REL-24-negative-deletion-tests.md](CDO08-REL-24-negative-deletion-tests.md)

Runtime negative deletion test:

```text
Workflow run: 30191955252
Actor: arn:aws:sts::511825856493:assumed-role/tf4-github-actions-terraform-apply/GitHubActions
RDS snapshot delete: AccessDenied explicit deny
ElastiCache snapshot delete: AccessDenied explicit deny
S3 archive object delete: AccessDenied explicit deny
MSK delete: AccessDeniedException explicit deny
```

Kết luận:

- Normal CI/apply role bị deny khi cố xóa protected recovery assets.
- CloudTrail có event ID cho các hành vi bị deny.
- Backup safety requirement đã có runtime evidence.

## 10. Các exception đã được PM/owner chốt

### Exception 1 - ADR file còn ghi draft nhưng quyết định đã ký/chốt

Các file ADR hiện tại vẫn còn metadata cũ:

```text
TRẠNG THÁI: DRAFT - CHƯA KÝ
```

File liên quan:

- [CDO08-REL-21-adr-draft.md](../adr/CDO08-REL-21-adr-draft.md)
- [CDO08-REL-21-summary.md](../adr/CDO08-REL-21-summary.md)
- [CDO08-REL-21-rpo-rto-matrix.md](../adr/CDO08-REL-21-rpo-rto-matrix.md)

Theo xác nhận PM/owner ngày 2026-07-27, quyết định RPO/RTO đã được chốt/ký về mặt nội dung. Metadata trong file ADR là nợ chỉnh tài liệu, không phải blocker kỹ thuật của Mandate 20.

Số đo thật sau drill:

- RDS `accounting`: measured recovery RTO `789s / 13m09s`.
- MSK replay: measured live replay tới report PASS `77s`, tổng live drill gồm cleanup `105s`.

### Exception 2 - Argo CD còn OutOfSync nhưng không blocker Mandate 20

Live Argo CD còn:

```text
kyverno             OutOfSync Healthy
techx-observability OutOfSync Progressing
techx-raw           OutOfSync Healthy
```

Các trạng thái này không được tính là blocker vì:

- runtime app chính `techx-corp`, `platform-secrets`, `external-secrets`, `root-bootstrap` đã đủ healthy/synced cho evidence dữ liệu;
- Mandate 20 chấm backup/restore, RPO/RTO và recovery evidence, không chấm Argo sync hygiene;
- GitOps/IaC source vẫn là nguồn reconstructability.

### Exception 3 - Valkey/cart là reconstructable

Valkey/cart được PM/owner chốt là dữ liệu tạm:

- mất cart không làm mất sổ cái order hoặc audit trail;
- khách có thể thêm lại sản phẩm vào cart;
- hệ chỉ cần cart service phục hồi đọc/ghi, không cần restore từng key cũ;
- snapshot retention 7 ngày vẫn đang bật như baseline an toàn.

## 11. Kết luận evidence

CDO08 đủ evidence để đóng Mandate 20 cho phạm vi team:

- RDS PITR restore drill thật PASS.
- MSK archive replay drill thật PASS.
- Backup deletion guardrail PASS.
- RDS, Valkey và MSK archive đều có encryption/retention phù hợp.
- Namespace `techx-tf4` không còn app PVC/EBS cần backup.
- Config và secret references có thể dựng lại qua Terraform, GitOps, ExternalSecrets và AWS Secrets Manager.
