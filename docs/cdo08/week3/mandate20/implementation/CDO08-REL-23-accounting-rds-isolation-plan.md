# CDO08-REL-23 - Accounting Schema-Level Recovery Implementation Plan

**Owner:** CDO08 Reliability + Infra
**Team:** CDO08
**Task:** CDO08-REL-23
**Subtask:** Object inventory · Isolated shared-RDS PITR procedure · Automate export/restore · Validate & production-safe cutover runbook
**Ngày ghi nhận:** 2026-07-24

## 1. Mục Tiêu

RDS PITR hoạt động ở cấp instance. `catalog`/`accounting`/`reviews` sống chung 1 instance `techx-tf4-postgresql`. Khôi phục `accounting` (sổ cái order, `Critical`) bằng restore-in-place cả instance sẽ kéo theo mất dữ liệu `catalog`/`reviews`.

Quy trình: PITR ra instance tạm cách ly → export schema `accounting` → validate trên database drill → cutover production có kiểm soát. `accounting` vẫn ở chung instance vật lý với `catalog`/`reviews` — không tách instance riêng thường trực.

## 2. Facts Hạ Tầng

| Field | Value |
|---|---|
| Instance nguồn | `techx-tf4-postgresql`, database `otel` |
| Engine | postgres 17.9, `db.t4g.micro`, Multi-AZ, 20 GiB gp3 |
| Security Group | `sg-0fbc6edd9ae2742d1` |
| Backup retention | 7 ngày (continuous log backup) |
| Owner 3 bảng `accounting` | `postgres` (không phải `techx_app`) |

## 3. Ràng Buộc Quan Trọng

- Schema `accounting` không có cột timestamp — so sánh trước/sau phải dùng diff tập `order_id`.
- IAM role vận hành chỉ đọc được secret `techx/tf4/rds-postgres*` (`techx_app`), không đọc được `MasterUserSecret` của bất kỳ RDS instance nào.
- `rds:RestoreDBInstanceToPointInTime`/`DeleteDBInstance`/`ModifyDBInstance` chỉ được phép khi target instance identifier khớp `techx-tf4-postgresql-restore-*`.
- **Prerequisite bắt buộc trước Subtask 4:** `GRANT postgres TO techx_app;` trên `techx-tf4-postgresql` (chạy 1 lần, ngoài phạm vi script) — để `techx_app` dùng được `SET ROLE postgres` cho các thao tác DDL.

## 4. Subtask 1 - Object Inventory (Hoàn Thành)

Đã xác nhận: object inventory đầy đủ, 0 cross-schema dependency, roles/privileges, baseline + validation checklist. Evidence: [CDO08-REL-23-object-inventory-evidence.md](../evidence/CDO08-REL-23-object-inventory-evidence.md).

## 5. Subtask 2 - PITR Ra Instance Cách Ly

Script: `scripts/rel-23/01-restore-pitr-isolated.ps1` (cleanup: `02-cleanup-pitr-isolated.ps1`).

Việc cần làm:

- Guard `RestoreTime` nằm trong cửa sổ restore-được của nguồn.
- SG tạm, ingress 5432 lấy từ rule 5432 sẵn có trên SG nguồn (không đoán qua tag).
- Restore-to-point-in-time, tên instance `techx-tf4-postgresql-restore-<run-id>`, mirror parameter group nguồn.
- Sau khi available: tự đặt master password biết trước qua `ModifyDBInstance` (không dùng managed secret — IAM không cho đọc).
- Ghi `Endpoint`/`MasterPassword` ra file JSON cục bộ, xoá sau khi dùng xong Subtask 2-3.

```powershell
.\01-restore-pitr-isolated.ps1 -RestoreTime 2026-07-20T10:00:00Z
```

Output mẫu:

```text
[INFO] t_restore_request=2026-07-25T08:00:00.000Z
[INFO] Waiting for techx-tf4-postgresql-restore-<run-id> available...
[INFO] t_instance_available=2026-07-25T08:22:14.000Z
[INFO] Waiting for password change to apply...
[OK] Isolated PITR instance ready: techx-tf4-postgresql-restore-<run-id>
     Endpoint : techx-tf4-postgresql-restore-<run-id>.xxxxx.us-east-1.rds.amazonaws.com
     TmpSgId  : sg-xxxxxxxxxxxxxxxxx
[NOTE] KHONG cap nhat production endpoint o buoc nay.
[NOTE] Cleanup: .\02-cleanup-pitr-isolated.ps1 -TargetId techx-tf4-postgresql-restore-<run-id> -TmpSgId sg-xxxxxxxxxxxxxxxxx
[WARN] .\rel23-pitr-<run-id>.json CHUA MAT KHAU THAT (MasterPassword) - dung cho 03/06, xoa file nay sau khi xong Subtask 2-3.
```

