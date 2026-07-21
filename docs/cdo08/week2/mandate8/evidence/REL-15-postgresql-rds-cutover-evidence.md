# REL-15 PostgreSQL RDS Cutover Evidence

**Người thực hiện:** Hoàng Nam
**Team:** CDO08
**Task:** CDO08-REL-15
**Subtask:** PostgreSQL RDS cutover / Chuyển traffic ứng dụng sang Amazon RDS PostgreSQL
**Ngày ghi nhận:** 2026-07-21

Tài liệu này ghi lại evidence cho bước cutover PostgreSQL từ PostgreSQL self-hosted trong EKS sang Amazon RDS PostgreSQL sau khi hoàn tất restore schema/data, DMS full-load + CDC, writer freeze, CDC catch-up và strict parity trước cutover.

Phạm vi tài liệu:

- Xác nhận RDS target có đủ schema/table app trước cutover.
- Xác nhận DMS full-load + CDC đã phục vụ catch-up trước cutover.
- Xác nhận strict row-count parity pass 5/5 bảng trong scope tại cutover gate.
- Xác nhận app đã chuyển sang dùng RDS PostgreSQL thông qua GitOps/ESO secret contract.
- Ghi lại trạng thái workload, SLO sau cutover và các mitigation runtime đã xử lý.

Tài liệu này không chứa plaintext credential, không in connection string có password thật, và không xác nhận cleanup DMS/NLB bridge đã hoàn tất. Cleanup sau observation window được ghi ở phần follow-up.

---

## 1. Tóm tắt Kết quả

REL-15 PostgreSQL đã hoàn tất cutover ứng dụng sang Amazon RDS PostgreSQL sau khi restore schema/data, chạy DMS full-load + CDC, freeze writer, đợi CDC catch-up và xác nhận strict row-count parity.

Kết quả chính:

| Hạng mục                            | Trạng thái | Evidence                                                                    |
| ----------------------------------- | ---------- | --------------------------------------------------------------------------- |
| RDS target có schema/table ứng dụng | PASS       | 5 bảng tồn tại trên RDS                                                     |
| DMS source/target endpoint          | PASS       | 2 endpoint `successful`                                                     |
| DMS full-load + CDC                 | PASS       | Task `techx-tf4-postgresql-forward` chạy `full-load-and-cdc`, progress 100% |
| Strict parity trước cutover         | PASS       | 5/5 bảng row count khớp sau writer freeze và CDC catch-up                   |
| App cutover sang RDS                | PASS       | Các service dùng `rds-postgres-secret` và RDS endpoint                      |
| Runtime/SLO sau cutover             | PASS       | Browse 100%, Cart 100%, Checkout 100%, p95 khoảng 40 ms sau khi ổn định     |

## 2. Phạm vi Dữ liệu

Các bảng thuộc phạm vi REL-15:

| Schema       | Table            | Vai trò                   |
| ------------ | ---------------- | ------------------------- |
| `accounting` | `order`          | Dữ liệu đơn hàng          |
| `accounting` | `orderitem`      | Dữ liệu item của đơn hàng |
| `accounting` | `shipping`       | Dữ liệu vận chuyển        |
| `catalog`    | `products`       | Dữ liệu catalog sản phẩm  |
| `reviews`    | `productreviews` | Dữ liệu đánh giá sản phẩm |

Tên bảng `accounting."order"` cần quote vì `order` là keyword trong SQL.

## 3. Target RDS và Secret Contract

RDS target dùng database `otel` tại endpoint nội bộ:

```text
techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com:5432
```

Credential contract được quản lý qua AWS Secrets Manager và External Secrets Operator:

| Thành phần               | Giá trị                                                      |
| ------------------------ | ------------------------------------------------------------ |
| AWS Secrets Manager path | `techx/tf4/rds-postgres`                                     |
| Kubernetes Secret        | `techx-tf4/rds-postgres-secret`                              |
| Secret keys dùng bởi app | `dotnet-conn-string`, `go-conn-string`, `python-conn-string` |
| App user                 | `techx_app`                                                  |

Các connection string đã được kiểm tra ở runtime và đều trỏ về RDS endpoint. Nội dung password không được ghi vào evidence.

