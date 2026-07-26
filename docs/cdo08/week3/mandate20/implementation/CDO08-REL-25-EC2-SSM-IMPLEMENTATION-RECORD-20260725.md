# CDO08 REL-25 - Quy trình RDS accounting PITR qua EC2/SSM

**Loại tài liệu:** Implementation runbook
**Owner:** CDO08 Reliability
**Cập nhật:** 2026-07-26

## Mục tiêu

Tài liệu này hướng dẫn chạy workflow:

```text
production RDS automated backup
  -> private RDS PITR target
  -> temporary private EC2 qua SSM
  -> export riêng schema accounting
  -> import vào accounting_drill
  -> validation và tính RTO
  -> cleanup toàn bộ tài nguyên drill
```

Script:

```text
docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh
```

## Tài nguyên script tạo tạm

Script tự tạo:

1. IAM role `techx-tf4-rel25-validation`.
2. IAM instance profile cùng tên.
3. Validation security group.
4. Restore security group.
5. EC2 validation client trong private subnet.
6. RDS PITR target.
7. Database `accounting_drill` trong restored RDS.

Mặc định `AUTO_CLEANUP=true`. Khi script kết thúc, các tài nguyên trên bị xóa.
EBS của EC2 có `DeleteOnTermination=true`.

## Luồng network

```text
Operator
  -> AWS Systems Manager
  -> private EC2 validation SG
  -> TCP/5432
  -> restore RDS SG
  -> private RDS PITR target
```

Kiểm soát:

- EC2 không có public IP.
- EC2 không có ingress và không mở SSH.
- Restore SG chỉ nhận TCP/5432 từ validation SG.
- Restore RDS không dùng production SG.
- Không tạo production DNS cho restore target.

## Bước 1 - mở Git Bash

Chạy từ root repository:

```bash
cd /d/XBrain_phase3/tf4-phase3-repo
```

Không chạy các block Bash dưới đây bằng PowerShell vì cú pháp `export` và
`date -u -d` khác nhau.

## Bước 2 - đăng nhập AWS SSO

```bash
export AWS_PROFILE=tf4-cdo08-admin
export AWS_REGION=us-east-1

aws sso login --profile "$AWS_PROFILE"
```

Xác nhận account và role:

```bash
aws sts get-caller-identity \
  --profile "$AWS_PROFILE" \
  --query '[Account,Arn]' \
  --output table
```

Đối chiếu thủ công rồi đặt account guardrail:

```bash
export EXPECTED_AWS_ACCOUNT_ID=511825856493
```

Không tiếp tục nếu account ID hoặc role không đúng môi trường TF4.

## Bước 3 - kiểm tra source production

```bash
export SOURCE_DB_IDENTIFIER=techx-tf4-postgresql

aws rds describe-db-instances \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --query 'DBInstances[0].{
    Identifier:DBInstanceIdentifier,
    Status:DBInstanceStatus,
    Public:PubliclyAccessible,
    Endpoint:Endpoint.Address,
    SubnetGroup:DBSubnetGroup.DBSubnetGroupName,
    SGs:VpcSecurityGroups[*].VpcSecurityGroupId
  }' \
  --output table
```

Kết quả yêu cầu:

```text
Identifier = techx-tf4-postgresql
Status = available
Public = False
SubnetGroup = techx-tf4-postgresql-private
```

Ghi lại endpoint và production SG để so sánh sau drill.

## Bước 4 - chọn restore timestamp

Đọc PITR window:

```bash
aws rds describe-db-instance-automated-backups \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --query 'DBInstanceAutomatedBackups[0].RestoreWindow.[EarliestTime,LatestTime]' \
  --output table
```

Chọn một UTC timestamp nằm giữa `EarliestTime` và `LatestTime`:

```bash
export RESTORE_TIMESTAMP=YYYY-MM-DDTHH:MM:SSZ
```

Không dùng timestamp sau `LatestTime`.

## Bước 5 - đặt drill naming

```bash
export RESTORE_DRILL_ID="rel25-$(date -u +%Y%m%d)"
export RESTORE_TARGET_IDENTIFIER="techx-tf4-drill-${RESTORE_DRILL_ID}-accounting-restore"
```

Nếu cần chạy lại trong cùng ngày, thêm suffix:

```bash
export RESTORE_DRILL_ID="rel25-$(date -u +%Y%m%d)-b"
export RESTORE_TARGET_IDENTIFIER="techx-tf4-drill-${RESTORE_DRILL_ID}-accounting-restore"
```