Cleanup (`02-cleanup-pitr-isolated.ps1 -TargetId <id> -TmpSgId <sg-id>`):

```text
[INFO] Deleting isolated instance techx-tf4-postgresql-restore-<run-id>...
[OK] Instance techx-tf4-postgresql-restore-<run-id> deleted.
[INFO] Deleting temp SG sg-xxxxxxxxxxxxxxxxx...
[OK] SG sg-xxxxxxxxxxxxxxxxx deleted.
[OK] Cleanup Subtask 2 hoan tat - khong con hạ tang nao con lai tu buoc PITR isolated.
```

## 6. Subtask 3 - Export/Restore Vào Database Drill

Scripts: `03-export-accounting.ps1`, `04-restore-accounting-drill.ps1`.

Drill (`otel_drill`) nằm ngay trên instance tạm — không cần hạ tầng thêm. `pg_dump --schema=accounting` tự giới hạn phạm vi, không lẫn `catalog`/`reviews`. Idempotent (`DROP DATABASE IF EXISTS` + `CREATE`).

```powershell
.\03-export-accounting.ps1 -PitrInfoPath .\rel23-pitr-<run-id>.json
.\04-restore-accounting-drill.ps1 -PitrInfoPath .\rel23-pitr-<run-id>.json -DumpPath .\accounting-<run-id>.dump
```

Output mẫu (`03-export-accounting.ps1`):

```text
[INFO] t_export_start=2026-07-25T08:25:00.000Z
[OK] Dump written: .\accounting-<run-id>.dump (2481392 bytes)
[INFO] t_export_done=2026-07-25T08:25:18.000Z
[NOTE] --schema=accounting tu gioi han pham vi - khong the lan catalog/reviews vao dump nay.
[INFO] Dump path (dung cho 04-restore-accounting-drill.ps1 va sau khi validate, cho 06-import-production.ps1): .\accounting-<run-id>.dump
```

Output mẫu (`04-restore-accounting-drill.ps1`):

```text
[OK] Restored into otel_drill for validation.
[NOTE] Chay tiep 07-validate-production.ps1 -Database otel_drill de doi chieu voi checklist truoc khi cutover production.
```

## 7. Subtask 4 - Validate + Production-Safe Cutover Runbook

Validate drill: `07-validate-production.ps1 -PitrInfoPath ... -Database otel_drill` — đối chiếu row count/orphan/tổng tiền với bản PITR gốc. PASS chỉ chứng minh drill khớp bản PITR, không chứng minh bản PITR đầy đủ (schema không có cột timestamp) — nguồn chân lý là Kafka (§8).

Runbook cutover, chạy khi có sự cố thật, sau khi validate drill PASS:

| Bước | Hành động |
|---|---|
| R.0 | Backup `accounting` production ra file (rollback checkpoint) |
| R.1 | `05-write-freeze.ps1` — scale `accounting` về 0, gate 0 connection `techx_app` |
| R.1b | Reset offset Kafka group `accounting` về `RestoreTime` (§8) |
| R.2 | `06-import-production.ps1` — rename `accounting`→`accounting_old`, import bản đã validate |
| R.3 | `07-validate-production.ps1` trên production — fail thì thử remediation §8 trước khi rollback |
| R.4 | `rollback-01-restore-old-schema.ps1` nếu R.3 vẫn fail |
| R.5 | `08-reopen-traffic.ps1` — scale về 1, theo dõi consumer lag về 0 |
| R.6 | `09-cleanup-old-schema.ps1 -Confirm` — xoá `accounting_old` sau khi ổn định |

Xác nhận `catalog`/`reviews` không đổi row count trước R.1 và sau R.6.

Output mẫu từng bước:

```text
# 05-write-freeze.ps1 (R.1)
[INFO] t_R1_freeze_start=2026-07-25T09:00:00.000Z
[INFO] R.1 - Scaling deployment/accounting to 0 in techx-tf4...
[INFO] Gate: cho 0 active connection cua role techx_app (tru chinh session gate nay)...
[OK] R.1 hoan tat - 0 active connection techx_app. Write-freeze confirmed.

# 06-import-production.ps1 (R.0 + R.1b + R.2)
[INFO] R.0 - Backup schema accounting production truoc khi dung gi...
[OK] R.0 backup luu tai .\accounting-production-backup-<run-id>.dump - GIU LAI, day la rollback checkpoint duy nhat truoc R.2.
[INFO] R.1b - Reset offset consumer group 'accounting' ve RestoreTime=2026-07-20T10:00:00Z...
[OK] R.1b hoan tat - offset group 'accounting' da reset ve 2026-07-20T10:00:00Z.
[INFO] R.2 - Rename accounting -> accounting_old, import ban da validate...
[OK] R.2 hoan tat.

# 07-validate-production.ps1 (R.3)
[RESULT] order_count      = 205891
[RESULT] orderitem_count  = 377846
[RESULT] shipping_count   = 205891
[RESULT] orphan orderitem = 0
[RESULT] orphan shipping  = 0
[OK] Validation PASS.

# 08-reopen-traffic.ps1 (R.5)
[INFO] R.5 - Scaling deployment/accounting to 1 in techx-tf4...
[INFO] Theo doi consumer lag group 'accounting' toi khi ve 0 (timeout 3600s)...
[OK] Consumer lag = 0.
[INFO] t_R5_traffic_reopened=2026-07-25T09:18:00.000Z

# 09-cleanup-old-schema.ps1 -Confirm (R.6)
[INFO] R.6 - Xoa schema accounting_old...
[OK] R.6 hoan tat - da don dep rollback checkpoint accounting_old.

# rollback-01-restore-old-schema.ps1 (chi khi R.3 fail, R.4)
[WARN] R.4 - Rollback: xoa ban import loi, khoi phuc accounting_old...
[OK] Rollback hoan tat - schema accounting da khoi phuc ve dung trang thai truoc R.2.
```

## 8. Kafka Rollback-Window

Restore về `RestoreTime` làm mất order phát sinh trong `RestoreTime → R.1` (rollback window — offset đã commit từ trước, không tự phục hồi), khác với `R.1 → R.5` (freeze window — Kafka tự bù khi resume).

`Consumer.cs` dùng `EnableAutoCommit=true`, không transactional với DB write. Redeliver gây PK violation trên `order_id` nhưng bị catch/log ("Order parsing failed"), không tạo dòng trùng/orphan — replay chồng lấn lên vùng đã restore an toàn về dữ liệu.

Retention topic `orders` đang dùng default broker (168h), chưa pin cứng — phải đảm bảo `RestoreTime` nằm trong retention trước khi cutover.

Remediation nếu R.3 fail vì thiếu order trong rollback window: xác nhận đã chạy R.1b, đợi consumer lag về 0 sau R.5, validate lại — không rollback ngay.

## 9. Đo RTO

```text
T_total = (t_restore_request -> t_instance_available)
        + (t_export_start -> t_restore_drill_done)
        + (t_R1_freeze_start -> t_R5_traffic_reopened)
```

`T_total` ≤ 2 giờ → PASS; vượt thì ghi FAIL + remediation.

## 10. Rollback Và Safety

- Trước R.2: rollback = không làm gì, chỉ xoá instance tạm.
- Sau R.2, trước R.3 PASS: `rollback-01-restore-old-schema.ps1` (rename ngược — `accounting_old` chưa từng bị xoá).
- Sau R.6 (đã cleanup `accounting_old`): dùng file backup R.0 để khôi phục thủ công.
- Không script nào xoá dữ liệu production ngoài `accounting_old` (chỉ R.6, cần `-Confirm`).

## 11. Rủi Ro Cần Xác Nhận

- Pin `log.retention.hours=168` cho MSK `orders` (`infra/terraform/msk.tf`) — chưa làm, cần quyết định riêng.
- GAP-06, RPO/RTO matrix (`accounting`: 2 giờ), cost estimate procedure-only — cần cập nhật riêng.
- Chưa có PM sign-off — không chạy Subtask 2-4 thật cho tới khi được duyệt.

## 12. Ngoài Phạm Vi

Subtask 1 đã thực thi thật. Script PowerShell Subtask 2-4 (`docs/cdo08/week3/mandate20/scripts/rel-23/*.ps1`) đã viết, qua parse-check, **chưa chạy thật**. Không có thay đổi Terraform/chart/GitOps.
