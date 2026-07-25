# CDO08-REL-25 - Hướng dẫn chạy internal dry run

**Subtask:** Automate shared-RDS PITR and accounting schema recovery workflow
**Owner:** CDO08 Reliability
**Shell sử dụng:** Git Bash
**Cập nhật:** 2026-07-24

## Mục tiêu

Chạy một lần RDS PITR thật vào môi trường cô lập, khôi phục riêng schema
`accounting`, lưu log RTO và xác nhận production instance không bị thay đổi.

Runbook này có thao tác tạo RDS và phát sinh chi phí. Chỉ chạy phần live sau khi
preflight trả exit code `0` và leader đã phê duyệt TTL/cleanup.

## Trạng thái thực thi hiện tại

Cập nhật sau phiên thực thi ngày 2026-07-24:

| Thời điểm UTC | Thao tác | Kết quả |
| --- | --- | --- |
| `09:27:18` | Kiểm tra hai SG theo tên drill | Chưa tồn tại |
| `09:27:18-09:27:37` | Tạo và tag validation-client SG, restore-target SG | PASS |
| `09:27:18-09:27:37` | Mở TCP/5432 từ validation-client SG tới restore-target SG | PASS |
| `09:27:37` | Verify CIDR/IPv6/prefix list ingress | Không có |
| `09:27:37` | So sánh với SG production | Không trùng |
| `09:27:37` | Kiểm tra attachment | Chưa gắn ENI/RDS |
| `09:33:50` | Tạo validation pod non-root | API accepted, pod Pending |
| Sau `09:33:50` | Scheduler kiểm tra pod ENI | Blocked: insufficient pod ENI |
| Trước `09:40:05` | Kiểm tra VPC CNI | `ENABLE_POD_ENI=false` |
| `09:40:05-09:40:17` | Cleanup pod, policy, secret và hai SG | PASS |

Hai SG thật đã được tạo theo tên:

```text
rel25-20260724-validation-client
rel25-20260724-restore-target
```

SG ID thật không ghi vào Git. Hai SG đã được xóa sau attempt.

Internal dry run bị chặn trước PITR vì cluster đang có
`ENABLE_POD_ENI=false`. Validation pod không thể schedule khi
`SecurityGroupPolicy` yêu cầu `vpc.amazonaws.com/pod-eni`.

Bước tiếp theo cần Platform phê duyệt bật Security Groups for Pods hoặc cung
cấp access path cô lập tương đương. Không tự rollout `aws-node` trong
production cluster. Chưa tạo RDS PITR và không còn tài nguyên REL-25 từ attempt.

## Quy tắc an toàn

- Không thay placeholder bằng production endpoint hoặc production SG.
- Không dùng `0.0.0.0/0`, `::/0` hoặc CIDR làm ingress cho restore RDS.
- Không ghi password/token vào file, command history, log hoặc Git.
- Không chạy lệnh live nếu target identifier không có `drill`, `accounting` và
  `restore`.
- Không chạy cleanup nếu identifier không khớp chính xác target đã tạo.
- Mỗi checkpoint phải PASS trước khi sang bước tiếp theo.

## 1. Mở Git Bash tại repository

```bash
cd /d/XBrain_phase3/tf4-phase3-repo

git branch --show-current
git status --short
```

Script phải tồn tại:

```bash
test -f docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh \
  && echo "PASS: script exists"
```

## 2. Khai báo biến read-only

Không commit các giá trị thật dưới đây:

```bash
export AWS_PROFILE=tf4-cdo08-admin
export AWS_REGION=us-east-1
export SOURCE_DB_IDENTIFIER=techx-tf4-postgresql
export DB_SUBNET_GROUP_NAME=techx-tf4-postgresql-private
export NAMESPACE=techx-tf4
```

Lấy AWS identity và Kubernetes context để đối chiếu với giá trị leader/Platform
đã duyệt:

```bash
aws sts get-caller-identity \
  --profile "$AWS_PROFILE" \
  --query '[Account,Arn]' \
  --output table

kubectl config current-context
```

Sau khi đối chiếu thủ công, nhập hai guardrail values qua terminal:

```bash
read -r -p "Expected AWS account ID: " EXPECTED_AWS_ACCOUNT_ID
export EXPECTED_AWS_ACCOUNT_ID

read -r -p "Expected Kubernetes context: " EXPECTED_KUBE_CONTEXT
export EXPECTED_KUBE_CONTEXT
```

