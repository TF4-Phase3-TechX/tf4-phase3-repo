# CDO08-REL-27 — Shared-RDS Accounting PITR Recovery and MSK Archive Replay Runbook

| Thuộc tính | Giá trị |
|---|---|
| Mandate | 20 — DR, backup và restore |
| Phạm vi | Shared Amazon RDS PostgreSQL `techx-tf4-postgresql`, database `otel`, schema `accounting`; MSK `techx-tf4-orders`; topic/archive được xác nhận ở preflight |
| Owner vận hành | CDO08 Reliability / Incident Commander (IC) được chỉ định |
| Approver | Hải (PM) và Nguyên (Tech Lead), hoặc người được ủy quyền trong incident |
| Múi giờ chuẩn | UTC; giờ địa phương chỉ được ghi bổ sung |
| Nguyên tắc | Restore cô lập, không ghi đè source, không tạo recovery RDS thường trực |
| Trạng thái tài liệu | Runbook thực thi; giá trị trong `<...>` phải được điền và lưu vào evidence trước khi chạy |

## 1. Mục tiêu và ranh giới

Runbook khôi phục schema `accounting` từ shared RDS về một thời điểm trước sự cố bằng PITR, kiểm tra dữ liệu trong RDS cô lập, sau đó hướng dẫn cutover có kiểm soát khi xảy ra incident thật. Các order event đến sau PITR timestamp được bù từ archive S3 của MSK.

Runbook không:

- restore đè lên RDS nguồn;
- biến RDS restore thành recovery environment thường trực;
- tự động cho phép ghi/cutover khi validation chưa PASS;
- coi broker retention là backup;
- khẳng định MSK Connect/S3 archive tồn tại nếu preflight chưa chứng minh được;
- thay đổi target RPO/RTO đã ký trong ADR.

Drill dừng sau validation và cleanup; không cutover production. Các bước write freeze/cutover/rollback ở mục 8 chỉ dùng cho incident thật, có approval.

## 2. Vai trò, escalation và quy ước

| Vai trò | Trách nhiệm |
|---|---|
| IC — Hải/PM hoặc delegate | Mở incident, quyết định freeze/cutover/rollback, chấp nhận business impact |
| Recovery Lead — Nguyên/Tech Lead hoặc delegate | Chọn restore point, điều phối RDS restore, ký technical verdict |
| DB Operator | Restore PITR, export/import schema, chạy validation SQL |
| Streaming Operator | Xác minh archive, lập manifest, replay và kiểm tra missing/duplicate |
| Application Owner | Freeze/resume accounting writes, smoke test ứng dụng |
| Evidence Recorder | Ghi UTC timestamp, account/region/resource context, command/output và approval |
| Security/Cloud Admin | Cấp quyền khẩn cấp hoặc xử lý KMS/IAM; không chia sẻ secret vào evidence |

Escalate ngay cho IC và Tech Lead khi: không xác định được corruption window; PITR timestamp ngoài restorable window; archive thiếu/không giải mã được; có active writer ngoài kiểm soát; validation sai lệch; RPO/RTO có nguy cơ vượt target; hoặc thao tác yêu cầu bỏ deletion protection/giảm retention.

Quy ước:

- `[A]`: tự động hoặc command có kết quả xác định.
- `[M]`: quyết định/phê duyệt thủ công.
- Mọi timestamp dùng ISO-8601 UTC, ví dụ `2026-07-24T03:15:00Z`.
- Không đưa password, connection string, SCRAM secret hoặc token vào log/evidence.
- Mỗi command phải lưu cả command, stdout/stderr, exit code, UTC timestamp và AWS identity.

## 3. Evidence workspace và biến phiên chạy

Chạy trong shell đã đăng nhập đúng AWS account. PowerShell mẫu:

```powershell
$env:AWS_REGION = "<region>"
$env:RUN_ID = "rel27-" + (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$env:RDS_SOURCE_ID = "techx-tf4-postgresql"
$env:RDS_RESTORE_ID = "$($env:RDS_SOURCE_ID)-dr-$($env:RUN_ID)"
$env:DB_NAME = "otel"
$env:ACCOUNTING_SCHEMA = "accounting"
$env:MSK_CLUSTER_NAME = "techx-tf4-orders"
$env:MSK_TOPIC = "<orders-topic>"
$env:ARCHIVE_BUCKET = "<confirmed-msk-archive-bucket>"
$env:ARCHIVE_PREFIX = "<confirmed-prefix>"
$env:PITR_UTC = "<YYYY-MM-DDTHH:MM:SSZ>"
$env:EVIDENCE_DIR = "docs/cdo08/week3/evidence/$($env:RUN_ID)"
New-Item -ItemType Directory -Path $env:EVIDENCE_DIR
```

**Expected:** thư mục mới nằm dưới `docs/cdo08/week3/evidence/`; tên restore là duy nhất.

**Abort:** biến còn `<...>`, đường dẫn evidence nằm ngoài `week3`, `RUN_ID` trùng, hoặc operator định lưu secret.

Evidence tối thiểu của một lần chạy:

```text
docs/cdo08/week3/evidence/<RUN_ID>/
  00-context.txt
  01-approvals.md
  02-rds-pitr-source.json
  03-restore-events.json
  04-pre-restore-baseline.txt
  05-accounting-export.log
  06-accounting-validation-before.txt
  07-archive-inventory.txt
  08-replay.log
  09-accounting-validation-after.txt
  10-timeline.md
  11-cleanup.txt
  12-verdict.md
```

## 4. Preflight và safety guardrails

### 4.1 [A] Ghi context và clock

```powershell
@(
  "captured_at_utc=$((Get-Date).ToUniversalTime().ToString('o'))"
  "aws_region=$env:AWS_REGION"
  "run_id=$env:RUN_ID"
  "source_rds=$env:RDS_SOURCE_ID"
  "restore_rds=$env:RDS_RESTORE_ID"
  "msk_cluster=$env:MSK_CLUSTER_NAME"
) | Set-Content "$env:EVIDENCE_DIR/00-context.txt"
aws sts get-caller-identity --output json | Add-Content "$env:EVIDENCE_DIR/00-context.txt"
aws configure get region | Add-Content "$env:EVIDENCE_DIR/00-context.txt"
```

**Expected:** account ID, caller ARN, region, source và restore ID hiện rõ; không có secret.

**Abort:** account/region khác approved scope, caller là root, clock lệch đáng kể, hoặc identity không truy vết được.

### 4.2 [M] Go/no-go

Evidence Recorder ghi trong `01-approvals.md`:

- incident/drill ID và loại phiên chạy;
- IC, Recovery Lead, DB Operator, Streaming Operator;
- corruption start/end UTC và nguồn xác định;
- target RPO/RTO lấy nguyên văn/link từ ADR;
- phạm vi chỉ `accounting`;
- cost ceiling và thời hạn cleanup;
- approval cho PITR; riêng incident thật có approval freeze/cutover.

**Expected:** IC và Tech Lead xác nhận bằng tên + UTC timestamp.

**Abort:** chưa có owner, target, corruption window hoặc approval. Drill không được phép chuyển production traffic.

### 4.3 [A] Kiểm tra RDS source, PITR, encryption và network isolation

```powershell
aws rds describe-db-instances --db-instance-identifier $env:RDS_SOURCE_ID `
  --query "DBInstances[0].{ID:DBInstanceIdentifier,Status:DBInstanceStatus,Engine:Engine,Version:EngineVersion,Encrypted:StorageEncrypted,Kms:KmsKeyId,Retention:BackupRetentionPeriod,Earliest:EarliestRestorableTime,Latest:LatestRestorableTime,Public:PubliclyAccessible,Subnet:DBSubnetGroup.DBSubnetGroupName,SGs:VpcSecurityGroups[*].VpcSecurityGroupId}" `
  --output json | Tee-Object "$env:EVIDENCE_DIR/02-rds-pitr-source.json"
```

