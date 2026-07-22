# REL-15 PostgreSQL Pre-Cutover Backup & Baseline Evidence

**Người thực hiện:** Hoàng Nam
**Team:** CDO08
**Task:** CDO08-REL-15
**Subtask:** Capture PostgreSQL pre-cutover backup and baseline
**Ngày ghi nhận:** 2026-07-20

Tài liệu này ghi lại evidence baseline PostgreSQL self-hosted trước khi migrate sang Amazon RDS. Evidence không chứa plaintext credential, connection string có secret, hoặc raw backup data.

---

## 1. Phạm vi

Subtask này chỉ thực hiện:

- Xác nhận PostgreSQL source hiện tại trong namespace `techx-tf4`.
- Ghi nhận service, pod, PVC và version PostgreSQL.
- Ghi nhận schema/table inventory, primary key, foreign key và identity column.
- Tạo schema dump và data dump trước cutover.
- Upload backup artifacts đã verify lên S3 backup bucket với retention 7 ngày.

Subtask này chưa thực hiện:

- Chưa restore dữ liệu vào RDS.
- Chưa chạy DMS task.
- Chưa tạo app user/secret thật cho workload.
- Chưa cutover app sang RDS.

---

## 2. Source PostgreSQL Runtime Baseline

### 2.1. Kubernetes Resource Inventory

Lệnh kiểm tra:

```powershell
kubectl -n techx-tf4 get deploy,svc,pvc,pod -l opentelemetry.io/name=postgresql -o wide
kubectl -n techx-tf4 get svc postgresql -o yaml
```

Output chính đã ghi nhận:

| Resource          | Value                                      |
| ----------------- | ------------------------------------------ |
| Namespace         | `techx-tf4`                                |
| Deployment        | `postgresql`                               |
| Deployment ready  | `1/1`                                      |
| Image             | `postgres:17.6`                            |
| Service           | `postgresql`                               |
| Service type      | `ClusterIP`                                |
| ClusterIP         | `172.20.87.154`                            |
| External IP       | `<none>`                                   |
| Port              | `5432/TCP`                                 |
| Selector          | `opentelemetry.io/name=postgresql`         |
| PVC               | `postgresql-pvc`                           |
| PVC status        | `Bound`                                    |
| PVC volume        | `pvc-e0600223-7b8a-4bc6-ab58-bdb77e9653e0` |
| PVC capacity      | `10Gi`                                     |
| PVC storage class | `gp2`                                      |
| Pod               | `postgresql-7b6b8fdc66-v269v`              |
| Pod status        | `Running`                                  |
| Pod IP            | `10.0.10.27`                               |
| Node              | `ip-10-0-10-231.ec2.internal`              |

Kết luận:

- PostgreSQL source đang chạy trong EKS.
- Service hiện là `ClusterIP`, không public.
- Đây là rollback source chính nếu migration/restore chưa cutover sang RDS.

### 2.2. PostgreSQL Version

Lệnh kiểm tra:

```powershell
kubectl -n techx-tf4 exec deploy/postgresql -- psql -U root -d otel -c "SELECT version();"
```

Output chính:

```text
PostgreSQL 17.6 (Debian 17.6-2.pgdg13+1) on x86_64-pc-linux-gnu
```

Kết luận:

- Source PostgreSQL runtime version là `17.6`.
- Target RDS đã được align ở version `17.9`; restore/migration cần ghi rõ version mismatch source-target và verify compatibility trước cutover.

---

## 3. Schema/Table Baseline

### 3.1. Table List

Lệnh kiểm tra:

```powershell
kubectl -n techx-tf4 exec deploy/postgresql -- psql -U root -d otel -c "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema') ORDER BY table_schema, table_name;"
```

Output đã ghi nhận:

| Schema       | Table            |
| ------------ | ---------------- |
| `accounting` | `order`          |
| `accounting` | `orderitem`      |
| `accounting` | `shipping`       |
| `catalog`    | `products`       |
| `reviews`    | `productreviews` |

### 3.2. Column Inventory

Lệnh kiểm tra:

```powershell
kubectl -n techx-tf4 exec deploy/postgresql -- psql -U root -d otel -c "SELECT table_schema, table_name, column_name, data_type, is_nullable, column_default, identity_generation FROM information_schema.columns WHERE table_schema IN ('accounting','catalog','reviews') ORDER BY table_schema, table_name, ordinal_position;"
```

Kết quả tóm tắt:

| Table                    | Column count | Ghi chú                                       |
| ------------------------ | -----------: | --------------------------------------------- |
| `accounting.order`       |            1 | `order_id text NOT NULL`                      |
| `accounting.orderitem`   |            7 | order item cost/product/quantity/order fields |
| `accounting.shipping`    |           10 | shipping cost/address/order fields            |
| `catalog.products`       |            8 | product catalog fields                        |
| `reviews.productreviews` |            5 | có identity column `id`                       |

Identity column:

| Table                    | Column | Type      | Identity     |
| ------------------------ | ------ | --------- | ------------ |
| `reviews.productreviews` | `id`   | `integer` | `BY DEFAULT` |

Không ghi nhận column `created_at`, `updated_at` hoặc `deleted_at` trên các bảng chính tại thời điểm baseline.

### 3.3. Primary Key Inventory

Lệnh kiểm tra:

```powershell
kubectl -n techx-tf4 exec deploy/postgresql -- psql -U root -d otel -c "SELECT tc.table_schema, tc.table_name, kcu.column_name FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema IN ('accounting','catalog','reviews') ORDER BY tc.table_schema, tc.table_name, kcu.ordinal_position;"
```

Output đã ghi nhận:

| Table                    | Primary key              |
| ------------------------ | ------------------------ |
| `accounting.order`       | `order_id`               |
| `accounting.orderitem`   | `order_id`, `product_id` |
| `accounting.shipping`    | `shipping_tracking_id`   |
| `catalog.products`       | `id`                     |
| `reviews.productreviews` | `id`                     |

### 3.4. Foreign Key Inventory

Lệnh kiểm tra:

```powershell
kubectl -n techx-tf4 exec deploy/postgresql -- psql -U root -d otel -c "SELECT tc.table_schema, tc.table_name, kcu.column_name, ccu.table_schema AS foreign_table_schema, ccu.table_name AS foreign_table_name, ccu.column_name AS foreign_column_name, rc.update_rule, rc.delete_rule FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema JOIN information_schema.referential_constraints rc ON rc.constraint_name = tc.constraint_name AND rc.constraint_schema = tc.table_schema WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema IN ('accounting','catalog','reviews') ORDER BY tc.table_schema, tc.table_name;"
```

Output đã ghi nhận:

| Table                  | Column     | References                   | Update rule | Delete rule |
| ---------------------- | ---------- | ---------------------------- | ----------- | ----------- |
| `accounting.orderitem` | `order_id` | `accounting.order(order_id)` | `NO ACTION` | `CASCADE`   |
| `accounting.shipping`  | `order_id` | `accounting.order(order_id)` | `NO ACTION` | `CASCADE`   |

---

## 4. Data Baseline

### 4.1. Exact Row Count

Lệnh kiểm tra:

```powershell
kubectl -n techx-tf4 exec deploy/postgresql -- psql -U root -d otel -c "SELECT 'accounting.order' AS table_name, count(*) FROM accounting.""order"" UNION ALL SELECT 'accounting.orderitem', count(*) FROM accounting.orderitem UNION ALL SELECT 'accounting.shipping', count(*) FROM accounting.shipping UNION ALL SELECT 'catalog.products', count(*) FROM catalog.products UNION ALL SELECT 'reviews.productreviews', count(*) FROM reviews.productreviews ORDER BY table_name;"
```

Output đã ghi nhận:

| Table                    | Exact row count |
| ------------------------ | --------------: |
| `accounting.order`       |          175460 |
| `accounting.orderitem`   |          322301 |
| `accounting.shipping`    |          175460 |
| `catalog.products`       |              10 |
| `reviews.productreviews` |              50 |