Không lấy tự động expected value từ current identity/context; làm vậy sẽ khiến
guardrail không phát hiện operator đang đứng nhầm account hoặc cluster.

## 3. Kiểm tra cú pháp và secret

```bash
bash -n \
  docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh

git diff --check
```

Kết quả mong đợi: cả hai lệnh trả exit code `0`.

Quét các mẫu secret phổ biến:

```bash
if rg -n \
  'AKIA[0-9A-Z]{16}|aws_secret_access_key|aws_session_token|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY' \
  docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh
then
  echo "STOP: review possible secret before continuing" >&2
  exit 1
else
  echo "PASS: no common secret pattern found"
fi
```

## 4. Chọn restore timestamp

Đọc PITR window:

```bash
aws rds describe-db-instance-automated-backups \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --query 'DBInstanceAutomatedBackups[0].RestoreWindow.[EarliestTime,LatestTime]' \
  --output table
```

Chọn timestamp UTC trước sự cố và nằm trong window, sau đó nhập:

```bash
read -r -p "Restore timestamp UTC (YYYY-MM-DDTHH:MM:SSZ): " RESTORE_TIMESTAMP
export RESTORE_TIMESTAMP
```

Không dùng timestamp ví dụ nguyên xi.

## 5. Khai báo drill ID và target identifier

```bash
export RESTORE_DRILL_ID="rel25-$(date -u +%Y%m%d)"
export RESTORE_TARGET_IDENTIFIER="techx-tf4-drill-${RESTORE_DRILL_ID}-accounting-restore"

printf 'RESTORE_DRILL_ID=%s\n' "$RESTORE_DRILL_ID"
printf 'RESTORE_TARGET_IDENTIFIER=%s\n' "$RESTORE_TARGET_IDENTIFIER"
```

Guardrail local:

```bash
case "$RESTORE_TARGET_IDENTIFIER" in
  *drill*accounting*restore*) echo "PASS: target naming" ;;
  *) echo "STOP: unsafe target identifier" >&2; exit 1 ;;
esac

test "$RESTORE_TARGET_IDENTIFIER" != "$SOURCE_DB_IDENTIFIER" || {
  echo "STOP: target equals production source" >&2
  exit 1
}
```

## 6. Kiểm tra hoặc tạo hai security group

Lấy VPC:

```bash
export VPC_ID="$(
  aws rds describe-db-instances \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
    --query 'DBInstances[0].DBSubnetGroup.VpcId' \
    --output text
)"

test -n "$VPC_ID" && test "$VPC_ID" != "None" || {
  echo "STOP: cannot resolve VPC_ID" >&2
  exit 1
}

echo "PASS: VPC resolved"
```

Kiểm tra SG được Platform tạo sẵn:

```bash
aws ec2 describe-security-groups \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --filters \
    "Name=vpc-id,Values=$VPC_ID" \
    "Name=tag:Environment,Values=RestoreDrill" \
    "Name=tag:RestoreDrillId,Values=$RESTORE_DRILL_ID" \
  --query 'SecurityGroups[].{ID:GroupId,Purpose:Tags[?Key==`Purpose`]|[0].Value}' \
  --output table
```

Nếu SG đã có, nhập ID được duyệt:

```bash
read -r -p "Validation-client SG ID: " VALIDATION_CLIENT_SECURITY_GROUP_ID
export VALIDATION_CLIENT_SECURITY_GROUP_ID

read -r -p "Restore-target SG ID: " RESTORE_SECURITY_GROUP_ID
export RESTORE_SECURITY_GROUP_ID
```

Nếu Platform giao CDO08 tự tạo SG, chạy từng lệnh dưới đây. Đây là bước tạo tài
nguyên AWS thật:

```bash
export VALIDATION_CLIENT_SECURITY_GROUP_ID="$(
  aws ec2 create-security-group \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --group-name "${RESTORE_DRILL_ID}-validation-client" \
    --description "REL-25 validation client" \
    --vpc-id "$VPC_ID" \
    --query GroupId \
    --output text
)"

export RESTORE_SECURITY_GROUP_ID="$(
  aws ec2 create-security-group \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --group-name "${RESTORE_DRILL_ID}-restore-target" \
    --description "REL-25 restore target" \
    --vpc-id "$VPC_ID" \
    --query GroupId \
    --output text
)"
```

