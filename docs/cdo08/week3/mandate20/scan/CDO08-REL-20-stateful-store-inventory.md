# CDO08-REL-20 (T2) - Inventory Store & Trạng thái Hạ tầng

**Mandate:** [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md) - Directive #20 (DR / Backup & Restore)
**Subtask:** T2 - "Liệt kê toàn bộ store và trạng thái hạ tầng thuộc phạm vi backup"
**Phương pháp:** `aws ...describe-*/list-*`, `kubectl get/describe` (read-only), và đọc `infra/terraform/` + `techx-corp-chart/`. Không có tài nguyên nào bị tạo/sửa/xoá.
**Điều kiện tiên quyết:** [CDO08-REL-20-revenue-path-dependency-trace.md](CDO08-REL-20-revenue-path-dependency-trace.md)
**Owner:** Nguyên (Techlead)

---

## 1. Sơ đồ service -> store -> backup -> owner

```text
[Live - production]

product-catalog, accounting  -->  RDS PostgreSQL (techx-tf4-postgresql)
                                     backup: automated snapshot + PITR, retention 7 ngày, mã hoá KMS
                                     owner: CDO08 reliability pod

cart                          -->  ElastiCache Valkey (techx-tf4-valkey-cart)
                                     backup: automated snapshot, retention 7 ngày, mã hoá at-rest + in-transit
                                     owner: CDO08 reliability pod

checkout, accounting,
fraud-detection               -->  MSK Kafka (techx-tf4-orders)
                                     backup: KHÔNG CÓ - MSK không có API snapshot/backup
                                     owner: CDO08 reliability pod

[Trạng thái hạ tầng / cụm]

Terraform apply/plan          -->  Terraform state (S3 + DynamoDB lock)
                                     backup: S3 versioning + SSE, tốt
                                     owner: Platform/Infra

ArgoCD                        -->  Repo GitOps riêng (tf4-phase3-gitops-manifests)
                                     backup: tái tạo từ git, ổn nếu repo đó cũng bền vững
                                     owner: Platform/Infra

Secret DB/cache/queue         -->  AWS Secrets Manager (qua ExternalSecrets)
                                     backup: bền vững theo AWS, k8s Secret chỉ là cache
                                     owner: Platform/Infra
```

## 2. Bảng inventory