Kết luận:

- Evidence dùng exact `COUNT(*)`.
- Không dùng `pg_stat_user_tables.n_live_tup` làm evidence chính.

### 4.2. Sequence Baseline

Lệnh kiểm tra:

```powershell
kubectl -n techx-tf4 exec deploy/postgresql -- psql -U root -d otel -c "SELECT max(id) AS max_productreview_id FROM reviews.productreviews;"
kubectl -n techx-tf4 exec deploy/postgresql -- psql -U root -d otel -c "SELECT last_value, is_called FROM reviews.productreviews_id_seq;"
```

Output đã ghi nhận:

| Check                                      | Value |
| ------------------------------------------ | ----- |
| `MAX(reviews.productreviews.id)`           | `50`  |
| `reviews.productreviews_id_seq.last_value` | `50`  |
| `reviews.productreviews_id_seq.is_called`  | `t`   |

Kết luận:

- Sequence hiện khớp với max ID tại thời điểm baseline.
- Sau restore/DMS full load cần verify/reset sequence trên RDS trước cutover.

---

## 5. Backup Artifacts

### 5.1. Local Backup Artifacts

Schema dump:

| Field  | Value                                                              |
| ------ | ------------------------------------------------------------------ |
| File   | `postgresql-schema-20260720-124528.sql`                            |
| Size   | `4434` bytes                                                       |
| SHA256 | `3311E0D93FFA8C21BC670C55AB786ADFB7B0400172864D49B6DA1469D9CC3675` |

Data dump:

| Field        | Value                                                              |
| ------------ | ------------------------------------------------------------------ |
| File         | `postgresql-data-20260720-124933.dump`                             |
| Format       | PostgreSQL custom dump                                             |
| Size         | `9091111` bytes                                                    |
| Pod SHA256   | `2b4c2c1d6e15f0c28c219dcd4ee33b62172679a0a6b039c8c91a76742e75d12d` |
| Local SHA256 | `2B4C2C1D6E15F0C28C219DCD4EE33B62172679A0A6B039C8C91A76742E75D12D` |

Dump list:

| Field  | Value                                                              |
| ------ | ------------------------------------------------------------------ |
| File   | `postgresql-data-20260720-124933.list`                             |
| Size   | `1624` bytes                                                       |
| SHA256 | `2F6AB8B1C239D4C6A1E3F65453820AE6F91ACAF9F104A0FCCFE6E0FEDD2CF9B6` |

Ghi chú:

- Backup valid là `postgresql-data-20260720-124933.dump`, vì local SHA256 khớp pod SHA256.
- Raw backup artifacts không được commit vào Git.

### 5.2. S3 Backup Location

Terraform output sau apply:

| Field       | Value                                                                  |
| ----------- | ---------------------------------------------------------------------- |
| Bucket name | `tf4-postgresql-migration-backups-511825856493-us-east-1`              |
| Bucket ARN  | `arn:aws:s3:::tf4-postgresql-migration-backups-511825856493-us-east-1` |
| Prefix      | `rel15/`                                                               |

Backup prefix:

```text
s3://tf4-postgresql-migration-backups-511825856493-us-east-1/rel15/precutover/20260720-124933/
```

Uploaded objects:

| Object                                  |    Size |
| --------------------------------------- | ------: |
| `postgresql-data-20260720-124933.dump`  | 9091111 |
| `postgresql-data-20260720-124933.list`  |    1624 |
| `postgresql-schema-20260720-124528.sql` |    4434 |

S3 list output:

```text
2026-07-20 13:41:48    9091111 postgresql-data-20260720-124933.dump
2026-07-20 13:41:59       1624 postgresql-data-20260720-124933.list
2026-07-20 13:42:04       4434 postgresql-schema-20260720-124528.sql
```

Head object check cho data dump:

```json
{
    "Size": 9091111,
    "ETag": "\"ca564b3d572fb02613a2bb4458267fb4-2\"",
    "Encryption": "AES256",
    "LastModified": "2026-07-20T06:41:48+00:00"
}
```

