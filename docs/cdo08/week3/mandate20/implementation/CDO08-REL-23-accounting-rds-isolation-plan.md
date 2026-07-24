# CDO08-REL-23 - Accounting Schema-Level Recovery Implementation Plan

**Owner:** CDO08 Reliability + Infra
**Team:** CDO08
**Task:** CDO08-REL-23
**Subtask:** Object inventory · Isolated shared-RDS PITR procedure · Automate export/restore · Validate & production-safe cutover runbook
**Ngày ghi nhận:** 2026-07-24

## 1. Mục Tiêu

RDS PITR hoạt động ở cấp instance. Ba schema `catalog`/`accounting`/`reviews` hiện sống chung 1 instance `techx-tf4-postgresql` (database `otel`). Nếu cần khôi phục `accounting` (sổ cái order — `Critical`, không tái tạo được) về một mốc thời gian trước sự cố, restore-in-place cả instance sẽ kéo theo `catalog`/`reviews` về cùng mốc đó, làm mất dữ liệu mới ghi không liên quan gì tới sự cố của `accounting`.

Subtask này xây một quy trình recovery không bao giờ restore-in-place cả instance: PITR toàn instance ra 1 bản sao tạm, cách ly → export riêng schema `accounting` từ bản đó → validate trên database drill → đưa vào production qua cutover có kiểm soát. `accounting` vẫn ở chung instance vật lý với `catalog`/`reviews` như hiện tại — không tách sang instance riêng thường trực, tránh chi phí/độ phức tạp nuôi 2 instance song song vĩnh viễn.

Quy trình gồm 4 subtask, chạy tuần tự:

| # | Subtask | Trạng thái |
|---|---|---|
| 1 | Schema object inventory | Đã hoàn thành — §4 |
| 2 | Restore-to-point-in-time ra instance cách ly | Kế hoạch — §5 |
| 3 | Tự động hoá export/restore vào database drill | Kế hoạch — §6 |
| 4 | Validate + production-safe cutover runbook | Kế hoạch — §7 |

## 2. Facts Hạ Tầng Đã Xác Minh

Scan trực tiếp trên AWS/RDS, thời điểm 2026-07-24:

| Field | Value |
|---|---|
| Instance nguồn | `techx-tf4-postgresql` |
| Database | `otel` |
| Engine | postgres 17.9, `db.t4g.micro`, Multi-AZ |
| Storage | 20 GiB gp3 |
| Publicly accessible | false |
| Security Group | `sg-0fbc6edd9ae2742d1` (Node-to-SG) |
| DB Subnet Group | `techx-tf4-postgresql-private` |
| Backup retention | 7 ngày |
| Latest restorable time | 2026-07-24T05:42:34Z (~real-time, continuous log backup) |
| Instance create time | 2026-07-19T14:12:01Z |
| Master password | `manage_master_user_password=true` — Secrets Manager tự sinh secret mới cho mỗi instance identifier mới |

## 3. Ràng Buộc Nền Tảng

- Schema `accounting` không có cột timestamp (`order`/`orderitem`/`shipping`) — không lọc được "dữ liệu phát sinh sau mốc X" bằng giá trị cột, mọi so sánh trước/sau phải dùng diff tập `order_id`.
- Role ứng dụng thật là `techx_app` (không phải `otelu` như `init.sql` gốc — file đó predate migration RDS).
- 0 cross-schema dependency — đã xác minh bằng query live, không FK nào nối `accounting` với `catalog`/`reviews`.
- Owner của cả 3 bảng là `postgres` (master), không phải `techx_app` — mọi thao tác restore/DDL trong plan này dùng credential master, không dùng `techx_app`.

## 4. Subtask 1 - Schema Object Inventory (Đã Hoàn Thành)

Evidence lấy sống 2026-07-24 qua pod tạm (`pg-inspect`, đã xoá sau khi dùng), kết nối bằng secret production.