Tag validation-client SG:

```bash
aws ec2 create-tags \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --resources "$VALIDATION_CLIENT_SECURITY_GROUP_ID" \
  --tags \
    Key=Owner,Value=CDO08 \
    Key=Environment,Value=RestoreDrill \
    Key=Mandate,Value=20 \
    Key=Task,Value=CDO08-REL-25 \
    Key=RestoreDrillId,Value="$RESTORE_DRILL_ID" \
    Key=Purpose,Value=RestoreValidationClient \
    Key=TTLHours,Value=24 \
    Key=Production,Value=false
```

Tag restore-target SG:

```bash
aws ec2 create-tags \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --resources "$RESTORE_SECURITY_GROUP_ID" \
  --tags \
    Key=Owner,Value=CDO08 \
    Key=Environment,Value=RestoreDrill \
    Key=Mandate,Value=20 \
    Key=Task,Value=CDO08-REL-25 \
    Key=RestoreDrillId,Value="$RESTORE_DRILL_ID" \
    Key=Purpose,Value=RestoreTarget \
    Key=TTLHours,Value=24 \
    Key=Production,Value=false
```

Chỉ mở PostgreSQL từ validation-client SG:

```bash
aws ec2 authorize-security-group-ingress \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --group-id "$RESTORE_SECURITY_GROUP_ID" \
  --ip-permissions \
    "IpProtocol=tcp,FromPort=5432,ToPort=5432,UserIdGroupPairs=[{GroupId=$VALIDATION_CLIENT_SECURITY_GROUP_ID,Description=REL25-validation-only}]"
```

Kiểm tra rule:

```bash
aws ec2 describe-security-groups \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --group-ids \
    "$VALIDATION_CLIENT_SECURITY_GROUP_ID" \
    "$RESTORE_SECURITY_GROUP_ID" \
  --output json
```

STOP nếu restore SG có CIDR, IPv6, prefix list hoặc source SG khác
validation-client SG.

## 7. Validation pod và temporary credential

Script yêu cầu đúng một pod:

```bash
kubectl -n "$NAMESPACE" get pods \
  -l restore-validation-client=true \
  -o wide
```

Pod phải:

- có `pg_isready`, `pg_dump`, `pg_restore`, `psql`;
- có pod ENI gắn `VALIDATION_CLIENT_SECURITY_GROUP_ID`;
- nhận PostgreSQL credential qua temporary Secret hoặc secret manager;
- không dùng production application role;
- không ghi credential vào manifest trong Git.

Runbook không tự tạo credential vì loại xác thực và secret manager phải do
Platform/Database owner phê duyệt. Không tiếp tục nếu chưa có pod và temporary
credential.

Kiểm tra tool trong pod:

```bash
export VALIDATION_POD="$(
  kubectl -n "$NAMESPACE" get pods \
    -l restore-validation-client=true \
    --field-selector=status.phase=Running \
    -o jsonpath='{.items[0].metadata.name}'
)"

test -n "$VALIDATION_POD" || {
  echo "STOP: no running validation pod" >&2
  exit 1
}

kubectl -n "$NAMESPACE" exec "pod/$VALIDATION_POD" -- \
  sh -c 'command -v pg_isready && command -v pg_dump && command -v pg_restore && command -v psql'
```

## 8. Accounting drill target

Nhập endpoint private do Platform/Database owner cấp:

```bash
read -r -p "Accounting drill endpoint: " ACCOUNTING_TARGET_HOST
export ACCOUNTING_TARGET_HOST
```

Guardrail local:

```bash
case "$ACCOUNTING_TARGET_HOST" in
  *prod*|*production*)
    echo "STOP: accounting target looks like production" >&2
    exit 1
    ;;
esac
```

Target phải cho phép drop/create schema `accounting`, không chứa `catalog` hoặc
`reviews`, và chỉ validation-client SG truy cập được.

## 9. Chạy preflight-only

Preflight gọi API read-only và kiểm tra kết nối, không tạo RDS:

```bash
export PREFLIGHT_ONLY=true
export NETWORK_WAIT_TIMEOUT_SECONDS=60

set -o pipefail
bash docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh \
  2>&1 | tee "rel25-preflight-${RESTORE_DRILL_ID}.log"

PREFLIGHT_EXIT=${PIPESTATUS[0]}
echo "preflight_exit_code=$PREFLIGHT_EXIT"
test "$PREFLIGHT_EXIT" -eq 0
```