**Expected:** `available`, PostgreSQL, `Encrypted=true`, `Retention>0`, `Public=false`; `PITR_UTC` nằm giữa `Earliest` và `Latest`.

**Abort:** source không available; backup/PITR không khả dụng; PITR ngoài window; encryption tắt; restore subnet/SG chưa được phê duyệt. Không giảm protection/retention để tiếp tục.

### 4.4 [A] Kiểm tra MSK Connect/S3 archive trước khi phụ thuộc vào replay

```powershell
aws kafkaconnect list-connectors --output json
aws s3api get-bucket-encryption --bucket $env:ARCHIVE_BUCKET
aws s3api get-bucket-versioning --bucket $env:ARCHIVE_BUCKET
aws s3api get-bucket-lifecycle-configuration --bucket $env:ARCHIVE_BUCKET
aws s3api list-objects-v2 --bucket $env:ARCHIVE_BUCKET --prefix $env:ARCHIVE_PREFIX --max-items 10
```

Xác nhận connector ở `RUNNING`, source cluster/topic đúng, không có delivery error, object mới nhất phù hợp cadence/RPO, format/schema version có replay tool tương thích, bucket encrypted và retention đủ bao phủ PITR window.

**Expected:** có connector và object archive bao phủ `(PITR_UTC, freeze/cutoff]`.

**Abort:** repo hiện không định nghĩa MSK Connect/S3 order archive; nếu runtime cũng không có connector, bucket, object manifest hoặc replay contract thì đánh dấu **FAIL — archival/replay unavailable**, tạo remediation và không tuyên bố replay PASS. RDS PITR drill cô lập vẫn có thể tiếp tục nếu IC đồng ý.

### 4.5 [A/M] Xác nhận guardrails

- Chọn DB subnet group private và recovery SG chỉ cho phép DB Operator/replay runner; không dùng application production SG nếu có lựa chọn hẹp hơn.
- Không sửa DNS, Kubernetes Secret hay production selector trong drill.
- Chụp baseline row counts/checksums từ source chỉ khi truy vấn read-only an toàn.
- Xác nhận đủ quota RDS, storage và budget.
- Xác nhận credentials được lấy qua approved secret channel, không đưa vào command history/file evidence.

**Abort:** không tạo được isolation, không có dung lượng/quota, chưa biết active writers, hoặc baseline query gây tải không chấp nhận được.

## 5. Chọn PITR timestamp

### 5.1 [M] Xác định restore point

Recovery Lead lập timeline:

1. `T_last_known_good`: thời điểm cuối dữ liệu được xác minh đúng.
2. `T_corruption_start`: record/log/CloudTrail đầu tiên của lỗi.
3. `T_archive_complete`: object archive mới nhất đã xác minh.
4. Chọn `PITR_UTC < T_corruption_start`, có safety margin phù hợp và nằm trong RDS restorable window.

Không dùng “latest restorable time” nếu nó nằm sau corruption. Với timestamp mơ hồ, chọn điểm sớm hơn và ghi rõ data-loss trade-off; không tự suy đoán timezone.

### 5.2 [A] Kiểm chứng timestamp

```powershell
[DateTimeOffset]::Parse($env:PITR_UTC).ToUniversalTime().ToString("o")
aws rds describe-db-instances --db-instance-identifier $env:RDS_SOURCE_ID `
  --query "DBInstances[0].[EarliestRestorableTime,LatestRestorableTime]" --output table