| # | Tài nguyên | Môi trường | Owner | Cơ chế backup | Trạng thái backup | Phương thức restore | Mã hoá at-rest | Ghi chú |
|---|---|---|---|---|---|---|---|---|
| 1 | RDS `techx-tf4-postgresql` (Postgres 17.9, Multi-AZ, `db.t4g.micro`) | Phase3 | CDO08 reliability pod | Automated RDS snapshot + PITR | Bật, retention 7 ngày, cửa sổ 18:00-19:00 UTC; 6 automated snapshot quan sát được 2026-07-19 -> 21 | `restore-db-instance-to-point-in-time` hoặc restore từ snapshot | Có (KMS) | `deletion_protection = true`, `storage_encrypted = true` trong `infra/terraform/rds.tf`, khớp với live config. Mật khẩu master ở Secrets Manager. Tình trạng tốt. |
| 2 | ElastiCache `techx-tf4-valkey-cart` (replication group, Multi-AZ) | Phase3 | CDO08 reliability pod | Automated ElastiCache snapshot | Bật, retention 7 ngày (`snapshot_retention_limit = 7` trong `infra/terraform/elasticache.tf`) | Restore từ snapshot của replication group | Có (at-rest + in-transit TLS + AUTH) | Chỉ là cache/session data, tái tạo được, không phải nguồn sự thật - RPO/RTO có thể nới lỏng hơn RDS. |
| 3 | MSK `techx-tf4-orders` (2 broker, `kafka.t3.small`) | Phase3 | CDO08 reliability pod | **Không có** - MSK không có API backup/snapshot | N/A - bảo vệ chỉ nhờ topic retention + replication factor 2, không phải backup | Không restore được từ snapshot; DR = tạo lại cluster + replay từ bản sao replicated hoặc từ producer gốc | Có (KMS + TLS in-transit, theo `infra/terraform/msk.tf`) | Gap cấu trúc: retention/replication chỉ bảo vệ khỏi mất 1 broker, không bảo vệ khỏi xoá topic hoặc mất cả cluster. Không có MSK Connect/S3 sink để lưu trữ lâu dài topic `orders`. |
| 4 | DynamoDB - dữ liệu ứng dụng | - | - | N/A | **Không tồn tại.** `grep -r "aws_dynamodb_table" infra/terraform/` = 0 kết quả cho app data; 0 env var `DYNAMODB_*` trong chart | - | - | Không nằm trên luồng ra tiền, không cần theo dõi. |
| 5 | DynamoDB `tf4-phase3-state-locks` (bảng lock Terraform) | Infra | Platform/Infra | PITR | Bật, recovery window 35 ngày | PITR restore-to-point-in-time | Có (SSE-KMS) | Dữ liệu lock tạm thời, tái tạo rỗng được ngay. Không phải app data. |
| 6 | Terraform state - S3 `tf4-phase3-state-bucket-...` + DynamoDB lock | Infra | Platform/Infra | S3 versioning + SSE | Versioning bật, SSE-S3 (AES256) | Restore version cũ từ S3 | Có | Backend hoàn toàn remote; hạ tầng tái tạo được từ state + repo này. Tốt. |
| 7 | ArgoCD (GitOps control plane) | Infra | Platform/Infra | Không có backup riêng - tái tạo từ git | N/A theo thiết kế | Bootstrap lại `root-bootstrap` Application trỏ về repo `tf4-phase3-gitops-manifests` | N/A | Đã kiểm tra trực tiếp repo `tf4-phase3-gitops-manifests` - host trên GitHub (`github.com/TF4-Phase3-TechX/...`), có `main`/`promotion/production`, có CODEOWNERS + CI validate. Bền vững, không phải single point of failure. `main` có cờ `protected: true` nhưng `required_status_checks.enforcement_level` đang là `off` - branch protection còn khá mỏng, nên biết vậy nhưng đây là vấn đề change-control, không tính vào phạm vi backup dữ liệu của Mandate 20. App `techx-corp` hiện `Degraded`, 3 app `OutOfSync` - vấn đề drift, khác chuyện backup. |
| 8 | ExternalSecrets -> AWS Secrets Manager | Infra | Platform/Infra | Nguồn từ Secrets Manager, sync mỗi giờ vào k8s Secret | N/A - độ bền do AWS quản lý | Sync lại từ Secrets Manager | Có | 9 ExternalSecrets trên `techx-tf4`/`techx-observability`, đều backed bởi `aws-secretsmanager`. `alertmanager-smtp-secret` báo lỗi sync - vấn đề vận hành, không liên quan độ bền dữ liệu. |
| 9 | IAM - role `tf4-github-actions-terraform-apply` | Infra | Platform/Infra + Security | - | **Có gap.** Role mang policy managed `PowerUserAccess` + `IAMFullAccess`, cho phép `Allow: * on Resource:*` (chỉ trừ `iam:*`, `organizations:*`) | - | - | Role CI/apply này xoá được không giới hạn `rds:DeleteDBSnapshot`, `dynamodb:DeleteBackup`, `ec2:DeleteSnapshot`, `elasticache:DeleteSnapshot`, `kafka:DeleteCluster`. Vi phạm yêu cầu #5 của mandate (tách quyền chống xoá backup). |
| 10 | PVC `techx-observability/opensearch-opensearch-0` (gp2, 40Gi) | Observability | Platform/Infra | Snapshot EBS thủ công | 2 snapshot (2026-07-14/15), không có gì sau đó | Restore từ snapshot EBS | Không (chưa mã hoá) | Đang sống/đang dùng. Không có OpenSearch snapshot repo native (S3), chỉ có snapshot nguyên volume, đã cũ >7 ngày. Ngoài luồng ra tiền nhưng vẫn là dữ liệu log/trace đang chạy. |
| 11 | PVC `techx-observability/prometheus` (gp2-retain, 20Gi) | Observability | Platform/Infra | Không có | 0 snapshot | N/A | Không (chưa mã hoá) | Chấp nhận được nếu Prometheus được coi là telemetry không cần backup - nhưng hiện chưa có quyết định nào ghi lại việc này, chỉ là chưa làm. |
| 12 | S3 `tf4-postgresql-migration-backups-...` (pg_dump lúc cutover) | Phase3 | CDO08 reliability pod | S3 versioning + SSE-S3 + lifecycle hết hạn 7 ngày | Bật; object dump đang tồn tại | `pg_restore` từ object dump | Có | Bản dump 1 lần lúc cutover, không phải backup định kỳ - hết hạn sau 7 ngày, không dùng làm cơ chế DR lâu dài được. |

## 3. Đã xác nhận tốt (không cần tạo gap cho các mục này)

- RDS automated backup + PITR: bật, khớp Terraform, có mã hoá. ✅
- ElastiCache automated snapshot: bật, khớp Terraform, có mã hoá. ✅
- Terraform state (S3 + DynamoDB lock): versioning, mã hoá, remote. ✅
- ExternalSecrets backed bởi AWS Secrets Manager: bền vững theo thiết kế. ✅
- ArgoCD tái tạo được từ git: ổn theo carve-out của mandate, phụ thuộc độ bền của repo GitOps ngoài (câu hỏi mở, không phải lỗi).

---

**Ghi chú cuối file - cần Nguyên xác minh thêm:**
Một số lệnh AWS API bị từ chối quyền trên role đang dùng để kiểm tra (`dynamodb:ListTables`, `dynamodb:DescribeLimits`, `kafka:ListConfigurations`, `kafka:ListClusterOperations`, `dlm:GetLifecyclePolicies`). Các kết luận trong tài liệu này (DynamoDB không có app table, không có lịch snapshot EBS tự động cho volume observability) dựa trên rà soát code (`grep` toàn bộ `infra/terraform/` không thấy `aws_dynamodb_table` cho app, không thấy `aws_dlm_lifecycle_policy` hay `aws_backup_plan`/`aws_backup_vault` nào). Nếu có tài nguyên nào được tạo tay ngoài Terraform (console), phần này sẽ không thấy được - nên kiểm tra lại bằng 1 role IAM rộng hơn để chắc chắn 100%.