PASS khi log có:

```text
preflight_only_passed no_rds_instance_created
```

Không chạy live nếu preflight exit code khác `0`.

## 10. Chụp trạng thái production trước dry run

```bash
aws rds describe-db-instances \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --query 'DBInstances[0].[DBInstanceIdentifier,DBInstanceStatus,PubliclyAccessible,VpcSecurityGroups[*].VpcSecurityGroupId]' \
  --output json \
  > "rel25-production-before-${RESTORE_DRILL_ID}.json"
```

File evidence này chỉ chứa metadata, không chứa password.

## 11. Chạy internal dry run thật

Bước này tạo RDS và phát sinh chi phí. Chỉ chạy sau phê duyệt:

```bash
export PREFLIGHT_ONLY=false
export CONFIRM_PITR_RESTORE=YES
export CONFIRM_ACCOUNTING_IMPORT=YES
export TTL_HOURS=24

set -o pipefail
bash docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh \
  2>&1 | tee "rel25-pitr-${RESTORE_DRILL_ID}.log"

DRY_RUN_EXIT=${PIPESTATUS[0]}
echo "dry_run_exit_code=$DRY_RUN_EXIT"
```

Không cleanup ngay nếu exit code khác `0`; trước tiên lưu log và xác định RDS
target có được tạo hay không.

## 12. Kiểm tra Acceptance Criteria

```bash
grep -E \
  'restore_request|target_status=available|apply_network_access|phase_start|phase_end|rto_end|accounting_schema_recovery_completed' \
  "rel25-pitr-${RESTORE_DRILL_ID}.log"
```

Internal dry run PASS khi:

- `DRY_RUN_EXIT=0`;
- có restore request;
- target đạt `available`;
- network access được apply và verify;
- accounting validation pass;
- có `rto_end rto_seconds=...`;
- có `production_source_was_not_modified`.

## 13. So sánh production trước và sau

```bash
aws rds describe-db-instances \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --query 'DBInstances[0].[DBInstanceIdentifier,DBInstanceStatus,PubliclyAccessible,VpcSecurityGroups[*].VpcSecurityGroupId]' \
  --output json \
  > "rel25-production-after-${RESTORE_DRILL_ID}.json"

diff -u \
  "rel25-production-before-${RESTORE_DRILL_ID}.json" \
  "rel25-production-after-${RESTORE_DRILL_ID}.json"
```

PASS khi `diff` không có output. Đây là evidence production instance metadata
không bị workflow thay đổi.

## 14. Cleanup sau khi lưu evidence

Xác nhận target trước khi xóa:

```bash
printf 'Cleanup target: %s\n' "$RESTORE_TARGET_IDENTIFIER"

case "$RESTORE_TARGET_IDENTIFIER" in
  *drill*accounting*restore*) ;;
  *) echo "STOP: refusing unsafe cleanup target" >&2; exit 1 ;;
esac

test "$RESTORE_TARGET_IDENTIFIER" != "$SOURCE_DB_IDENTIFIER" || {
  echo "STOP: refusing production cleanup" >&2
  exit 1
}
```

Sau khi reviewer/leader xác nhận evidence đã đủ, xóa RDS drill:

```bash
aws rds delete-db-instance \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" \
  --skip-final-snapshot \
  --delete-automated-backups
```

Chờ RDS biến mất:

```bash
aws rds wait db-instance-deleted \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER"
```

Xóa validation pod/temporary secret theo owner đã được phê duyệt. Chỉ xóa hai SG
sau khi không còn ENI/RDS tham chiếu:

```bash
aws ec2 delete-security-group \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --group-id "$RESTORE_SECURITY_GROUP_ID"

aws ec2 delete-security-group \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --group-id "$VALIDATION_CLIENT_SECURITY_GROUP_ID"
```

Không chạy các lệnh cleanup SG nếu SG do Platform quản lý hoặc được giữ lại cho
drill tiếp theo.

## 15. File evidence cần giữ

```text
rel25-preflight-<drill-id>.log
rel25-pitr-<drill-id>.log
rel25-production-before-<drill-id>.json
rel25-production-after-<drill-id>.json
```

Trước khi commit evidence, kiểm tra không có endpoint, account ID, ARN, SG ID,
pod IP hoặc credential cần được redacted theo policy nội bộ.