```

Ghi `PITR_UTC`, lý do, log/evidence nguồn và người phê duyệt vào timeline.

**Expected:** timestamp UTC duy nhất, trước sự cố và trong window.

**Abort:** không chứng minh được điểm trước corruption. Escalate; cân nhắc snapshot cũ hơn nhưng không gọi đó là PITR đạt target.

## 6. Restore shared RDS sang instance cô lập

### 6.1 [A] Bắt đầu đo RTO và tạo restore

Ghi `T0` ngay khi IC tuyên bố bắt đầu recovery. Dùng subnet/SG đã phê duyệt:

```powershell
$env:RTO_START_UTC = (Get-Date).ToUniversalTime().ToString("o")
aws rds restore-db-instance-to-point-in-time `
  --source-db-instance-identifier $env:RDS_SOURCE_ID `
  --target-db-instance-identifier $env:RDS_RESTORE_ID `
  --restore-time $env:PITR_UTC `
  --db-instance-class db.t4g.micro `
  --db-subnet-group-name "<private-db-subnet-group>" `
  --vpc-security-group-ids "<isolated-recovery-sg-id>" `
  --no-publicly-accessible `
  --no-multi-az `
  --tags Key=Purpose,Value=Mandate20-DR Key=RunId,Value=$env:RUN_ID Key=AutoCleanupAfter,Value="<UTC>"
```

`--no-multi-az` chỉ áp dụng cho RDS tạm nhằm kiểm soát chi phí; không thay đổi source. Không chỉ định KMS key khác trừ khi Security/Cloud Admin đã xác nhận quyền decrypt.

**Expected:** API trả DB identifier đúng và status `creating`.

**Abort:** target ID đã tồn tại; command có thể tác động source; subnet public; SG mở rộng; encryption/KMS lỗi; restore point bị AWS từ chối. Không fallback sang source.

### 6.2 [A] Chờ và ghi sự kiện restore

```powershell
aws rds wait db-instance-available --db-instance-identifier $env:RDS_RESTORE_ID
aws rds describe-db-instances --db-instance-identifier $env:RDS_RESTORE_ID `
  --query "DBInstances[0].{ID:DBInstanceIdentifier,Status:DBInstanceStatus,Endpoint:Endpoint.Address,Encrypted:StorageEncrypted,Public:PubliclyAccessible,CreateTime:InstanceCreateTime,SGs:VpcSecurityGroups[*].VpcSecurityGroupId}" `
  --output json | Tee-Object "$env:EVIDENCE_DIR/03-restore-events.json"
```

**Expected:** `available`, encrypted, private, đúng isolated SG. Endpoint chỉ được giữ trong evidence nội bộ nếu policy cho phép.

**Abort:** public accessibility, SG sai, unencrypted, restore vượt RTO threshold, hoặc RDS event báo failure.

### 6.3 [A] Kiểm tra kết nối read-only

Từ approved recovery runner:

```bash
export PGOPTIONS='-c default_transaction_read_only=on'
psql "host=<restore-endpoint> dbname=otel user=<recovery-reader> sslmode=verify-full sslrootcert=<rds-ca>" \
  -v ON_ERROR_STOP=1 -c "select now() at time zone 'utc' as checked_at_utc, current_database(), pg_is_in_recovery();"
```

**Expected:** kết nối TLS thành công vào `otel`; query chỉ đọc.

**Abort:** endpoint là source, TLS verification fail, database/schema thiếu, hoặc credential có quyền ngoài approved scope.

## 7. Export/restore riêng schema accounting và validation

### 7.1 [A] Inventory và baseline trên PITR restore

```bash
psql "$RESTORED_RDS_DSN" -v ON_ERROR_STOP=1 <<'SQL'
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema='accounting'
ORDER BY table_name;

SELECT c.relname AS sequence_name, s.last_value
FROM pg_class c
JOIN pg_namespace n ON n.oid=c.relnamespace
JOIN pg_sequences s ON s.schemaname=n.nspname AND s.sequencename=c.relname
WHERE n.nspname='accounting'
ORDER BY c.relname;
SQL
```

Với từng table `accounting.order`, `accounting.orderitem`, `accounting.shipping`, ghi row count, `min/max` business timestamp và khóa chính. Nếu tên cột khác runtime schema, DB Operator phải inventory trước rồi mới viết query; không đoán cột.

