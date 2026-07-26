# CDO08-REL-23 - Recovery Flow Walkthrough (5 Bước)

**Task:** CDO08-REL-23
**Ngày ghi nhận:** 2026-07-25
**Liên quan:** [CDO08-REL-23-accounting-rds-isolation-plan.md](CDO08-REL-23-accounting-rds-isolation-plan.md)

Tài liệu này mô tả luồng 5 bước để khôi phục schema `accounting`, cộng thêm 1 bước Rollback dùng khi có lỗi giữa chừng.

## Timeline Ví Dụ (dùng xuyên suốt tài liệu)

| Giờ | Sự kiện |
|---|---|
| 2026-07-25 09:00 | Trạng thái sạch, chưa có gì bất thường |
| 2026-07-25 09:15 | Sự cố bắt đầu (bug ghi đè / migration hỏng) |
| 2026-07-25 09:47 | Team phát hiện sự cố qua alert |
| 2026-07-25 10:00 | Bắt đầu chạy quy trình REL-23 |
| **`RestoreTime` = 2026-07-25 09:05** | 10 phút trước sự cố (09:15) — mốc chọn để restore |

**Phụ thuộc vào Kafka/MSK:** Bước 4 ("Bù dữ liệu qua Kafka") giả định Kafka **còn sống và còn giữ message** trong khoảng `RestoreTime` → lúc dừng ghi. Nếu MSK cũng gặp sự cố mất dữ liệu cùng lúc, bước này không tự khôi phục được. — phụ thuộc vào cơ chế archive/restore riêng của MSK, thuộc phạm vi **CDO08-REL-22** (MSK Connect S3 Sink, GAP-02).

---

## Bước 1 - Chuẩn Bị (Prerequisite)

- Xác định `RestoreTime` — mốc thời gian trước sự cố cần khôi phục về.
- Xác định mục tiêu trước khi bắt đầu: **RTO ≤ 2 giờ**, **RPO ≤ 15 phút**.
- Tạo Security Group tạm (ingress 5432 từ SG node production).
- Tạo 1 RDS instance tạm bằng PITR — instance này dùng để restore file dump vào ở Bước 3.

(script: `01-restore-pitr-isolated.ps1`)

```powershell
# Tao SG tam, cho phep ingress 5432 tu SG node production
aws ec2 create-security-group --group-name rel23-pitr-tmp-<run-id> --vpc-id <vpc-id> `
    --description "Temp SG for REL-23 isolated PITR"
aws ec2 authorize-security-group-ingress --group-id <tmp-sg-id> `
    --protocol tcp --port 5432 --source-group <node-sg-id>

# Restore-to-point-in-time ra instance moi, tach biet
aws rds restore-db-instance-to-point-in-time `
    --source-db-instance-identifier techx-tf4-postgresql `
    --target-db-instance-identifier techx-tf4-postgresql-restore-<run-id> `
    --restore-time 2026-07-25T09:05:00Z `
    --no-publicly-accessible `
    --db-subnet-group-name techx-tf4-postgresql-private `
    --db-parameter-group-name techx-tf4-postgresql17-dms `
    --vpc-security-group-ids <tmp-sg-id> `
    --db-instance-class db.t4g.micro `
    --no-multi-az
```

---

## Bước 2 - Dump Schema `accounting`

Dump schema `accounting` từ instance tạm ra 1 file.

(script: `03-export-accounting.ps1`)

```powershell
pg_dump --schema=accounting --format=custom --file=accounting.dump
```

Kết quả: 1 file `.dump`, kèm log kích thước (bytes) và 2 mốc thời gian `t_export_start`/`t_export_done`. Từ mốc `t_restore_request` (Bước 1) tới đây, RTO bắt đầu được tính và cộng dồn qua các bước sau.

---

## Bước 3 - Tạo DB Mới, Restore Từ File Dump

(script: `04-restore-accounting-drill.ps1`)

```sql
DROP DATABASE IF EXISTS otel_drill;
CREATE DATABASE otel_drill;
```

```powershell
pg_restore --dbname=otel_drill --no-owner --no-privileges --clean --if-exists accounting.dump
```

Tạo database rỗng `otel_drill` trên instance tạm, restore file dump vào đó.

**Đo dữ liệu có nguy cơ mất:** so tập `order_id` giữa baseline production (trước sự cố) và bản vừa restore:

```sql
-- Chay tren baseline production va tren otel_drill, roi diff 2 file
COPY (SELECT order_id FROM accounting."order" ORDER BY 1) TO STDOUT;
```

Số `order_id` có ở baseline nhưng không có ở bản restore = số order có nguy cơ mất nếu dừng ở đây, không làm Bước 4.

**RTO tính đến hiện tại:** `t_restore_drill_done - t_restore_request`.

---

## Bước 4 - Đưa Dữ Liệu Vào Production

- **Backup trước** — dump schema `accounting` đang chạy thật ra 1 file riêng. Lý do: có đường lùi nếu các bước sau thất bại.

  ```powershell
  pg_dump --schema=accounting --format=custom --file=prod-backup.dump
  ```

- **Dừng ghi** — scale `accounting` về 0, xác nhận không còn connection nào đang ghi. Lý do: đảm bảo không ai ghi thêm trong lúc import.

  (script: `05-write-freeze.ps1`)

  ```powershell
  kubectl scale deployment/accounting -n techx-tf4 --replicas=0
  ```
  ```sql
  SELECT count(*) FROM pg_stat_activity WHERE usename='techx_app' AND pid <> pg_backend_pid();
  ```

- **Bù dữ liệu qua Kafka** — reset offset consumer group `accounting` về `RestoreTime`. Lý do: order phát sinh giữa `RestoreTime` và lúc dừng ghi đã mất khỏi bản restore, phải replay lại từ Kafka.

  ```powershell
  kafka-consumer-groups.sh --bootstrap-server $KAFKA_ADDR --command-config client.properties `
      --group accounting --topic orders --reset-offsets --to-datetime 2026-07-25T09:05:00Z --execute
  ```

