# REL-15 PostgreSQL Restore Evidence

**Owner:** Hoàng Nam
**Team:** CDO08
**Task:** CDO08-REL-15
**Subtask:** Restore PostgreSQL data into RDS target
**Ngày cập nhật:** 2026-07-21

Tài liệu này ghi lại evidence cho bước restore schema và dữ liệu PostgreSQL từ PostgreSQL self-hosted trong EKS sang Amazon RDS PostgreSQL bằng AWS DMS.

Phạm vi tài liệu:

- Xác nhận RDS target đã có schema/table app.
- Xác nhận AWS DMS full-load đã hoàn tất cho 5 table.
- Xác nhận DMS CDC đang chạy để tiếp tục đồng bộ write mới từ source sang RDS.
- Ghi lại các lỗi runtime đã gặp và mitigation đã thực hiện.

Tài liệu này không chứa plaintext credential và không xác nhận cutover app sang RDS. Final frozen parity và cutover gate thuộc subtask tiếp theo.

---

## 1. Trạng thái Tổng quan

| Hạng mục                     | Trạng thái  | Ghi chú                                                                     |
| ---------------------------- | ----------- | --------------------------------------------------------------------------- |
| RDS target                   | PASS        | RDS PostgreSQL `available`, private endpoint, DB `otel`.                    |
| Schema restore               | PASS        | RDS có đủ 3 schema và 5 table app.                                          |
| DMS source/target connection | PASS        | Cả source và target endpoint đều `successful`.                              |
| DMS full-load                | PASS        | 5/5 table `Table completed`, `Errored = 0`.                                 |
| DMS CDC                      | RUNNING     | Task đang `running`, log ghi nhận WAL events và target apply tiếp tục chạy. |
| Final frozen parity          | PENDING     | Chưa freeze writer, nên live row-count chỉ là sanity check.                 |
| App cutover                  | NOT STARTED | App vẫn chưa cutover sang RDS.                                              |

---

## 2. Thông tin Runtime Target

| Trường                       | Giá trị                                                                  |
| ---------------------------- | ------------------------------------------------------------------------ |
| Account ID                   | `511825856493`                                                           |
| Region                       | `us-east-1`                                                              |
| Namespace                    | `techx-tf4`                                                              |
| Database                     | `otel`                                                                   |
| RDS endpoint                 | `techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com`          |
| RDS port                     | `5432`                                                                   |
| DMS replication instance     | `techx-tf4-postgresql-dms`                                               |
| DMS replication instance ARN | `arn:aws:dms:us-east-1:511825856493:rep:JPOXJ6J6NVEEVK6IDAJGAE23HY`      |
| DMS task ID                  | `techx-tf4-postgresql-forward`                                           |
| DMS task ARN                 | `arn:aws:dms:us-east-1:511825856493:task:7SDVOIB6RVGXJP3M5WK72BNYKY`     |
| Source endpoint ARN          | `arn:aws:dms:us-east-1:511825856493:endpoint:UZXAJZANSFBARPVQFIKK5MBF4M` |
| Target endpoint ARN          | `arn:aws:dms:us-east-1:511825856493:endpoint:52US7I3JLRBG7NPFNJMFSDB2KY` |

Cách xử lý credential:

- Source DMS credential path: `techx/tf4/dms-postgres-source`
- Target app credential path: `techx/tf4/rds-postgres`
- DMS endpoints dùng Secrets Manager reference.
- Không commit PostgreSQL password vào Git/Jira/Slack.

---

## 3. Evidence Restore Schema

RDS target đã được xác nhận là chưa có table app trước khi restore schema:

```text
 table_schema | table_name
--------------+------------
(0 rows)
```

Schema được restore từ schema dump pre-cutover:

```text
postgresql-schema-20260720-124528.sql
```

Kết quả lệnh restore:

```text
CREATE SCHEMA
CREATE SCHEMA
CREATE SCHEMA
CREATE TABLE
CREATE TABLE
CREATE TABLE
CREATE TABLE
CREATE TABLE
ALTER TABLE
ALTER TABLE
ALTER TABLE
ALTER TABLE
ALTER TABLE
ALTER TABLE
CREATE INDEX
ALTER TABLE
ALTER TABLE
```