**Object inventory:**

| Object | Kết quả |
|---|---|
| Tables | `order` (PK `order_id` text), `orderitem` (PK ghép `order_id`+`product_id`), `shipping` (PK `shipping_tracking_id` text) |
| Sequences | 0 |
| Indexes | 3 unique index tự sinh từ PK, không index phụ |
| Constraints | 3 PRIMARY KEY + 2 FOREIGN KEY, cả 2 FK đều `ON DELETE CASCADE` → `"order"` |
| Functions | 0 |
| Extensions (toàn DB `otel`) | Chỉ `plpgsql` (mặc định hệ thống) |
| Schema/table owner | `postgres` |

**Roles/privileges:** `techx_app` có SELECT/INSERT/UPDATE/DELETE/TRUNCATE trên cả 3 bảng.

**Baseline (2026-07-24):** `order` = 205,891 · `orderitem` = 377,846 · `shipping` = 205,891. Orphan check 2 chiều: 0 dòng.

**Validation checklist dùng cho mọi lần restore sau này:**

| # | Kiểm tra | Điều kiện đạt |
|---|---|---|
| 1 | `order_count` | = baseline tại đúng mốc restore đang xét |
| 2 | `shipping_count` = `order_count` | Quan hệ 1:1 |
| 3 | `orderitem_count` ≥ `order_count` | ~1.83 item/order tại baseline hiện tại |
| 4 | Orphan `orderitem`→`order` | 0 dòng |
| 5 | Orphan `shipping`→`order` | 0 dòng |
| 6 | Privilege `techx_app` sau restore | Đủ 5 quyền trên cả 3 bảng, owner vẫn `postgres` |

Kỳ vọng đã đạt: có schema object inventory · không còn dependency chưa rõ · có validation checklist và expected row relationships.

## 5. Subtask 2 - Restore-To-Point-In-Time Ra Instance Cách Ly

**Quyết định thiết kế:**

| Vấn đề | Quyết định | Lý do |
|---|---|---|
| Terraform hoá instance tạm? | Không — thuần AWS CLI/script | Instance sinh-diệt mỗi lần recovery, không nên buộc Terraform state quản lý resource ephemeral |
| Security Group | Tạo SG riêng mỗi lần chạy, ingress 5432 từ EKS node SG | Xoá SG độc lập cùng lúc dọn instance, không đụng SG production |
| Sizing | Mirror nguồn: `db.t4g.micro`, gp3, 20 GiB | An toàn, instance sống rất ngắn nên không cần tối ưu nhỏ hơn |
| Credential | Giữ `--manage-master-user-password` → Secrets Manager tự sinh secret mới | Đây chính là "temporary validation credential", không cần dựng cơ chế cấp phát riêng |

**Script:** `docs/cdo08/week3/mandate20/scripts/rel-23/01-restore-pitr-isolated.ps1`. Guard sẵn: `RestoreTime` phải nằm trong `[EarliestRestorableTime, LatestRestorableTime]` của nguồn, tự tra node SG qua tag cluster (không dùng tên wildcard mong manh), mirror `--db-parameter-group-name` của nguồn (restore mặc định không kế thừa).

```powershell
.\01-restore-pitr-isolated.ps1 -RestoreTime 2026-07-20T10:00:00Z
```

Kỳ vọng sau khi chạy:

```text
Instance:  rel23-accounting-pitr-<run-id>  (available)
Endpoint:  <ghi ra file rel23-pitr-<run-id>.json>
SecretArn: <MasterUserSecret cua instance moi>
Production techx-tf4-postgresql: khong bi dung toi (khong ModifyDBInstance nao)
```

Cleanup: `docs/cdo08/week3/mandate20/scripts/rel-23/02-cleanup-pitr-isolated.ps1 -TargetId <id> -TmpSgId <sg-id>` — xoá instance (`--skip-final-snapshot`, không cần vì nguồn còn nguyên) và SG tạm.