Kết luận:

- Backup data dump đã được upload lên S3.
- Object size trên S3 khớp local valid dump size.
- Server-side encryption là `AES256`.

---

## 6. S3 Backup Bucket Controls

### 6.1. Lifecycle Retention

Lệnh kiểm tra:

```powershell
aws s3api get-bucket-lifecycle-configuration --bucket tf4-postgresql-migration-backups-511825856493-us-east-1 --profile tf4 --region us-east-1
```

Output đã ghi nhận:

```json
{
    "Rules": [
        {
            "Expiration": {
                "Days": 7
            },
            "ID": "expire-rel15-postgresql-backups-after-7-days",
            "Filter": {
                "Prefix": "rel15/"
            },
            "Status": "Enabled",
            "NoncurrentVersionExpiration": {
                "NoncurrentDays": 1
            },
            "AbortIncompleteMultipartUpload": {
                "DaysAfterInitiation": 1
            }
        }
    ]
}
```

Kết luận:

- Backup objects dưới prefix `rel15/` có lifecycle expiration 7 ngày.
- Noncurrent versions expire sau 1 ngày.
- Incomplete multipart upload abort sau 1 ngày.

### 6.2. Public Access Block

Lệnh kiểm tra:

```powershell
aws s3api get-public-access-block --bucket tf4-postgresql-migration-backups-511825856493-us-east-1 --profile tf4 --region us-east-1
```

Output đã ghi nhận:

```json
{
    "PublicAccessBlockConfiguration": {
        "BlockPublicAcls": true,
        "IgnorePublicAcls": true,
        "BlockPublicPolicy": true,
        "RestrictPublicBuckets": true
    }
}
```

Kết luận:

- Bucket chặn public ACL và public policy.
- Backup artifacts không public.

### 6.3. Versioning

Lệnh kiểm tra:

```powershell
aws s3api get-bucket-versioning --bucket tf4-postgresql-migration-backups-511825856493-us-east-1 --profile tf4 --region us-east-1
```

Output đã ghi nhận:

```json
{
    "Status": "Enabled"
}
```

Kết luận:

- Bucket versioning đã bật.

---

## 7. Rollback Notes

Rollback source hiện tại:

- PostgreSQL self-hosted trong EKS namespace `techx-tf4`.
- Deployment `postgresql` vẫn `1/1 Ready`.
- PVC `postgresql-pvc` vẫn `Bound`.
- Service `postgresql` vẫn là `ClusterIP` nội bộ.

Trước khi cutover:

- Có thể rollback bằng cách tiếp tục giữ app dùng PostgreSQL in-cluster.
- Không có dữ liệu mới chỉ tồn tại trên RDS nếu app chưa được cutover.

Sau khi RDS đã nhận write mới:

- Không được switch thẳng endpoint về PostgreSQL cũ nếu chưa xử lý delta.
- Runtime schema hiện không có `created_at`, `updated_at`, `deleted_at`, nên việc xác định delta `UPDATE/DELETE` sau cutover khó hơn.
- Cần bổ sung cơ chế audit/timestamp hoặc reverse CDC trước khi cho phép rollback post-write an toàn.
- Nếu delta không xác định chắc, ưu tiên fix-forward trên RDS thay vì rollback thủ công.

---

## 8. Kết luận

Subtask `Capture PostgreSQL pre-cutover backup and baseline` đã có các evidence chính:

- Source PostgreSQL pod/service/PVC đã được xác nhận.
- Source PostgreSQL version đã được xác nhận.
- Schema/table, PK/FK và identity inventory đã được ghi nhận.
- Exact row count cho các bảng quan trọng đã được ghi nhận.
- Sequence baseline đã được ghi nhận.
- Schema dump, custom data dump và dump list đã được tạo.
- Valid data dump đã được verify bằng SHA256 giữa pod và local.
- Backup artifacts đã được upload lên S3 private bucket.
- S3 bucket đã bật encryption, versioning, public access block và lifecycle retention 7 ngày.

Không có plaintext credential hoặc raw backup data được commit vào Git.