Ví dụ trạng thái đã mask:

```text
Dotnet: Host=techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com;Port=5432;Database=otel;Username=techx_app;Password=***;Ssl Mode=Require;Trust Server Certificate=true
Python: postgresql://techx_app:***@techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com:5432/otel?sslmode=require
Go:     postgres://techx_app:***@techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com:5432/otel?sslmode=require
```

## 4. Restore và Grants

Schema đã được restore vào RDS trước khi start migration task. Kết quả kiểm tra table list trên RDS:

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

RDS app user `techx_app` đã được cấp quyền trên các schema/table ứng dụng:

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

Default privileges cũng đã được cấu hình để các object tạo mới trong phạm vi schema ứng dụng có quyền phù hợp cho `techx_app`.

## 5. DMS Full-load và CDC

DMS task đang dùng migration type `full-load-and-cdc`:

```json
{
    "Id": "techx-tf4-postgresql-forward",
    "Status": "running",
    "MigrationType": "full-load-and-cdc",
    "FullLoadProgressPercent": 100,
    "TablesLoaded": 5,
    "TablesLoading": 0,
    "TablesQueued": 0,
    "TablesErrored": 0,
    "LastFailureMessage": null
}
```

DMS endpoint source đã được cấu hình PostgreSQL CDC theo `test_decoding` và tắt DDL capture:

```json
{
    "Id": "techx-tf4-postgresql-source",
    "Status": "active",
    "Extra": "PluginName=test_decoding;CaptureDdls=false"
}
```

Connection test cho cả source và target đều thành công:

```json
[
    {
        "Endpoint": "techx-tf4-postgresql-rds-target",
        "Status": "successful",
        "LastFailureMessage": null
    },
    {
        "Endpoint": "techx-tf4-postgresql-source",
        "Status": "successful",
        "LastFailureMessage": null
    }
]
```

## 6. Strict Parity Trước Cutover

Trước khi cutover app, writer vào PostgreSQL self-hosted đã được freeze, DMS CDC được đợi catch-up, sau đó chạy strict parity:

```bash
SOURCE_FROZEN=true bash docs/cdo08/week2/mandate8/scripts/postgres/06-parity-counts.sh
```

Kết quả:

```text
table                                source       target   status
accounting."order"                   202012       202012     PASS
accounting.orderitem                 370687       370687     PASS
accounting.shipping                  202012       202012     PASS
catalog.products                         10           10     PASS
reviews.productreviews                   50           50     PASS
[INFO] reviews.productreviews sequence on target:
 max_productreview_id | last_value | is_called
----------------------+------------+-----------
                   50 |         50 | t
(1 row)

[OK] Row count parity passed.
```

Kết luận: 5/5 bảng quan trọng đạt row-count parity tại cutover gate.

## 7. Cutover Ứng dụng Sang RDS

Sau khi parity pass, GitOps/app config được chuyển sang dùng managed PostgreSQL data source:

```yaml
managedData:
    enabled: true
    postgresql:
        enabled: true
```

Kết quả runtime sau sync:

```text
kubectl -n argocd get application techx-corp
NAME         SYNC STATUS   HEALTH STATUS
techx-corp   Synced        Healthy
```

Các workload chính sau cutover:

```text
NAME              READY   UP-TO-DATE   AVAILABLE
checkout          2/2     2            2
shipping          2/2     2            2
accounting        1/1     1            1
product-reviews   1/1     1            1
product-catalog   2/2     2            2
load-generator    1/1     1            1
```

Các service PostgreSQL client đã được kiểm tra connection string runtime:

| Service           | Evidence                                                                          |
| ----------------- | --------------------------------------------------------------------------------- |
| `accounting`      | `DB_CONNECTION_STRING` trỏ tới RDS endpoint, database `otel`                      |
| `product-reviews` | Python connection string trỏ tới RDS endpoint, database `otel`, `sslmode=require` |
| `product-catalog` | Dùng key `go-conn-string` trong `rds-postgres-secret`                             |

## 8. SLO Sau Cutover