## 6. Subtask 3 - Tự Động Hoá Export/Restore Vào Database Drill

Drill database nằm ngay trên chính instance tạm ở Subtask 2 — tạo 1 database mới `otel_drill`, restore schema `accounting` vào đó, không đụng bản dữ liệu gốc `otel` đã PITR. Vì cùng instance/cùng role namespace, không phát sinh vấn đề role mapping.

**Scripts:**

```powershell
.\03-export-accounting.ps1 -IsolatedInstanceId rel23-accounting-pitr-<run-id>
.\04-restore-accounting-drill.ps1 -IsolatedInstanceId rel23-accounting-pitr-<run-id> -DumpPath .\accounting-<run-id>.dump
```

Ghi chú kỹ thuật:

- `pg_dump --schema=accounting` tự giới hạn phạm vi — không có cách nào lấy lẫn `catalog`/`reviews` vào dump.
- Restore drill dùng `--no-owner --no-privileges` và **không** dùng `--role=techx_app` — master mới của instance tạm không phải thành viên role đó (`SET ROLE` sẽ fail `permission denied to set role`); quan hệ membership này chưa từng tồn tại kể cả trên instance nguồn.
- Idempotent: `DROP DATABASE IF EXISTS otel_drill` + `CREATE DATABASE` mỗi lần chạy.
- Sequence: hiện schema không có sequence nào (§4) — script không hardcode giả định này, nếu sau này có thì `pg_dump`/`pg_restore` tự xử lý đúng.
- Không bao giờ echo `PGPASSWORD` ra log; credential lấy qua Secrets Manager (`Get-RdsMasterCreds`), giữ trong biến môi trường của pod tạm.

Kỳ vọng: dump chỉ chứa `accounting` objects, restore hoàn thành vào `otel_drill`, script chạy lại từ đầu không cần chỉnh tay.

## 7. Subtask 4 - Validate Và Production-Safe Cutover Runbook

### 7.1. Validate trên drill

Chạy `07-validate-production.ps1 -DbInstanceIdentifier rel23-accounting-pitr-<run-id> -Database otel_drill` — so `otel.accounting` (bản PITR gốc) với `otel_drill.accounting` (vừa restore), kỳ vọng khớp tuyệt đối 1:1 (row count, order_id diff theo file, tổng `item_cost_units`/`item_cost_nanos`, orphan check).

Giới hạn quan trọng: các kiểm tra này chỉ chứng minh **drill khớp bản PITR** và **cấu trúc không hỏng** — không chứng minh bản PITR **đầy đủ**, vì schema không có cột timestamp. Nguồn chân lý duy nhất cho tính đầy đủ là Kafka topic `orders` (§7.3).

### 7.2. Runbook cutover production

Chạy khi có sự cố thật, sau khi §7.1 PASS:

| Bước | Hành động | Ghi chú an toàn |
|---|---|---|
| R.0 | Backup schema `accounting` production hiện tại ra file, trước khi đụng gì | Rollback checkpoint bắt buộc |
| R.1 | `05-write-freeze.ps1`: scale `accounting` về 0 + gate xác nhận 0 connection `techx_app` trong `pg_stat_activity` | `accounting` là 1 role, không phải 1 process — gate loại trừ job/cron/psql thủ công khác đang dùng chung role |
| R.1b | Reset offset consumer group `accounting` về `RestoreTime` (xem §7.3) | Chỉ thực hiện được khi group không còn active member — đúng khớp cửa sổ ngay sau R.1 |
| R.2 | `06-import-production.ps1`: `ALTER SCHEMA accounting RENAME TO accounting_old`, import bản đã validate dưới tên `accounting` bằng credential master | Rename trước khi import, không `DROP SCHEMA` trực tiếp — cho phép rollback tức thời |
| R.3 | `07-validate-production.ps1` trên `accounting` production | Phải PASS hết mới sang bước tiếp; nếu fail vì thiếu order trong rollback window, xem nhánh remediation §7.3 trước khi coi là fail chặn cứng |
| R.4 | `rollback-01-restore-old-schema.ps1` nếu R.3 fail | `DROP SCHEMA accounting CASCADE` → `ALTER SCHEMA accounting_old RENAME TO accounting` — luôn có đường lùi tới R.6 |
| R.5 | `08-reopen-traffic.ps1`: scale `accounting` về 1, theo dõi consumer lag về 0 | Bao gồm cả phần replay rollback-window nếu đã chạy R.1b |
| R.6 | `09-cleanup-old-schema.ps1 -Confirm` | Không xoá `accounting_old` ngay sau R.5 — giữ như rollback checkpoint cho tới khi xác nhận ổn định |