**Expected:** đủ ba table hoặc đúng inventory đã ký; query không lỗi.

**Abort:** schema/table bắt buộc thiếu, object owner/extension không tương thích, hoặc PITR chứa corruption.

### 7.2 [A] Export accounting từ isolated restore

```bash
pg_dump "$RESTORED_RDS_DSN" \
  --schema=accounting \
  --format=custom \
  --no-owner \
  --no-privileges \
  --file="accounting-${RUN_ID}.dump"

pg_restore --list "accounting-${RUN_ID}.dump" > "accounting-${RUN_ID}.manifest.txt"
sha256sum "accounting-${RUN_ID}.dump" "accounting-${RUN_ID}.manifest.txt"
```

Lưu dump ở encrypted temporary storage, không commit database dump vào Git. Evidence chỉ giữ manifest, checksum, size, UTC timestamp và storage URI đã redacted.

**Expected:** exit code `0`; manifest chỉ chứa schema `accounting`; checksum được ghi.

**Abort:** dump có schema khác, chứa secret, thiếu table/sequence/constraint, storage không mã hóa, hoặc `pg_dump` version không tương thích.

### 7.3 [A] Restore vào validation database cô lập

Không import vào shared source. Tạo database/schema validation trên recovery RDS hoặc một target cô lập đã phê duyệt:

```bash
createdb "$VALIDATION_ADMIN_DSN" "otel_accounting_${RUN_ID_SAFE}"
pg_restore \
  --dbname="$VALIDATION_DSN" \
  --no-owner \
  --no-privileges \
  --exit-on-error \
  "accounting-${RUN_ID}.dump"
```

**Expected:** restore exit code `0`; schema, tables, indexes, constraints và sequences tồn tại.

**Abort:** target là production/shared source; object collision không được giải thích; constraint/index restore fail.

### 7.4 [A/M] Integrity gate

Chạy và lưu:

- row count từng table giữa PITR restore và validation DB;
- PK uniqueness: `count(*) = count(distinct <pk>)`;
- orphan check cho mọi FK (`orderitem`/`shipping` phải tham chiếu order hợp lệ);
- `NOT NULL`, FK, unique/index validity từ PostgreSQL catalog;
- sequence `last_value >= max(id)` cho cột dùng sequence;
- aggregate business: số order, tổng item quantity/value và trạng thái shipping theo contract;
- sample theo order ID trước/sát PITR timestamp;
- checksum ổn định theo PK cho table đủ nhỏ; table lớn dùng chunked aggregate có ghi giới hạn.

**Expected:** mọi comparison bằng nhau, không orphan/duplicate, sequence không lùi; Application Owner ký PASS.

**Abort:** bất kỳ mismatch không giải thích được. Không cutover; giữ isolated restore để điều tra trong cost window.

## 8. Incident thật: write freeze, cutover và rollback

> Toàn bộ mục này là `[M] + [A]`, không chạy trong drill. IC phải phê duyệt từng gate.

### 8.1 Freeze

1. IC thông báo maintenance/write freeze và ghi `T_freeze`.
2. Application Owner dừng/scale về 0 các writer vào `accounting` và pause accounting consumer group bằng phương thức đã kiểm thử.
3. DB Operator thu hồi `INSERT/UPDATE/DELETE` của application role hoặc đặt role/database read-only theo change plan.
4. Xác minh không còn active write transaction bằng `pg_stat_activity` và metric/log.
5. Ghi Kafka offsets/cutoff time; không xóa consumer group.

**Expected:** không có accounting write mới sau `T_freeze`; reads theo quyết định IC.

**Abort:** writer chưa kiểm soát, transaction dài chưa kết thúc, consumer vẫn commit, hoặc freeze gây impact ngoài approved scope.

### 8.2 Prepare target