Kiểm tra input:

```bash
printf '%s\n' \
  "RESTORE_TIMESTAMP=$RESTORE_TIMESTAMP" \
  "RESTORE_DRILL_ID=$RESTORE_DRILL_ID" \
  "RESTORE_TARGET_IDENTIFIER=$RESTORE_TARGET_IDENTIFIER"
```

Target identifier phải khác production identifier và chứa `drill`, `rel25`,
`accounting`, `restore`.

## Bước 6 - kiểm tra script local

Kiểm tra cú pháp:

```bash
bash -n \
  docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh

echo "exit_code=$?"
```

Kết quả yêu cầu:

```text
exit_code=0
```

Quét secret:

```bash
if rg -n \
  'AKIA[0-9A-Z]{16}|aws_secret_access_key|aws_session_token|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY' \
  docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh
then
  echo "STOP: review possible secret" >&2
  exit 1
else
  echo "PASS: no common secret pattern found"
fi
```

## Bước 7 - chạy preflight read-only

```bash
export PREFLIGHT_ONLY=true
export AUTO_CLEANUP=true
export EXECUTION_LOG="/tmp/rel25-${RESTORE_DRILL_ID}-preflight.log"

bash \
  docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh

echo "exit_code=$?"
```

Kết quả đạt:

```text
preflight_passed
preflight_only_passed_no_resources_created
exit_code=0
```

Preflight chỉ:

- kiểm tra AWS account;
- kiểm tra production RDS;
- kiểm tra timestamp trong PITR window;
- kiểm tra private subnet;
- kiểm tra target chưa tồn tại.

Preflight không tạo IAM, SG, EC2 hoặc RDS.

## Bước 8 - chạy live internal dry run

Chỉ chạy khi preflight exit code `0`:

```bash
export PREFLIGHT_ONLY=false
export CONFIRM_PITR_RESTORE=YES
export AUTO_CLEANUP=true
export TTL_HOURS=6
export EXECUTION_LOG="/tmp/rel25-${RESTORE_DRILL_ID}-execution.log"

bash \
  docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh

echo "exit_code=$?"
```

Không đóng terminal trong lúc script đang chạy. PITR có thể mất 20-40 phút.

## Bước 9 - các phase script thực hiện

### 9.1 Environment preflight

Script:

- gọi `sts:GetCallerIdentity`;
- fail nếu account khác `EXPECTED_AWS_ACCOUNT_ID`;
- đọc production RDS metadata;
- fail nếu source không `available` hoặc đang public;
- kiểm tra PITR window;
- fail nếu target đã tồn tại;
- chọn private subnet từ DB subnet group.

### 9.2 Tạo validation identity

Script tạo EC2 trust role và instance profile:

```text
techx-tf4-rel25-validation
```

Role được gắn:

```text
AmazonSSMManagedInstanceCore
```

Inline policy chỉ đọc đúng RDS managed master secret ARN:

```text
secretsmanager:DescribeSecret
secretsmanager:GetSecretValue
```

Secret value chỉ được đọc trong EC2 và không được đưa vào log.

### 9.3 Tạo isolated network

Script tạo:

```text
techx-tf4-<drill-id>-validation
techx-tf4-<drill-id>-restore
```

Rules:

```text
validation SG egress:
  TCP/443 -> AWS SSM và package repository
  TCP/80  -> package bootstrap
  TCP/UDP 53 -> VPC DNS
  TCP/5432 -> restore SG

restore SG ingress:
  TCP/5432 <- validation SG
```

Restore SG không có CIDR/public ingress.

### 9.4 Tạo private EC2

EC2 sử dụng:

```text
AMI: latest Amazon Linux 2023
Instance type: t3.nano
Public IP: false
EBS: encrypted gp3, DeleteOnTermination=true
IMDS: v2 required
Access: SSM only
```

Bootstrap cài:

```text
jq
postgresql17
```

Script chờ SSM `Online`, chờ cloud-init hoàn tất và kiểm tra:

```text
aws
jq
pg_isready
pg_dump
pg_restore
psql
```

### 9.5 PITR RDS

RTO bắt đầu ngay trước:

```text
rds restore-db-instance-to-point-in-time
```

Target:

- dùng identifier drill mới;
- nằm trong private DB subnet group;
- `PubliclyAccessible=false`;
- `MultiAZ=false`;
- chỉ gắn restore SG;
- có TTL, cleanup và cost tags.

