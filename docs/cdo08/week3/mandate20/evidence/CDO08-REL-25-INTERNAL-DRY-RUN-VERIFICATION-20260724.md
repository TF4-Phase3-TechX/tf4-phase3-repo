# CDO08-REL-25 - Internal Dry-Run Verification Evidence

**Subtask:** Automate shared-RDS PITR and accounting schema recovery workflow
**Owner:** CDO08 Reliability
**Ngày kiểm tra:** 2026-07-24
**Khoảng thời gian kiểm tra:** 08:42-08:55 UTC
**Thời điểm bắt đầu ghi evidence:** 2026-07-24T08:55:55Z
**Branch:** `main`
**Commit được kiểm tra:** `3c1b29d`
**Nguồn commit:** PR `#614`

## Mục đích

Ghi lại các bước kiểm tra script
`scripts/postgres/rel25-restore-accounting-pitr.sh`, kết quả thật thu được và
những điều kiện còn thiếu trước khi thực hiện internal dry run có tạo RDS.

File này không phải bằng chứng restore thành công. Acceptance Criteria
`Restore thành công trong internal dry run` chỉ đạt sau khi live workflow trả
exit code `0` và có log RTO hoàn chỉnh.

## Trạng thái trước khi tạo evidence

Tại `2026-07-24T08:55:55Z`:

- local branch đang là `main`;
- commit hiện tại là `3c1b29d`;
- working tree sạch;
- thư mục `docs/cdo08/week3/mandate20/evidence` chỉ có `.gitkeep`;
- chưa tạo RDS, SG, pod hoặc secret nào trong phiên kiểm tra này.

## Kết quả kiểm tra

| Hạng mục | Kết quả thật | Trạng thái |
| --- | --- | --- |
| Script đã merge vào `main` | Commit `3c1b29d`, PR `#614` | PASS |
| Cú pháp Bash | `bash -n` trả exit code `0` | PASS |
| AWS SSO | `sts:GetCallerIdentity` thành công | PASS |
| Kubernetes context | Truy cập được cluster dự kiến | PASS |
| Source RDS | `available`, private | PASS |
| PITR window | `2026-07-19T14:22:03.013Z` đến `2026-07-24T08:42:37Z` tại thời điểm kiểm tra | PASS |
| Quyền tạo SG | `ec2 create-security-group --dry-run` trả `DryRunOperation` | PASS |
| RestoreDrill SG | Đã tạo/verify, sau đó xóa lúc `2026-07-24T09:40:17Z` | CLEANED |
| Validation pod | Không có pod với label `restore-validation-client=true` | BLOCKED |
| Accounting drill RDS target | Không tìm thấy RDS target ngoài source production | BLOCKED |
| Temporary drill credential | Chưa được cấp; không đọc hoặc dùng application/production secret hiện có | BLOCKED |
| Live RDS PITR | Chưa chạy vì prerequisite chưa đủ | NOT RUN |

`DryRunOperation` của EC2 có nghĩa request tạo SG sẽ thành công nếu bỏ cờ
`--dry-run`; lệnh kiểm tra không tạo SG thật.

## Evidence tạo isolated security groups

### Before

Tại `2026-07-24T09:27:18Z`:

- không có SG theo hai tên drill dự kiến;
- production RDS không bị thay đổi;
- chưa có validation pod, accounting drill target hoặc RDS PITR target.

### Thao tác đã thực hiện

Hai SG được tạo trong cùng VPC với source RDS:

```text
rel25-20260724-validation-client
rel25-20260724-restore-target
```

Các AWS API đã gọi:

```text
ec2:DescribeSecurityGroups
ec2:CreateSecurityGroup
ec2:CreateTags
ec2:AuthorizeSecurityGroupIngress
ec2:DescribeNetworkInterfaces
rds:DescribeDBInstances
```

Core commands đã sử dụng, với ID thật được giữ ngoài Git:

```bash
aws ec2 create-security-group \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --group-name "${RESTORE_DRILL_ID}-validation-client" \
  --description "REL-25 validation client" \
  --vpc-id "$VPC_ID"

aws ec2 create-security-group \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --group-name "${RESTORE_DRILL_ID}-restore-target" \
  --description "REL-25 isolated RDS restore target" \
  --vpc-id "$VPC_ID"

aws ec2 create-tags \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --resources "<VALIDATION_SG_ID>" \
  --tags \
    Key=Owner,Value=CDO08 \
    Key=Environment,Value=RestoreDrill \
    Key=Mandate,Value=20 \
    Key=Task,Value=CDO08-REL-25 \
    Key=RestoreDrillId,Value=rel25-20260724 \
    Key=Purpose,Value=RestoreValidationClient \
    Key=TTLHours,Value=24 \
    Key=CleanupAfter,Value=2026-07-25T09:27:25Z \
    Key=CostCenter,Value=ReliabilityDrill \
    Key=Production,Value=false

aws ec2 create-tags \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --resources "<RESTORE_SG_ID>" \
  --tags \
    Key=Owner,Value=CDO08 \
    Key=Environment,Value=RestoreDrill \
    Key=Mandate,Value=20 \
    Key=Task,Value=CDO08-REL-25 \
    Key=RestoreDrillId,Value=rel25-20260724 \
    Key=Purpose,Value=RestoreTarget \
    Key=TTLHours,Value=24 \
    Key=CleanupAfter,Value=2026-07-25T09:27:25Z \
    Key=CostCenter,Value=ReliabilityDrill \
    Key=Production,Value=false

aws ec2 authorize-security-group-ingress \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --group-id "<RESTORE_SG_ID>" \
  --protocol tcp \
  --port 5432 \
  --source-group "<VALIDATION_SG_ID>"
```

