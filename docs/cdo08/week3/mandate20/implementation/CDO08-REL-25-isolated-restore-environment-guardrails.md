# CDO08 REL-25 - Isolated restore environment guardrails

## Mục tiêu

Ngăn workflow PITR:

- restore nhầm vào production identifier;
- dùng production endpoint hoặc security group;
- tạo public RDS/EC2;
- cho workload ngoài validation client kết nối;
- để lại tài nguyên drill phát sinh chi phí.

Guardrail được tích hợp trực tiếp trong entry point:

```text
docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh
```

Không còn preflight Pod/Kubernetes riêng.

## Naming contract

Input:

```text
RESTORE_DRILL_ID=rel25-YYYYMMDD
```

Có thể thêm suffix khi chạy lại:

```text
RESTORE_DRILL_ID=rel25-YYYYMMDD-b
```

RDS target bắt buộc:

```text
RESTORE_TARGET_IDENTIFIER=techx-tf4-drill-${RESTORE_DRILL_ID}-accounting-restore
```

Script fail nếu:

- drill ID sai format;
- target identifier không khớp chính xác naming contract;
- target identifier trùng production source;
- target đã tồn tại.

## AWS account guardrail

Operator phải cung cấp:

```text
AWS_PROFILE
EXPECTED_AWS_ACCOUNT_ID
```

Script gọi `sts:GetCallerIdentity` và fail nếu account hiện tại khác account kỳ
vọng. Account ID không có default trong source code.

## Production source guardrail

Production RDS mặc định:

```text
SOURCE_DB_IDENTIFIER=techx-tf4-postgresql
```

Đối với source, script chỉ gọi:

```text
rds:DescribeDBInstances
rds:DescribeDBInstanceAutomatedBackups
rds:DescribeDBSubnetGroups
```

Production chỉ được dùng làm source của:

```text
rds:RestoreDBInstanceToPointInTime
```

Script không modify, reboot, delete, đổi SG hoặc chạy SQL trên production.

## Restore timestamp guardrail

`RESTORE_TIMESTAMP` được parse thành UTC và phải nằm trong:

```text
EarliestTime <= RESTORE_TIMESTAMP <= LatestTime
```

Window được đọc từ RDS automated backups. Script fail trước khi tạo resource
nếu timestamp không hợp lệ hoặc nằm ngoài retention window.

## Private subnet guardrail

Validation EC2 dùng một subnet lấy từ production DB subnet group.

Trước khi tạo EC2, script kiểm tra:

```text
MapPublicIpOnLaunch=False
```

EC2 được tạo với:

```text
AssociatePublicIpAddress=false
```

Sau khi EC2 chạy, script đọc metadata và fail nếu `PublicIpAddress` khác
`None`.

## Validation EC2 guardrail

EC2 validation:

```text
AMI: latest Amazon Linux 2023
Instance type: t3.nano
Ingress: none
SSH: disabled
Access: AWS Systems Manager only
EBS: encrypted gp3
DeleteOnTermination: true
IMDSv2: required
```

Script kiểm tra EC2 chỉ gắn validation SG và chờ SSM `Online`.

## Security group contract

Script tạo hai SG trong cùng VPC:

```text
Validation SG
Restore SG
```

Network path duy nhất tới restored RDS:

```text
Temporary EC2
  -> Validation SG
  -> TCP/5432
  -> Restore SG
  -> Restored RDS
```

Restore SG chỉ có ingress:

```text
Protocol: TCP
Port: 5432
Source: Validation SG
```

Không dùng:

- CIDR ingress;
- IPv6 ingress;
- prefix list;
- production SG;
- EKS node SG;
- public ingress;
- port ngoài `5432`.

## Restore RDS guardrail

PITR request luôn có:

```text
PubliclyAccessible=false
MultiAZ=false
DBSubnetGroupName=techx-tf4-postgresql-private
VpcSecurityGroupIds=<restore-sg-only>
```

Sau khi target `available`, script apply lại restore SG rồi kiểm tra:

- status là `available`;
- target private;
- đúng DB subnet group;
- chỉ có restore SG;
- endpoint khác production endpoint.

Nếu một điều kiện sai, workflow fail và chạy cleanup.

## Secret guardrail

Script không chứa password.

Validation IAM role chỉ được cấp:

```text
secretsmanager:DescribeSecret
secretsmanager:GetSecretValue
```