Khuyến nghị an toàn là import `accounting` vào database đích mới/cô lập rồi chuyển ứng dụng có kiểm soát. Không drop schema trên shared source khi chưa có snapshot/export hiện trạng và explicit approval.

1. Tạo forensic export của schema accounting hiện tại.
2. Import PITR accounting dump vào target.
3. Chạy toàn bộ integrity gate.
4. Replay archive theo mục 9 đến `T_freeze`.
5. Chạy validation sau replay; reset sequence bằng giá trị `max(id)` theo từng sequence mapping đã inventory.
6. Deploy canary/green accounting instance trỏ target, chưa nhận production traffic.

**Abort:** target dùng nhầm source endpoint; replay chưa đủ range; validation fail; sequence mapping chưa rõ.

### 8.3 Cutover

Chỉ khi IC + Tech Lead ghi `GO`:

1. Chuyển approved Secret/DNS/service selector của accounting sang target bằng GitOps/change record.
2. Restart/canary một replica; kiểm tra TLS, DB identity và read-only smoke test.
3. Cho phép ghi có kiểm soát; tạo một synthetic/correlation order đã được phê duyệt.
4. Xác minh đúng một accounting record, không duplicate, consumer offset tiến và error rate bình thường.
5. Ghi `T_service_restored`; tính actual RTO từ `T0`.

**Expected:** service healthy, test record đúng một lần, validation PASS.

**Abort:** connection error, write vào source cũ, duplicate/missing, constraint error, consumer lag/error tăng. Freeze lại và rollback.

### 8.4 Rollback

1. IC tuyên bố rollback; freeze writers lần nữa.
2. Dừng consumer/canary trỏ recovery target.
3. Xác định mọi write phát sinh sau cutover. Không bỏ các write này.
4. Đồng bộ ngược các write hợp lệ bằng phương án đã phê duyệt (DMS/controlled export-import/idempotent event replay).
5. Chỉ khi reconciliation PASS mới trả endpoint về target trước cutover.
6. Resume một replica, smoke test, rồi resume toàn bộ.

**Abort:** chưa đồng bộ được post-cutover writes hoặc có xung đột. Giữ freeze, escalate Tech Lead/PM; không rollback mù gây RPO lớn hơn.

## 9. MSK archive replay từ S3

### 9.1 [A/M] Lập immutable replay manifest

Khoảng replay mặc định là `(PITR_UTC, T_freeze]`; điều chỉnh theo event-time semantics đã ký. Inventory S3 object/version, ETag/checksum, size, partition, first/last event time, Kafka key và schema version:

```powershell
aws s3api list-object-versions --bucket $env:ARCHIVE_BUCKET --prefix $env:ARCHIVE_PREFIX `
  --output json | Set-Content "$env:EVIDENCE_DIR/07-archive-inventory.txt"
```

Copy manifest sang evidence; không sửa/xóa archive. Streaming Operator xác nhận không có gap giữa archive objects và cutoff.

**Expected:** coverage liên tục, checksum/schema hợp lệ, không object `PENDING/FAILED`.

**Abort:** thiếu object/partition, event timestamp không đáng tin, format không có decoder, KMS deny, hoặc archive mới nhất không đạt RPO.

### 9.2 [A] Replay vào topic/consumer cô lập trước

Không replay thẳng vào production topic. Tạo topic tạm có retention ngắn, tên gắn `RUN_ID`; giữ nguyên event key và thêm header:

- `x-replay-run-id`;
- source bucket/key/version;
- original topic/partition/offset nếu archive có;
- original event timestamp;
- SHA-256 payload.

Replay tool phải:

- đọc đúng manifest, không dùng wildcard mở;
- validate schema trước publish;
- giữ thứ tự theo partition/key; không hứa global ordering;
- dùng deterministic idempotency key (ưu tiên business order ID + event type/version);
- ghi accepted/rejected/skipped-duplicate count;
- không log PII/secret.

Lệnh phụ thuộc connector/archive format thực tế:

```text
<approved-replay-tool> \
  --manifest <immutable-manifest> \
  --from-exclusive <PITR_UTC> \
  --to-inclusive <T_freeze-or-drill-cutoff> \
  --target-topic <isolated-replay-topic> \
  --run-id <RUN_ID> \
  --dry-run

