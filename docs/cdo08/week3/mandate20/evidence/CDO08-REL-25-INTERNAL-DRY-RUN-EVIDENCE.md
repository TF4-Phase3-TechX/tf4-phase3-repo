# CDO08 REL-25 - Internal dry-run evidence

**Subtask:** Automate shared-RDS PITR and accounting schema recovery workflow
**Owner:** CDO08 Reliability
**Thời gian evidence:** 2026-07-24 đến 2026-07-25
**Trạng thái cuối:** PASS - internal dry run hoàn chỉnh và cleanup thành công

## Mục tiêu

Evidence này tổng hợp toàn bộ kết quả thật của REL-25 vào một file:

```text
production RDS backup
  -> isolated private RDS PITR
  -> accounting export/import
  -> validation
  -> RTO
  -> cleanup
```

Không đánh dấu subtask Done cho tới khi live run có `validation=PASS`,
`rto_end` và `cleanup_complete_no_drill_resources_remaining`.

## Baseline production

Trước live run:

```text
Identifier: techx-tf4-postgresql
Status: available
Public: false
Production SG: sg-0fbc6edd9ae2742d1
```

Production chỉ được dùng làm PITR source và gọi API `describe`. Workflow không
modify production identifier, endpoint hoặc security group.

## Attempt EKS Pod SG ngày 2026-07-24

Thiết kế validation pod bị chặn:

```text
Node types: t3.large, t3a.large
ENABLE_POD_ENI: false
Pod status: Pending
Scheduler: Insufficient vpc.amazonaws.com/pod-eni
```

Không bật Pod ENI hoặc thay đổi production node group. Pod, temporary Secret,
SecurityGroupPolicy và hai SG của attempt này đã được xóa. Không có RDS PITR
được tạo.

Kết quả này dẫn tới quyết định dùng temporary private EC2 qua SSM.

## Static verification ngày 2026-07-25

```text
bash -n: PASS
Secret pattern scan: PASS, không có match
ShellCheck: NOT RUN, local chưa cài
```

Các preflight lỗi môi trường ban đầu:

| Lần | Exit code | Nguyên nhân | Cloud resource |
| --- | ---: | --- | --- |
| 1 | 1 | Git Bash thiếu `jq` | Không tạo |
| 2 | 1 | PowerShell runner không truyền environment vào Bash | Không tạo |
| 3 | 255 | Bash dùng `HOME=/root`, không thấy Windows SSO profile | Không tạo |

Script sau đó loại dependency `jq` ở local; Bash được trỏ tới đúng Windows AWS
SSO home.

## Preflight thành công

```text
Start: 2026-07-25T15:41:15Z
Exit code: 0
Restore timestamp: 2026-07-25T15:20:00Z
Source: techx-tf4-postgresql
Target: techx-tf4-drill-rel25-20260725-accounting-restore
VPC: vpc-0a4e2abe9fbb70451
Private subnet: subnet-0753e69d90fe8f820
Result: preflight_only_passed_no_resources_created
```

## Live attempt 1

```text
Start: 2026-07-25T15:44:23Z
Result: FAIL trước PITR
Reason: EC2 SSM Online trước khi cloud-init/package bootstrap hoàn tất
RDS created: no
```

Tài nguyên:

```text
EC2 i-0e5a93ca744e80133: terminated
Validation SG sg-03319241c0973daba: deleted
Restore SG sg-0c244ee54bbf2974e: deleted
IAM role/profile: deleted
```

Hai SG ban đầu không delete được do rule tham chiếu chéo. Rule TCP/5432 được
revoke rồi hai SG được xóa. Script được sửa để revoke cross-reference trước
delete và chờ bootstrap tối đa 10 phút.

## Live attempt 2

### PITR result

```text
Start: 2026-07-25T16:10:01Z
RTO start: 2026-07-25T16:12:20Z
Restore request: 2026-07-25T16:12:20Z
Target: techx-tf4-drill-rel25-20260725-b-accounting-restore
RDS available: 2026-07-25T16:45:58Z
PITR wait duration: 2012 seconds
Target public: false
Validation EC2 public IP: none
```

PITR sang isolated RDS mới đã thành công và target đạt `available`.

### Accounting recovery result

Workflow dừng trước import:

```text
2026-07-25T16:46:07Z
Restored RDS has no managed master secret
```

PITR target giữ database credential nhưng không trả
`MasterUserSecret.SecretArn` riêng. Vì vậy attempt này chưa có:

- accounting dump/import pass;
- row-count reconciliation;
- orphan/duplicate validation pass;
- `rto_end`.