### After

Tại `2026-07-24T09:27:37Z`:

- validation-client SG có `Purpose=RestoreValidationClient`,
  `Environment=RestoreDrill`, `Production=false` và không có ingress;
- restore-target SG có `Purpose=RestoreTarget`,
  `Environment=RestoreDrill`, `Production=false`;
- restore-target SG chỉ có TCP/5432 từ validation-client SG;
- không có CIDR, IPv6 CIDR hoặc prefix list ingress;
- hai SG không trùng bất kỳ SG nào đang gắn vào production RDS;
- hai SG chưa gắn vào ENI hoặc RDS nào;
- `CleanupAfter=2026-07-25T09:27:25Z`.

Không tạo RDS, pod, secret hoặc DNS record trong bước này.

## Internal dry-run attempt

### Validation environment

Sau khi SG pass, workflow thử tạo:

```text
Secret/rel25-db-auth-20260724
SecurityGroupPolicy/rel25-validation-client-sg
Pod/rel25-validation-client
```

Temporary Secret copy credential cần thiết ở dạng Kubernetes Secret data và tạo
password riêng cho accounting target cục bộ. Secret value không được in ra
terminal, log hoặc evidence.

Lần tạo pod đầu tiên bị admission policy từ chối vì thiếu
`runAsNonRoot=true`. Manifest được sửa để dùng:

```text
runAsNonRoot=true
runAsUser=999
runAsGroup=999
seccompProfile=RuntimeDefault
allowPrivilegeEscalation=false
capabilities.drop=[ALL]
```

Pod sau đó được API chấp nhận lúc `2026-07-24T09:33:50Z`, nhưng không schedule
được. Scheduler báo:

```text
Insufficient vpc.amazonaws.com/pod-eni
```

### Root cause

Read-only inspection xác nhận:

```text
aws-node ENABLE_POD_ENI=false
```

Các node không advertise `vpc.amazonaws.com/pod-eni`, trong khi
`SecurityGroupPolicy` làm validation pod request một pod ENI. Vì vậy không thể
gắn validation-client SG riêng cho pod và không thể thỏa access path cô lập.

Bật `ENABLE_POD_ENI=true` sẽ rollout VPC CNI `aws-node` trên toàn cluster và có
thể thay đổi network behavior của production workloads. Thao tác này không được
thực hiện trong dry-run attempt khi chưa có Platform approval.

Không dùng node SG hoặc production application SG để bỏ qua blocker vì cách đó
không chứng minh chỉ validation client được kết nối.

### Cleanup

Cleanup chạy từ `2026-07-24T09:40:05Z` đến
`2026-07-24T09:40:17Z`.

Các lệnh đã chạy:

```bash
kubectl -n techx-tf4 delete \
  pod/rel25-validation-client \
  --ignore-not-found --wait=true

kubectl -n techx-tf4 delete \
  securitygrouppolicy.vpcresources.k8s.aws/rel25-validation-client-sg \
  --ignore-not-found --wait=true

kubectl -n techx-tf4 delete \
  secret/rel25-db-auth-20260724 \
  --ignore-not-found --wait=true

aws ec2 delete-security-group \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --group-id "<RESTORE_SG_ID>"

aws ec2 delete-security-group \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --group-id "<VALIDATION_SG_ID>"
```

Tất cả delete command trả exit code `0`. Read-only verification sau cleanup:

- không còn pod, temporary Secret hoặc SecurityGroupPolicy REL-25;
- không còn hai SG theo tên drill;
- RDS target trả `DBInstanceNotFound`;
- production RDS không bị thay đổi;
- không còn tài nguyên REL-25 phát sinh phí từ attempt này.

## Các lệnh đã sử dụng

Các lệnh dưới đây được chạy trong khoảng `08:42-08:55 UTC`. Hệ thống không ghi
timestamp bắt đầu riêng cho từng command, vì vậy không suy đoán timestamp chi
tiết hơn.

### Kiểm tra Git và cú pháp

```bash
git branch --show-current
git status --short
git log -1 --oneline

bash -n \
  docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh
```

### Kiểm tra AWS identity

```bash
aws sts get-caller-identity \
  --profile tf4-cdo08-admin \
  --query '[Account,Arn]' \
  --output text
```

Account ID và ARN thật không được chép vào evidence này.

### Kiểm tra PITR restore window