- **Đổi tên rồi mới import** — đổi tên schema `accounting` hiện tại thành `accounting_old`, sau đó import bản đã kiểm chứng vào tên `accounting`. Lý do: không xoá bản cũ ngay, để có thể khôi phục tức thời nếu import lỗi.

  (script: `06-import-production.ps1`)

  ```sql
  ALTER SCHEMA accounting RENAME TO accounting_old;
  ```
  ```powershell
  pg_restore --dbname=otel --schema=accounting accounting-validated.dump
  ```

- **Validate lại trên production** — chạy lại checklist trên schema `accounting` vừa import. Lý do: xác nhận đúng trước khi cho phép mở lại traffic.

  (script: `07-validate-production.ps1`)

  ```sql
  SELECT count(*) FROM accounting."order";
  SELECT count(*) FROM accounting.orderitem;
  SELECT count(*) FROM accounting.shipping;
  ```

- **Mở lại traffic** — scale `accounting` về 1, theo dõi consumer lag về 0. Lý do: xác nhận Kafka đã bù xong dữ liệu trước khi coi là hoàn tất.

  (script: `08-reopen-traffic.ps1`)

  ```powershell
  kubectl scale deployment/accounting -n techx-tf4 --replicas=1
  kafka-consumer-groups.sh --bootstrap-server $KAFKA_ADDR --command-config client.properties `
      --describe --group accounting
  ```

- **Dọn `accounting_old`** — chỉ xoá sau khi đã theo dõi ổn định một thời gian. Lý do: đây là rollback checkpoint cuối cùng, không xoá vội.

  (script: `09-cleanup-old-schema.ps1`)

  ```sql
  DROP SCHEMA accounting_old CASCADE;
  ```

---

## Bước 5 - Xoá Instance Tạm

- Xoá ngay sau khi Bước 3 xong — không cần đợi tới hết Bước 4.
- Không cần snapshot cuối vì instance nguồn (production) vẫn còn nguyên.
- Dọn luôn Security Group tạm.

(script: `02-cleanup-pitr-isolated.ps1`)

```powershell
aws rds delete-db-instance --db-instance-identifier <id> --skip-final-snapshot --delete-automated-backups
aws ec2 delete-security-group --group-id <sg-id>
```

---

## Rollback (chỉ dùng khi có lỗi)

**Rollback ở đây nghĩa là gì:** không phải "quay lại trước sự cố" — đó chính là việc cả 5 bước trên đang làm. Rollback ở đây là: nếu **thao tác khôi phục (Bước 4)** thất bại hoặc validate ra sai (bước "Validate lại trên production" không đạt), thì huỷ bỏ chính thao tác import đó, đưa production quay lại đúng trạng thái **ngay trước khi Bước 4 bắt đầu** — tức là lưới an toàn cho chính quy trình recovery, không phải xử lý sự cố gốc.

**Vì sao làm được ngay lập tức:** Bước 4 chỉ đổi tên schema cũ (`accounting` → `accounting_old`), không xoá — nên bản cũ luôn còn nguyên cho tới khi chủ động dọn (bước cuối của Bước 4).

- Xảy ra lỗi **sau khi đổi tên, trước khi dọn `accounting_old`**: xoá bản import lỗi, đổi tên `accounting_old` trở lại thành `accounting`.

  (script: `rollback-01-restore-old-schema.ps1`)

  ```sql
  DROP SCHEMA accounting CASCADE;
  ALTER SCHEMA accounting_old RENAME TO accounting;
  ```

- Xảy ra lỗi **sau khi đã dọn `accounting_old`** (phát hiện muộn): không còn schema cũ để đổi tên lại — dùng file backup đã tạo ở đầu Bước 4 (`pg_dump` trước khi đụng gì) để khôi phục thủ công.
- Nếu đã chạy bước "bù dữ liệu qua Kafka" rồi mới rollback: cần kiểm tra lại tính nhất quán Kafka/DB trước khi mở lại traffic — offset đã bị kéo lùi nhưng DB có thể đã quay về trạng thái trước đó.