Script poll cho tới khi RDS `available`, sau đó apply lại SG và kiểm tra endpoint
khác production.

### 9.6 Accounting recovery

Qua SSM, EC2 thực hiện:

```text
1. Đọc RDS master credential từ Secrets Manager.
2. Chạy pg_isready tới restored RDS.
3. Tạo database accounting_drill.
4. Chạy pg_dump --schema=accounting từ database otel.
5. Tạo schema accounting trong accounting_drill.
6. Chạy pg_restore vào accounting_drill.
7. So row counts nguồn và đích.
8. Kiểm tra duplicate order.
9. Kiểm tra shipping orphan.
10. Kiểm tra orderitem orphan.
11. Fail nếu target có catalog hoặc reviews.
12. Ghi nhận sequence count.
13. Xóa file dump tạm.
```

### 9.7 RTO

RTO kết thúc sau khi accounting validation pass:

```text
rto_start
  -> PITR request
  -> wait available
  -> network verification
  -> dump
  -> import
  -> validation
rto_end
```

EC2/SG preparation có phase duration riêng nhưng không nằm trong recovery RTO.

### 9.8 Cleanup

EXIT trap luôn chạy khi `AUTO_CLEANUP=true`, kể cả khi workflow lỗi:

```text
RDS PITR target
  -> EC2/EBS
  -> revoke SG cross-reference
  -> restore SG
  -> validation SG
  -> instance profile
  -> inline secret policy
  -> SSM policy attachment
  -> IAM role
```

Nếu cleanup lỗi, log ghi `cleanup_remaining_*` và resource ID.

## Bước 10 - đọc kết quả

```bash
rg -n \
  'validation=PASS|rto_end|accounting_recovery_completed|cleanup_complete|cleanup_remaining|level=ERROR' \
  "$EXECUTION_LOG"
```

Run thành công phải có đủ:

```text
validation=PASS
rto_end rto_seconds=<number>
accounting_recovery_completed_production_was_not_modified
cleanup_complete_no_drill_resources_remaining
exit_code=0
```

## Bước 11 - kiểm tra cleanup độc lập

Kiểm tra RDS:

```bash
aws rds describe-db-instances \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER"
```

Kết quả kỳ vọng:

```text
DBInstanceNotFound
```

Kiểm tra active EC2:

```bash
aws ec2 describe-instances \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --filters \
    "Name=tag:RestoreDrillId,Values=$RESTORE_DRILL_ID" \
    "Name=instance-state-name,Values=pending,running,stopping,stopped" \
  --query 'Reservations[].Instances[].InstanceId' \
  --output text
```

Output phải rỗng.

Kiểm tra SG:

```bash
aws ec2 describe-security-groups \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --filters "Name=tag:RestoreDrillId,Values=$RESTORE_DRILL_ID" \
  --query 'SecurityGroups[].GroupId' \
  --output text
```

Output phải rỗng.

Kiểm tra IAM:

```bash
aws iam get-role \
  --profile "$AWS_PROFILE" \
  --role-name techx-tf4-rel25-validation

aws iam get-instance-profile \
  --profile "$AWS_PROFILE" \
  --instance-profile-name techx-tf4-rel25-validation
```

Hai command phải trả `NoSuchEntity`.

## Bước 12 - kiểm tra production sau run

```bash
aws rds describe-db-instances \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --query 'DBInstances[0].{
    Identifier:DBInstanceIdentifier,
    Status:DBInstanceStatus,
    Public:PubliclyAccessible,
    Endpoint:Endpoint.Address,
    SGs:VpcSecurityGroups[*].VpcSecurityGroupId
  }' \
  --output table
```

Production phải:

- vẫn `available`;
- vẫn private;
- identifier không đổi;
- endpoint không đổi;
- security group không đổi.

## Kết quả đã được chứng minh

Live internal dry run `rel25-20260726-b` đã PASS:

```text
Source counts: 205891,205891,377846
Target counts: 205891,205891,377846
Duplicates: 0
Shipping orphans: 0
Orderitem orphans: 0
Unexpected schemas: 0
Sequence count: 0
RTO: 1572 seconds
Exit code: 0
Cleanup: PASS
```

Evidence:

```text
docs/cdo08/week3/mandate20/evidence/CDO08-REL-25-INTERNAL-DRY-RUN-EVIDENCE.md
```