<same-command-without-dry-run-after-approval>
```

**Expected:** dry-run count khớp manifest; publish count = accepted + rejected/skipped có giải thích; DLQ/reject count bằng 0 hoặc được adjudicate.

**Abort:** tool/format chưa được phê duyệt, ordering không bảo toàn theo key, không có idempotency, count mismatch, schema error hoặc publish nhầm production.

### 9.3 [A/M] Apply vào recovered accounting target

Cho recovery consumer riêng đọc isolated replay topic, dùng consumer group mới gắn `RUN_ID`. Không tái sử dụng production group. Consumer phải ghi vào recovered target và enforce idempotency.

Validation:

- mọi expected order ID có đúng một accounting order;
- không thiếu partition/range;
- duplicate business key = 0;
- child rows không orphan;
- event accepted/rejected/duplicate totals reconcile với manifest;
- consumer lag về 0 tại cutoff;
- DB max business timestamp đạt `T_freeze` trong giới hạn target RPO;
- sequence/integrity/aggregate gate mục 7.4 vẫn PASS.

**Expected:** reconciliation PASS; Streaming Operator, DB Operator và Application Owner ký.

**Abort:** missing/duplicate không giải thích được, lag không về 0, DB constraint fail hoặc event sau cutoff bị áp dụng.

Trong incident thật, chỉ sau gate này mới được cutover. Trong drill, dừng tại đây.

## 10. Đo RPO/RTO và verdict

Ghi các mốc UTC:

| Mốc | Ý nghĩa |
|---|---|
| `T0` | IC bắt đầu recovery clock |
| `T_pitr` | restore point đã chọn |
| `T_last_verified_record` | event/record mới nhất được phục hồi và xác minh |
| `T_freeze`/drill cutoff | điểm dữ liệu cần phục hồi tới |
| `T_service_restored` | service/canary usable và validation PASS |

Tính:

- **Actual RPO trước replay:** `corruption/cutoff time - T_last_verified_record_on_PITR`.
- **Actual RPO sau replay:** `cutoff - latest continuously verified recovered event`.
- **Actual RTO:** `T_service_restored - T0`; drill dùng thời điểm validation hoàn tất thay service cutover và phải ghi rõ.

Không lấy thời điểm RDS status `available` làm RTO cuối nếu export, replay hoặc validation chưa xong. So actual với target ADR ở hai cột riêng. Không sửa target. Bất kỳ target nào không đạt là `FAIL` và phải có remediation owner.

## 11. Cleanup và cost controls

### 11.1 [M] Cleanup approval

Chỉ cleanup khi:

- evidence, manifest, checksums và verdict đã lưu;
- IC/Tech Lead xác nhận không cần giữ tài nguyên để điều tra;
- incident đã ổn định hoặc drill đã kết thúc;
- post-cutover writes đã được bảo toàn.

### 11.2 [A] Dọn tài nguyên tạm

1. Xóa isolated replay topic/consumer group theo approved Kafka admin command.
2. Xóa validation database/dump tạm sau retention ngắn; evidence checksum/manifest vẫn giữ.
3. Xóa recovery secret/SG rule/runner tạm.
4. Xóa RDS restore:

```powershell
aws rds delete-db-instance `
  --db-instance-identifier $env:RDS_RESTORE_ID `
  --skip-final-snapshot `
  --delete-automated-backups
aws rds wait db-instance-deleted --db-instance-identifier $env:RDS_RESTORE_ID
```

`--skip-final-snapshot` chỉ dùng cho instance PITR tạm sau approval; không bao giờ áp dụng cho source.

5. Query theo tag `RunId=$env:RUN_ID` và xác nhận không còn RDS, snapshots, ENI/SG, runner, topic hoặc temporary objects ngoài evidence retention.