Script được sửa để EC2 validation role đọc đúng source RDS managed master
secret ARN. Secret value chỉ được đọc bên trong EC2, không xuất ra operator log.
Fix này chưa có live evidence pass.

### Cleanup result

```text
RDS target: deleted at 2026-07-25T16:50:00Z
EC2 i-01e2daf4be33de2c0: terminated at 2026-07-25T16:50:54Z
Restore SG sg-0701480b0c0a31fb0: deleted at 2026-07-25T16:51:02Z
Validation SG sg-05e376326434db67c: deleted at 2026-07-25T16:51:05Z
IAM instance profile: deleted at 2026-07-25T16:51:12Z
IAM role: deleted at 2026-07-25T16:51:19Z
Result: cleanup_complete_no_drill_resources_remaining
```

Không có attempt live mới sau cleanup trên.

## Live attempt 3

```text
Start: 2026-07-26T00:17:42Z
Restore timestamp: 2026-07-26T00:05:00Z
RTO start: 2026-07-26T00:20:03Z
RDS available: 2026-07-26T00:42:40Z
PITR wait duration: 1353 seconds
Target private: PASS
Endpoint distinct from production: PASS
Inherited master credential: PASS
Database accounting_drill created: PASS
Accounting import: FAIL
```

Lỗi thật:

```text
pg_restore: ERROR: schema "accounting" does not exist
```

`pg_restore --schema=accounting` không tạo schema đích trong run này. Script đã
được sửa để chạy `CREATE SCHEMA accounting` trước import. Fix chưa có live
evidence pass.

Cleanup:

```text
RDS target: deleted at 2026-07-26T00:44:47Z
EC2 i-01914aa97c40102df: terminated at 2026-07-26T00:46:11Z
Restore SG sg-0ddee7363c5c0b0c3: deleted at 2026-07-26T00:46:19Z
Validation SG sg-05a82c7a6d9cc2693: deleted at 2026-07-26T00:46:21Z
IAM instance profile: deleted at 2026-07-26T00:46:27Z
IAM role: deleted at 2026-07-26T00:46:34Z
Result: cleanup_complete_no_drill_resources_remaining
```

## Live attempt 4 - thành công

### Input và isolation

```text
Start: 2026-07-26T00:48:54Z
Restore timestamp: 2026-07-26T00:05:00Z
Drill ID: rel25-20260726-b
Target: techx-tf4-drill-rel25-20260726-b-accounting-restore
Validation EC2: i-0a3d04af4568afc9c
Validation SG: sg-0a147a82119fccdec
Restore SG: sg-0e3208b106a9e5278
Validation EC2 public IP: none
Restore RDS public: false
Restore endpoint distinct from production: PASS
```

Restore SG chỉ nhận TCP/5432 từ validation SG. EC2 không có ingress, public IP
hoặc SSH access; command được chạy qua SSM.

### Phase timestamps và RTO

```text
Environment preflight: 23 seconds
IAM identity creation: 24 seconds
Isolated network creation: 22 seconds
Validation EC2 creation/bootstrap: 59 seconds
RTO start: 2026-07-26T00:51:02Z
Restore request duration: 4 seconds
RDS wait available: 1529 seconds
Network verification: 9 seconds
Accounting recovery/validation: 30 seconds
RTO end: 2026-07-26T01:17:14Z
Total RTO: 1572 seconds
```

`1572` giây tương đương `26 phút 12 giây`. RTO bắt đầu trước PITR request và
kết thúc sau accounting import cùng validation.

### Accounting reconciliation

```text
validation=PASS
source order rows=205891
source shipping rows=205891
source orderitem rows=377846
target order rows=205891
target shipping rows=205891
target orderitem rows=377846
duplicates=0
shipping_orphans=0
item_orphans=0
unexpected_schemas=0
sequence_count=0
```

Database `accounting_drill` chỉ nhận schema `accounting`. Schema hiện tại không
có sequence nên `sequence_count=0` là kết quả kỳ vọng.

### Cleanup

```text
RDS target deleted: 2026-07-26T01:21:05Z
EC2 terminated: 2026-07-26T01:21:42Z
Restore SG deleted: 2026-07-26T01:21:50Z
Validation SG deleted: 2026-07-26T01:21:52Z
IAM instance profile deleted: 2026-07-26T01:21:58Z
IAM role deleted: 2026-07-26T01:22:04Z
Result: cleanup_complete_no_drill_resources_remaining
Exit code: 0
```

Kiểm tra AWS độc lập sau run:

```text
Drill RDS: DBInstanceNotFound
Active drill EC2: none
Drill security groups: none
Validation IAM role: NoSuchEntity
Validation instance profile: NoSuchEntity
```

Production sau run:

```text
Identifier: techx-tf4-postgresql
Status: available
Public: false
Endpoint: không đổi
Security group: sg-0fbc6edd9ae2742d1
```

## Post-refactor modular verification

Sau khi tách script thành entry point, common library và remote recovery module,
workflow được chạy live lại để evidence vẫn chứng minh đúng code hiện tại.

Files:

```text
scripts/postgres/rel25-restore-accounting-pitr.sh
scripts/postgres/lib/rel25-common.sh
scripts/postgres/rel25-accounting-recovery-remote.sh
```

Input:

```text
Drill ID: rel25-20260726-refactor
Restore timestamp: 2026-07-26T07:25:00Z
Target: techx-tf4-drill-rel25-20260726-refactor-accounting-restore
```

Phase result:

```text
Preflight start: 2026-07-26T07:38:55Z
RTO start: 2026-07-26T07:41:03Z
RDS available: 2026-07-26T08:11:32Z
PITR wait: 1825 seconds
Accounting validation complete: 2026-07-26T08:12:10Z
RTO: 1867 seconds
Exit code: 0
```

Remote module result:

```text
validation=PASS
source_counts=205891,205891,377846
target_counts=205891,205891,377846
duplicates=0
shipping_orphans=0
item_orphans=0
unexpected_schemas=0
sequence_count=0
```

Cleanup:

```text
RDS deleted: 2026-07-26T08:16:02Z
EC2 i-06171c36e94f3b34a terminated: 2026-07-26T08:16:54Z
Restore SG sg-0f370586298cf7738 deleted: 2026-07-26T08:17:02Z
Validation SG sg-0a65fc0529d8c170e deleted: 2026-07-26T08:17:04Z
IAM instance profile deleted: 2026-07-26T08:17:10Z
IAM role deleted: 2026-07-26T08:17:16Z
Result: cleanup_complete_no_drill_resources_remaining
```

Independent AWS verification:

```text
Drill RDS: DBInstanceNotFound
Active drill EC2: none
Drill SG: none
Validation IAM role: NoSuchEntity
Validation instance profile: NoSuchEntity
Production RDS: available, private, endpoint và SG không đổi
```

## Các command chính đã chạy

```bash
aws sso login --profile tf4-cdo08-admin

aws rds describe-db-instance-automated-backups \
  --profile tf4-cdo08-admin \
  --region us-east-1 \
  --db-instance-identifier techx-tf4-postgresql

bash -n \
  docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh

PREFLIGHT_ONLY=true \
bash docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh

PREFLIGHT_ONLY=false \
CONFIRM_PITR_RESTORE=YES \
AUTO_CLEANUP=true \
bash docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh
```

Script live gọi các API chính:

```text
iam create-role/create-instance-profile/attach-role-policy
ec2 create-security-group/authorize-security-group-*
ec2 run-instances
ssm send-command/get-command-invocation
rds restore-db-instance-to-point-in-time
rds modify-db-instance
rds delete-db-instance
ec2 terminate-instances/delete-security-group
iam delete-instance-profile/delete-role
```

## Acceptance Criteria

| Tiêu chí | Trạng thái | Evidence |
| --- | --- | --- |
| Nhận restore timestamp | PASS | Timestamp được parse và kiểm tra trong PITR window. |
| PITR sang RDS instance mới | PASS | Target attempt 2 đạt `available`. |
| Chờ available và apply network | PASS | Wait 2012 giây; target private và dùng restore SG. |
| Timestamp từng phase | PASS | Có start/end/duration trong live log. |
| Script không chứa secret thật | PASS | Secret scan không có match; runtime secret không in ra log. |
| Không đụng production | PASS | Identifier/endpoint/SG production không bị modify. |
| Accounting export/import/validation | PASS | Attempt 4 row counts khớp; duplicate/orphan/unexpected schema đều `0`. |
| Tổng RTO | PASS | Modular run `rto_seconds=1867`, kết thúc sau validation. |
| Cleanup | PASS | RDS, EC2, SG và IAM tạm đã xóa. |
| Internal dry run hoàn chỉnh | PASS | Attempt 4 exit code `0`, validation và cleanup pass. |

## Kết luận

Internal dry run đã có đủ:

```text
validation=PASS
rto_end rto_seconds=1867
accounting_recovery_completed_production_was_not_modified
cleanup_complete_no_drill_resources_remaining
```

Subtask đáp ứng Acceptance Criteria của workflow RDS PITR accounting.