Sau khi cutover và xử lý các vấn đề telemetry/runtime không thuộc blocker PostgreSQL, dashboard SLO ghi nhận:

| Chỉ số                 | Kết quả          |
| ---------------------- | ---------------- |
| Browse non-5xx         | `100.000%`       |
| Storefront p95 latency | khoảng `40.2 ms` |
| Cart success           | `100.000%`       |
| Checkout success       | `100.000%`       |

Kết quả này xác nhận app flow đã phục hồi ổn định sau khi traffic chạy với RDS PostgreSQL target.

## 9. Sự cố Trong Quá trình và Mitigation

Các lỗi đã gặp và đã xử lý trong quá trình chuẩn bị/cutover:

| Sự cố                                    | Nguyên nhân                                                       | Mitigation                                                       | Trạng thái           |
| ---------------------------------------- | ----------------------------------------------------------------- | ---------------------------------------------------------------- | -------------------- |
| DMS không lấy được secret                | DMS subnet/SG thiếu đường ra Secrets Manager                      | Thêm egress HTTPS phù hợp cho DMS security group                 | Resolved             |
| DMS endpoint create fail                 | IAM role trust dùng service principal không đúng vùng             | Đổi trust sang `dms.us-east-1.amazonaws.com`                     | Resolved             |
| DMS CDC gọi `pglogical`                  | DMS mặc định thử `pglogical` trong khi source không có extension  | Cấu hình `PluginName=test_decoding`                              | Resolved             |
| DMS DDL artifact fail                    | DMS cố tạo DDL audit artifact trên source                         | Cấu hình `CaptureDdls=false`                                     | Resolved             |
| App user thiếu quyền target              | `techx_app` chưa có đủ schema/table privileges                    | Grant USAGE/CRUD và default privileges                           | Resolved             |
| Connection string Python/Go sai database | URI bị nối sai làm database bị parse thành `=require`             | Sửa secret contract connection string về `/otel?sslmode=require` | Resolved             |
| Checkout SLO giảm sau cutover            | Vấn đề telemetry/exporter ở currency/quote làm request bị timeout | Hotfix runtime telemetry path; SLO phục hồi                      | Resolved sau cutover |

Các vấn đề telemetry được ghi nhận là sự cố runtime độc lập với trạng thái parity/restore của PostgreSQL. Không có PostgreSQL blocker còn mở tại thời điểm evidence này.

## 10. Ghi chú về Post-cutover Count

Sau cutover, nếu so sánh lại source self-hosted với RDS target có thể thấy RDS target cao hơn source. Đây là kỳ vọng hợp lệ vì writer đã chuyển sang RDS, ví dụ:

```text
accounting."order" source=202012 target=202014 DIFF
```

Kết quả này không phủ định strict parity trước cutover. Nó cho thấy các write mới sau cutover đang đi vào RDS target.

## 11. Cleanup và Follow-up

Các hạng mục còn lại sau khi observation window được chấp thuận:

1. Dừng hoặc archive DMS forward task khi không còn cần CDC từ source sang target.
2. Dọn temporary migration bridge/NLB và các security group rule chỉ phục vụ migration nếu không còn được dùng.
3. Giữ lại backup/evidence trước khi ngắt hẳn PostgreSQL self-hosted.
4. Reverse RDS-to-EKS task chưa được tạo vì chưa có write-back credential về EKS; rollback dữ liệu tự động theo reverse CDC không nằm trong phạm vi PR này.
5. Tiếp tục theo dõi SLO Checkout/Browse/Cart trong observation window sau cutover.

## 12. Kết luận

REL-15 PostgreSQL migration sang RDS đã đạt các acceptance criteria chính:

- RDS target có đủ schema/table cho app cutover.
- DMS full-load + CDC đã chạy và phục vụ catch-up trước cutover.
- Strict row-count parity pass 5/5 bảng trước khi chuyển traffic ghi sang RDS.
- App đã chạy với RDS PostgreSQL target qua GitOps/ESO secret contract.
- SLO chính sau cutover đã phục hồi về trạng thái đạt ngưỡng.

Trạng thái đề xuất: PostgreSQL cutover hoàn tất, chuyển sang observation và cleanup có kiểm soát.