Xác nhận `catalog`/`reviews` không đổi: đếm row 2 schema đó trước R.1 và sau R.6, phải bằng nhau tuyệt đối.

### 7.3. Kafka rollback-window — điểm quan trọng nhất

Restore về `RestoreTime` (trước sự cố) làm mất mọi order **hợp lệ** phát sinh trong khoảng `RestoreTime → R.1` — khác với khoảng `R.1 → R.5` (order còn kẹt trong Kafka chưa consume, tự động có lại khi resume).

| Khoảng | Tên | Cơ chế phục hồi |
|---|---|---|
| `RestoreTime → R.1` | Rollback window | Offset **đã commit từ trước** — KHÔNG tự phục hồi, phải reset offset thủ công |
| `R.1 → R.5` | Freeze window | Order còn trong Kafka chưa consume — tự động replay khi resume |

Cơ chế commit offset thật (`Consumer.cs`): `EnableAutoCommit = true`, hoàn toàn độc lập với `SaveChanges()` — không transactional với DB write. Vì `ProcessMessage` bọc toàn bộ xử lý trong 1 `try/catch` ngoài cùng, message bị redeliver gây PK violation trên `order_id` (insert thẳng, không upsert) → EF Core rollback nguyên transaction → log "Order parsing failed", không tạo dòng trùng, không tạo orphan, pod không crash. Kết luận: **replay chồng lấn lên vùng đã restore là an toàn về dữ liệu** — chỉ không phân biệt được trong log "duplicate mong đợi" với "lỗi thật".

Retention check bắt buộc trước cutover: topic `orders` không có `log.retention.hours`/`retention.ms` tường minh trong `aws_msk_configuration.orders` — đang chạy theo default broker (168h = 7 ngày), trùng hợp khớp `backup_retention_period` của RDS nhưng chưa được pin cứng (xem §9).

Thủ tục reset offset (chạy trong R.1b, sau khi R.1 xác nhận 0 connection ghi):

```powershell
# Ben trong 06-import-production.ps1 (goi kafka-consumer-groups.sh qua pod tam)
kafka-consumer-groups.sh --bootstrap-server $KAFKA_ADDR --command-config client.properties `
  --group accounting --topic orders --reset-offsets --to-datetime <RestoreTime> --execute
```

Nhánh remediation khi R.3 fail vì thiếu order trong rollback window: không coi là fail chặn cứng ngay — xác nhận đã chạy R.1b, đợi consumer lag về 0 sau R.5, rồi validate lại. Theo dõi số dòng log "Order parsing failed" của pod `accounting` trong lúc replay — nên xấp xỉ đúng số order đã tồn tại sẵn do overlap; nếu cao bất thường thì dừng lại điều tra.

### 7.4. Đo tổng recovery time

```text
T_total = (Subtask 2: t_restore_request -> t_instance_available)
        + (Subtask 3: t_export_start -> t_restore_drill_done)
        + (Subtask 4: t_R1_freeze_start -> t_R5_traffic_reopened)