Verify schema/table trên RDS sau restore:

```text
 table_schema |   table_name
--------------+----------------
 accounting   | order
 accounting   | orderitem
 accounting   | shipping
 catalog      | products
 reviews      | productreviews
(5 rows)
```

Kết luận:

- RDS target đã có đủ app schemas: `accounting`, `catalog`, `reviews`.
- RDS target đã có đủ 5 application tables cần thiết cho DMS full-load.

---

## 4. Các Fix Runtime cho DMS Endpoint và Task

Trong quá trình restore/backfill, một số blocker runtime đã được phát hiện và xử lý trước khi DMS full-load chạy thành công.

### 4.1. Source CDC Plugin

DMS run ban đầu cố dùng `pglogical` và fail vì source PostgreSQL image không có extension này:

```text
ERROR: could not access file "pglogical": No such file or directory
ERROR: relation "pglogical.replication_set" does not exist
```

Runtime probe xác nhận `test_decoding` hoạt động:

```text
SELECT * FROM pg_create_logical_replication_slot('dms_probe_test_decoding','test_decoding');
```

Mitigation:

```text
PluginName=test_decoding
```

### 4.2. DDL Capture

Sau khi chuyển sang `test_decoding`, DMS tiếp tục cố tạo DDL audit artifact ở source và fail:

```text
ddl_create_db_artifact(...) failed in creating 'TABLE' awsdms_ddl_audit
```

Scope migration hiện tại là restore schema trước, sau đó migrate data/CDC row changes. Runtime DDL capture không cần thiết trong migration window này.

Mitigation:

```text
PluginName=test_decoding;CaptureDdls=false
```

Verify runtime endpoint:

```json
{
    "Id": "techx-tf4-postgresql-source",
    "Status": "active",
    "Extra": "PluginName=test_decoding;CaptureDdls=false"
}
```

### 4.3. Target Grants cho DMS/App User

DMS target endpoint connect bằng RDS app user `techx_app`. Sau khi restore schema, app user ban đầu chưa có `USAGE` trên app schemas:

```text
 schema_name | can_usage | can_create
-------------+-----------+------------
 accounting  | f         | f
 catalog     | f         | f
 dms_control | t         | t
 reviews     | f         | f
```

Mitigation đã apply trên RDS:

```sql
GRANT USAGE ON SCHEMA accounting, catalog, reviews TO techx_app;

GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE
ON ALL TABLES IN SCHEMA accounting, catalog, reviews
TO techx_app;

GRANT USAGE, SELECT, UPDATE
ON ALL SEQUENCES IN SCHEMA accounting, catalog, reviews
TO techx_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA accounting, catalog, reviews
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO techx_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA accounting, catalog, reviews
GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO techx_app;
```

Verify sau khi grant:

```text
 schema_name | can_usage | can_create
-------------+-----------+------------
 accounting  | t         | f
 catalog     | t         | f
 dms_control | t         | t
 reviews     | t         | f
(4 rows)
```

Quyền trên tables:

```text
 schema_name |   table_name   | can_insert | can_update | can_delete | can_select
-------------+----------------+------------+------------+------------+------------
 accounting  | order          | t          | t          | t          | t
 accounting  | orderitem      | t          | t          | t          | t
 accounting  | shipping       | t          | t          | t          | t
 catalog     | products       | t          | t          | t          | t
 reviews     | productreviews | t          | t          | t          | t
(5 rows)
```

---

## 5. Evidence DMS Full-load

DMS task được restart bằng `reload-target` sau khi target grants được fix.

Output monitor:

```json
{
    "Id": "techx-tf4-postgresql-forward",
    "Status": "running",
    "StopReason": null,
    "LastFailureMessage": null,
    "Progress": 100,
    "Loaded": 5,
    "Loading": 0,
    "Queued": 0,
    "Errored": 0
}
```

Table statistics:

| Table                    | State             | Full-load rows | Validation       | Failed records |
| ------------------------ | ----------------- | -------------: | ---------------- | -------------: |
| `catalog.products`       | `Table completed` |             10 | `No primary Key` |              0 |
| `accounting.shipping`    | `Table completed` |         178026 | `No primary Key` |              0 |
| `reviews.productreviews` | `Table completed` |             50 | `Validated`      |              0 |
| `accounting.order`       | `Table completed` |         178026 | `No primary Key` |              0 |
| `accounting.orderitem`   | `Table completed` |         326678 | `No primary Key` |              0 |

Kết luận:

- DMS full-load đã hoàn tất cho cả 5 app tables.
- Hiện không còn table nào ở trạng thái errored.
- DMS validation không phải nguồn final parity cho toàn bộ bảng vì một số bảng báo `No primary Key`.
- Exact row-count parity sẽ được xử lý riêng trong REL-15 parity subtask.

---

## 6. Evidence Runtime CDC

DMS task tiếp tục `running` sau full-load, giữ CDC active trong lúc app vẫn write vào source PostgreSQL.

DMS logs gần đây ghi nhận WAL capture và target apply vẫn đang tiếp diễn:

```text
Event fetched from wal log
Applied record 143893 to target
Applied record 153713 to target
Applied record 158709 to target
Applied record 163257 to target
Applied record 167841 to target
Task is running
```

Kết luận:

- DMS đã qua giai đoạn full-load và đang chạy ongoing CDC.
- App chưa cutover sang RDS.
- Source PostgreSQL vẫn là active write path cho tới cutover gate.

---

## 7. Live Sanity Count

Live row-count check được chạy khi source PostgreSQL vẫn đang nhận write:

```text
table                                source       target   status
accounting."order"                   185768       185790     DIFF
accounting.orderitem                 340806       340839     DIFF
accounting.shipping                  185857       185878     DIFF
catalog.products                         10           10     PASS
reviews.productreviews                   50           50     PASS
```

Diễn giải:

- `catalog.products` và `reviews.productreviews` khớp trong live sanity check.
- Các bảng accounting vẫn đang thay đổi trong lúc count được thu thập, nên chênh lệch trước writer freeze là expected.
- Đây không phải final parity evidence.

Final parity phải chạy sau:

```text
freeze writer -> wait for CDC catch-up -> run exact row counts/checksums/sequences
```

---

## 8. Evidence Sequence

RDS `reviews.productreviews_id_seq` đã được reset sau full-load.

Trước khi reset:

```text
 max_productreview_id | last_value | is_called
----------------------+------------+-----------
                   50 |          1 | f
```

Lệnh reset:

```sql
SELECT setval(
  pg_get_serial_sequence('reviews.productreviews','id'),
  COALESCE((SELECT MAX(id) FROM reviews.productreviews), 1),
  true
);
```

Sau khi reset:

```text
 max_productreview_id | last_value | is_called
----------------------+------------+-----------
                   50 |         50 | t
```

Kết luận:

- Identity sequence đã biết trên RDS đã được align với dữ liệu đã load.
- Sequence verification cần được chạy lại trong final cutover parity.

---

## 9. Cleanup

Các Kubernetes resources tạm dùng cho verification/grants đã được xóa:

```text
pod/rds-admin-grant deleted
pod/rds-app-permission-check deleted
secret/rds-admin-temp deleted
secret/rds-app-temp deleted
```

Verify:

```text
kubectl -n techx-tf4 get pod | Select-String "rds-parity-check|rds-sequence-reset|rds-admin-grant|rds-app-permission-check"
```

Output rỗng.

---

## 10. Việc còn lại

Trạng thái restore/backfill của subtask 2:

- Schema restore: PASS
- DMS full-load: PASS
- DMS CDC: RUNNING
- RDS has data: PASS
- Migration blocker: chưa ghi nhận blocker mới sau target grants và DMS endpoint fixes

Việc còn lại trước cutover:

- Subtask 3: chạy final parity sau writer freeze và CDC catch-up.
- Verify exact row counts cho cả 5 tables.
- Verify sample/checksum khi cần.
- Re-check sequence values.
- Chuẩn bị cutover/rollback evidence trước khi switch app traffic.

Cutover chưa được thực hiện.