```bash
aws rds describe-db-instance-automated-backups \
  --profile tf4-cdo08-admin \
  --region us-east-1 \
  --db-instance-identifier techx-tf4-postgresql \
  --query 'DBInstanceAutomatedBackups[0].RestoreWindow.[EarliestTime,LatestTime]' \
  --output text
```

### Kiểm tra RestoreDrill security group

```bash
aws ec2 describe-security-groups \
  --profile tf4-cdo08-admin \
  --region us-east-1 \
  --filters Name=tag:Environment,Values=RestoreDrill \
  --query 'SecurityGroups[].{ID:GroupId,Purpose:Tags[?Key==`Purpose`]|[0].Value,Drill:Tags[?Key==`RestoreDrillId`]|[0].Value,Production:Tags[?Key==`Production`]|[0].Value,Vpc:VpcId}' \
  --output table
```

Kết quả không có row.

### Kiểm tra validation client

```bash
kubectl config current-context

kubectl -n techx-tf4 get pods \
  -l restore-validation-client=true \
  -o wide
```

Kết quả: `No resources found in techx-tf4 namespace.`

### Kiểm tra quyền tạo security group, không tạo thật

```bash
VPC_ID="$(
  aws rds describe-db-instances \
    --profile tf4-cdo08-admin \
    --region us-east-1 \
    --db-instance-identifier techx-tf4-postgresql \
    --query 'DBInstances[0].DBSubnetGroup.VpcId' \
    --output text
)"

test -n "$VPC_ID" && test "$VPC_ID" != "None" || {
  echo "ERROR: Khong lay duoc VPC_ID" >&2
  exit 1
}

echo "VPC_ID da duoc resolve"

aws ec2 create-security-group \
  --profile tf4-cdo08-admin \
  --region us-east-1 \
  --group-name rel25-permission-check-not-created \
  --description 'REL-25 permission dry-run' \
  --vpc-id "$VPC_ID" \
  --dry-run
```

Kết quả: `DryRunOperation`. Không có SG được tạo.

### Kiểm tra accounting drill target

```bash
aws rds describe-db-instances \
  --profile tf4-cdo08-admin \
  --region us-east-1 \
  --query 'DBInstances[?DBInstanceIdentifier!=`techx-tf4-postgresql`].[DBInstanceIdentifier,DBInstanceStatus,PubliclyAccessible,Endpoint.Address]' \
  --output table
```

Kết quả không có RDS instance ngoài source production.

### Kiểm tra tên Secret, không đọc giá trị

```bash
kubectl -n techx-tf4 get secrets \
  -o custom-columns=NAME:.metadata.name \
  --no-headers
```

Chỉ metadata name được đọc. Không có lệnh `kubectl get secret -o yaml/json`,
không decode và không ghi secret value vào terminal hoặc evidence.

## Các lệnh không chạy

Trong phiên kiểm tra này không chạy:

```text
aws rds restore-db-instance-to-point-in-time
aws rds modify-db-instance
aws rds delete-db-instance
aws ec2 create-security-group (không có --dry-run)
aws ec2 authorize-security-group-ingress
kubectl create secret
kubectl apply
```

Do đó không có production instance hoặc cloud resource nào bị thay đổi.

## Đối chiếu Acceptance Criteria

| Acceptance Criteria | Evidence hiện tại | Trạng thái |
| --- | --- | --- |
| Nhận restore timestamp làm input | Script nhận và validate `RESTORE_TIMESTAMP` | Đạt về code |
| Chạy `restore-db-instance-to-point-in-time` | Lệnh có trong script | Đạt về code |
| Chờ instance available và apply network access | Có `wait_for_rds` và `modify-db-instance` trên restore target | Đạt về code |
| Xuất timestamps từng phase | Có `phase_start`, `phase_end`, duration và `rto_seconds` | Đạt về code |
| Script không chứa secret thật | Không có secret value trong script/evidence | Đạt |
| Không đụng production instance | Restore/modify dùng target identifier mới; phiên kiểm tra chỉ read-only/dry-run | Đạt về guardrail |
| Restore thành công trong internal dry run | Validation pod bị chặn vì `ENABLE_POD_ENI=false`; PITR chưa được gọi | Chưa đạt |

## Điều kiện để chạy bước tiếp theo

Trước live dry run cần:

1. Platform review và phê duyệt bật `ENABLE_POD_ENI=true`, hoặc cung cấp access
   path cô lập tương đương được script hỗ trợ.
2. Tạo lại hai RestoreDrill SG.
3. Tạo validation pod có pod ENI gắn validation-client SG.
4. Cấp accounting drill target và temporary credential.
5. Chạy `PREFLIGHT_ONLY=true` và lưu log exit code `0`.
6. Được phê duyệt chi phí/TTL rồi mới chạy live PITR.

## Evidence cần bổ sung sau live dry run

Sau khi prerequisite đầy đủ, append vào file evidence mới:

- restore timestamp đã được phê duyệt;
- target identifier drill;
- UTC start/end của từng phase;
- instance chuyển sang `available`;
- network validation pass;
- integrity result;
- tổng `rto_seconds`;
- exit code `0`;
- cleanup timestamp và xác nhận tài nguyên drill đã được xóa.