**Expected:** AWS trả deleted/not found cho đúng restore ID; source vẫn `available`; production topic/archive không đổi.

**Abort:** identifier không khớp chính xác `RDS_RESTORE_ID`, resource là source, evidence chưa chốt, hoặc Security/IC yêu cầu legal hold.

### 11.3 [A] Cleanup evidence

Ghi vào `11-cleanup.txt`: UTC, identity, resource IDs trước/sau, delete request ID, final status và xác nhận source/archive còn nguyên. Ghi chi phí ước tính theo thời lượng RDS tạm và storage; không để tài nguyên quá `AutoCleanupAfter`.

## 12. Checklist ký kết phiên chạy

| Gate | PASS/FAIL | Evidence | Owner |
|---|---|---|---|
| Đúng account/region/resource context |  | `00-context.txt` | Evidence Recorder |
| PITR window, retention, encryption |  | `02-rds-pitr-source.json` | DB Operator |
| Restore cô lập, private, encrypted |  | `03-restore-events.json` | DB Operator |
| Accounting export/restore đầy đủ |  | `05-*`, `06-*` | DB Operator |
| Integrity/sequence/FK/aggregate |  | `06-*`, `09-*` | App + DB |
| S3 archive coverage và checksum |  | `07-archive-inventory.txt` | Streaming |
| Replay missing/duplicate/lag |  | `08-*`, `09-*` | Streaming + App |
| Actual RPO/RTO so với target |  | `10-timeline.md`, `12-verdict.md` | Tech Lead |
| Cleanup và cost control |  | `11-cleanup.txt` | Recovery Lead |

Final verdict phải ghi `PASS`, `CONDITIONAL PASS` hoặc `FAIL`; liệt kê root cause/remediation cho mọi FAIL. Hải (PM) ký business verdict và Nguyên (Tech Lead) ký technical result bằng tên, UTC timestamp và evidence-pack version.

## 13. Các abort condition tuyệt đối

Dừng ngay, không “best effort” cutover khi:

- có khả năng command chạm RDS source hoặc production topic ngoài approved change;
- restore không cô lập/private/encrypted;
- PITR không chứng minh được là trước corruption;
- archive/replay coverage không đầy đủ;
- missing, duplicate, orphan, checksum hoặc sequence validation fail;
- active writer/consumer chưa freeze;
- không bảo toàn được writes phát sinh trong cutover/rollback;
- operator phải vô hiệu hóa deletion protection, encryption, retention hoặc IAM separation để tiếp tục;
- RPO/RTO fail nhưng không có owner/remediation.

## 14. Repository-backed assumptions và gap phải xác minh

- `infra/terraform/rds.tf` định nghĩa RDS source `techx-tf4-postgresql`, database `otel`, encrypted storage, private access, Multi-AZ và automated backup retention 7 ngày.
- `infra/terraform/msk.tf` định nghĩa MSK `techx-tf4-orders`, TLS/SASL-SCRAM và encrypted broker storage.
- Shared PostgreSQL chứa ít nhất `accounting.order`, `accounting.orderitem`, `accounting.shipping` theo evidence Week 2; runtime schema vẫn phải inventory.
- Tại thời điểm viết runbook, repo chưa có Terraform/IaC xác nhận MSK Connect S3 sink, bucket order archive hoặc replay tool. Đây là prerequisite của replay, không phải evidence PASS. Nếu runtime không có, tạo remediation P0/P1 theo target và ghi FAIL trung thực.

## 15. Tham chiếu

- Mandate 20: yêu cầu PITR trước sự cố, restore tách biệt, drill thật, RPO/RTO và backup safety.
- `infra/terraform/rds.tf`
- `infra/terraform/msk.tf`
- `docs/cdo08/week2/mandate3/evidence/postgresql_persistence_evidence.md`
- `docs/cdo08/week2/CDO08-managed-data-services-migration-plan.md`