```

Ghi từng mốc thời gian thật khi rehearsal. `T_total` ≤ 2 giờ → PASS; nếu vượt, ghi rõ FAIL + remediation (dự kiến Subtask 2 provisioning instance chiếm nhiều thời gian nhất — RDS restore-to-point-in-time cho `db.t4g.micro`/20GB thường mất 10-30 phút).

## 8. Rollback Và Safety

- Trước R.2 (chưa import): rollback = không làm gì, `accounting` production chưa hề bị đụng, chỉ cần xoá instance tạm (Subtask 2 cleanup) và không cần chạy tiếp.
- Sau R.2, trước R.3 PASS: `rollback-01-restore-old-schema.ps1` — vì R.2 chỉ rename (không drop), `accounting_old` luôn còn nguyên để khôi phục tức thời.
- Sau R.5 (đã reopen traffic) nhưng phát hiện lỗi muộn: dùng bản backup `R.0` (file `.dump` riêng, lưu ngoài schema) làm nguồn khôi phục thủ công — không còn `accounting_old` sau R.6 nếu đã cleanup.
- Nếu đã chạy R.1b (reset offset Kafka) rồi phải rollback: đánh giá lại tính nhất quán Kafka/DB trước khi mở lại traffic — offset đã bị kéo lùi nhưng DB có thể đã quay về trạng thái trước đó (xem cảnh báo trong `rollback-01-restore-old-schema.ps1`).
- Không script nào trong bộ này xoá dữ liệu production ngoài `accounting_old` (chỉ ở R.6, yêu cầu `-Confirm` tường minh) và chỉ sau khi đã xác nhận ổn định.

## 9. Rủi Ro Cần Xác Nhận

- **MSK `orders` retention chưa pin cứng** — đang dựa vào default broker (168h), khuyến nghị pin tường minh `log.retention.hours=168` trong `infra/terraform/msk.tf` (`aws_msk_configuration.orders`) để khoá cứng ràng buộc "Kafka retention ≥ RDS PITR window" dùng ở §7.3. Chưa sửa trong lượt này vì đụng infra đang chạy thật, cần quyết định riêng.
- **Image `apache/kafka:3.9.0` cho pod client Kafka chưa được smoke-test thật** — chọn image chính thức của Apache Kafka project (khớp `kafka_versions=3.9.x` trong `msk.tf`) để đảm bảo `bin/kafka-consumer-groups.sh` tồn tại đúng path, nhưng chưa xác minh được bằng cách chạy thật (không có kết nối để tra manifest image tại thời điểm viết). Cần smoke-test 1 lần trước rehearsal đầu tiên.
- **Node SG lookup dựa vào tag `aws:eks:cluster-name`/`aws:eks:cluster-resource-controller`** — cần xác nhận đúng 1 SG khớp filter trên cluster thật trước khi chạy `01-restore-pitr-isolated.ps1` lần đầu.
- **GAP-06 (gap register), RTO/RPO matrix (`accounting`: 2 giờ), cost estimate cho phương án procedure-only** — 3 tài liệu này cần cập nhật khớp hướng đã chốt ở đây, chưa làm trong lượt này.
- **Chưa có PM sign-off** — không chạy Subtask 2-4 thật (tạo instance tạm, export/restore, cutover production) cho tới khi kế hoạch này được duyệt.

## 10. Ngoài Phạm Vi

Subtask 1 đã thực thi thật (evidence §4). Bộ script PowerShell cho Subtask 2-4 (`docs/cdo08/week3/mandate20/scripts/rel-23/*.ps1`) đã viết và qua kiểm tra parse cú pháp, nhưng **chưa chạy thật lần nào** — chưa tạo instance tạm, chưa export/restore thật, chưa chạy cutover runbook trên production. Không có thay đổi Terraform/chart/GitOps ở subtask này — `accounting` vẫn ở nguyên chỗ, không đổi connection string, không đổi secret, không đổi instance.