Resource là đúng source RDS managed master secret ARN, không phải wildcard toàn
bộ Secrets Manager.

EC2 đọc secret trong runtime. Secret value:

- không trả về SSM output;
- không ghi vào execution log;
- không ghi vào evidence;
- chỉ tồn tại trong environment của remote process.

IAM role và inline policy bị xóa sau drill.

## Accounting-only guardrail

Remote recovery script:

```text
docs/cdo08/week3/mandate20/scripts/postgres/rel25-accounting-recovery-remote.sh
```

Chỉ chạy:

```text
pg_dump --schema=accounting
pg_restore --schema=accounting
```

Target database bắt buộc:

```text
ACCOUNTING_TARGET_DB=accounting_drill
```

Validation fail nếu target có schema:

```text
catalog
reviews
```

## Data integrity guardrail

Remote validation:

- so row count `accounting.order`;
- so row count `accounting.shipping`;
- so row count `accounting.orderitem`;
- fail khi source và target counts khác nhau;
- fail khi có duplicate `order_id`;
- fail khi có shipping orphan;
- fail khi có orderitem orphan;
- ghi nhận sequence count.

## TTL và cost tags

Tài nguyên drill có:

```text
Owner=CDO08
Environment=RestoreDrill
Mandate=20
Task=CDO08-REL-25
RestoreDrillId=<drill-id>
TTLHours=<hours>
CleanupAfter=<UTC timestamp>
CostCenter=ReliabilityDrill
Production=false
```

Default:

```text
TTL_HOURS=6
```

## Cleanup guardrail

Default:

```text
AUTO_CLEANUP=true
```

EXIT trap chạy khi success và failure:

```text
delete RDS PITR target
-> terminate EC2 và DeleteOnTermination EBS
-> revoke SG cross-reference
-> delete restore SG
-> delete validation SG
-> delete IAM instance profile
-> delete inline secret policy
-> detach SSM managed policy
-> delete IAM role
```

Nếu cleanup không hoàn tất, script:

- trả exit code khác `0`;
- ghi `cleanup_remaining_*`;
- ghi resource ID cần xử lý thủ công.

## Preflight modes

Preflight read-only:

```bash
PREFLIGHT_ONLY=true \
bash docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh
```

Preflight không tạo IAM, SG, EC2 hoặc RDS.

Live run cũng chạy cùng preflight ở đầu workflow:

```bash
PREFLIGHT_ONLY=false \
CONFIRM_PITR_RESTORE=YES \
AUTO_CLEANUP=true \
bash docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh
```

## Acceptance Criteria mapping

| Tiêu chí | Guardrail |
| --- | --- |
| Restore target không dùng production identifier/endpoint | Exact naming contract, target absence check và endpoint comparison. |
| Chỉ validation client được kết nối | Restore SG chỉ nhận TCP/5432 từ validation SG gắn trực tiếp vào private EC2. |
| Preflight fail nếu target trùng production | Entry point fail trước resource creation nếu identifier trùng hoặc naming sai. |
| Không dùng production SG | Restore SG được tạo riêng và target phải chỉ gắn SG đó. |
| Không dùng production DNS | Workflow dùng AWS-generated drill endpoint và không tạo DNS record. |
| Temporary secrets | EC2 role chỉ đọc exact managed secret ARN trong thời gian drill. |
| Cost/TTL/cleanup tags | Bắt buộc trên EC2, EBS, SG và RDS target. |
| Cleanup | EXIT trap và independent AWS verification. |

## Verification đã chứng minh

Live dry run `rel25-20260726-b`:

```text
Target private: PASS
Endpoint distinct from production: PASS
Restore SG isolation: PASS
Accounting validation: PASS
RTO: 1572 seconds
Cleanup: PASS
Production unchanged: PASS
```

Post-refactor run `rel25-20260726-refactor` xác nhận guardrail vẫn PASS sau khi
xóa standalone Pod preflight và chuyển checks vào entry point:

```text
Preflight: PASS
Private EC2/RDS: PASS
Exact validation-SG -> restore-SG TCP/5432 path: PASS
Endpoint distinct from production: PASS
Accounting validation: PASS
RTO: 1867 seconds
Cleanup: PASS
Production unchanged: PASS
```

Evidence:

```text
docs/cdo08/week3/mandate20/evidence/CDO08-REL-25-INTERNAL-DRY-RUN-EVIDENCE.md
```
