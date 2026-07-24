# CDO08-REL-25 - Automate RDS Accounting Point-in-Time Restore

**Mandate:** [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md)
**Subtask:** Automate RDS accounting point-in-time restore
**Owner:** CDO08 Reliability
**Updated:** 2026-07-24

## Mục tiêu

Khôi phục dữ liệu `accounting` về timestamp trước sự cố từ shared RDS bằng
workflow tự động: PITR toàn instance sang RDS staging cô lập, export riêng
schema `accounting`, rồi restore vào database drill/target được kiểm soát.
Production `techx-tf4-postgresql` chỉ được dùng làm source PITR, không bị sửa.

Theo inventory hiện tại, `accounting`, `catalog` và `reviews` vẫn nằm chung
instance. RDS PITR hoạt động ở cấp instance nên staging RDS tạm thời chứa cả ba
schema, nhưng workflow chỉ dump/restore `accounting`. Target accounting cuối
cùng không được chứa `catalog` hoặc `reviews`. Sau GAP-06/REL-32, operator phải
đặt `SOURCE_DB_IDENTIFIER` thành instance riêng của `accounting` và review lại
PITR window trước khi chạy.

## Căn cứ từ Mandate 20

- Inventory xác nhận RDS PostgreSQL có automated backup, PITR và retention 7
  ngày.
- RPO/RTO draft của `accounting` là 15 phút/1 giờ; đây chưa phải cam kết đã ký.
- ADR yêu cầu restore thành instance mới trong môi trường tách biệt.
- GAP-03 yêu cầu chạy restore thật, đo RTO và nộp evidence.
- Guardrail hiện có yêu cầu target khác production, private và dùng
  restore-only security group.

## Script

```text
docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh
```

Script thực hiện:

1. Nhận `RESTORE_TIMESTAMP` ISO-8601 làm input.
2. Kiểm tra timestamp nằm trong PITR restore window của AWS.
3. Từ chối target trùng production hoặc không có naming drill.
4. Từ chối dùng lại production security group.
5. Xác minh restore SG có đúng drill tags, không có CIDR/public ingress, và chỉ
   mở TCP/5432 từ validation-client SG.
6. Xác minh validation-client pod có đúng SG, kết nối và authenticate
   read-only được vào accounting drill target trước khi tạo RDS PITR.
7. Gọi `restore-db-instance-to-point-in-time` để tạo staging instance private.
8. Chờ target `available`.
9. Áp lại restore-only security group và chờ `available`.
10. Xác minh target không public, đúng subnet/SG và xuất metadata.
11. Từ validation-client pod, chạy `pg_isready` tới endpoint restore trên cổng
    5432 và chờ đến khi network probe thành công.
12. Export riêng schema `accounting` từ staging RDS bằng `pg_dump
    --schema=accounting`.
13. Drop/create schema `accounting` trên accounting drill target rồi import
    bằng `pg_restore`.
14. Validate integrity: đếm order, chặn orphan `shipping`/`orderitem`, và fail
    nếu target có schema `catalog` hoặc `reviews`.
15. Cleanup dump tạm trên validation pod.
16. Log UTC start/end/duration của từng phase cùng tổng `rto_seconds`; RTO chỉ
    kết thúc sau export + import + validation.

Script không đọc hoặc chứa database password. Credential PostgreSQL phải được
cấp qua temporary secret hoặc `.pgpass` trong validation-client pod.

## Input bắt buộc

| Biến | Ý nghĩa |
| --- | --- |
| `AWS_PROFILE` | Profile SSO của operator. |
| `EXPECTED_AWS_ACCOUNT_ID` | AWS account ID kỳ vọng, cấp qua environment hoặc secret CI; không lưu trong Git. |
| `EXPECTED_KUBE_CONTEXT` | Kubernetes context kỳ vọng, cấp qua environment hoặc secret CI; không lưu trong Git. |
| `RESTORE_DRILL_ID` | ID drill, ví dụ `rel25-20260723`. |
| `RESTORE_TIMESTAMP` | Timestamp UTC trước sự cố và nằm trong PITR window. |
| `RESTORE_TARGET_IDENTIFIER` | Instance mới theo naming contract. |
| `RESTORE_SECURITY_GROUP_ID` | Restore-only SG gắn cho RDS target. |
| `VALIDATION_CLIENT_SECURITY_GROUP_ID` | SG chỉ gắn cho validation client và là nguồn ingress TCP/5432 duy nhất. |
| `ACCOUNTING_TARGET_HOST` | Endpoint database drill/target để import riêng schema `accounting`. Không được là production endpoint hoặc staging PITR endpoint. |
| `CONFIRM_PITR_RESTORE=YES` | Chỉ bắt buộc khi restore thật; xác nhận trước khi tạo tài nguyên có chi phí. |
| `CONFIRM_ACCOUNTING_IMPORT=YES` | Xác nhận drop/create schema `accounting` trên drill target trước khi import. |

`SOURCE_DB_IDENTIFIER` mặc định là `techx-tf4-postgresql`.
`EXPECTED_AWS_ACCOUNT_ID` và `EXPECTED_KUBE_CONTEXT` không có giá trị mặc định;
script dừng nếu chưa cấp hoặc nếu profile/context hiện tại không khớp. Không
commit hai giá trị này vào repository; cấp chúng qua environment cục bộ hoặc
secret variables của CI.
`DB_SUBNET_GROUP_NAME` mặc định là `techx-tf4-postgresql-private`.
`DB_INSTANCE_CLASS` mặc định lấy từ production source. Drill mặc định
`MultiAZ=false`, private, TTL 24 giờ để giảm chi phí.
`SOURCE_DB_NAME`, `SOURCE_DB_USER`, `ACCOUNTING_TARGET_DB`,
`ACCOUNTING_TARGET_USER` và `PGSSLMODE` có default lần lượt là `otel`, `otelu`,
`otel`, `otelu`, `require`.

Validation-client pod mặc định được tìm trong namespace `techx-tf4` bằng label
`restore-validation-client=true`. Pod phải ở trạng thái Running, image phải có
`pg_isready`, `pg_dump`, `pg_restore` và `psql`, và ENI của pod phải thực sự gắn
`VALIDATION_CLIENT_SECURITY_GROUP_ID`.

Operator cần các quyền AWS tối thiểu:

- `sts:GetCallerIdentity`
- `rds:DescribeDBInstances`
- `rds:DescribeDBInstanceAutomatedBackups`
- `rds:DescribeDBSubnetGroups`
- `ec2:DescribeSecurityGroups`
- `ec2:DescribeNetworkInterfaces`
- `rds:RestoreDBInstanceToPointInTime` và `rds:ModifyDBInstance` chỉ khi chạy
  restore thật

Kubernetes context phải trỏ đúng cluster TF4; operator cần quyền `get pods` và
`create pods/exec` trong namespace validation. Script không đọc Kubernetes
Secret.

`PREFLIGHT_ONLY=true` chạy toàn bộ kiểm tra read-only rồi dừng trước lệnh tạo
RDS. Chế độ này không yêu cầu `CONFIRM_PITR_RESTORE=YES`.

## Kiểm tra trước khi chạy thật

Đăng nhập và kiểm tra PITR window:

```bash
export AWS_PROFILE=your-sso-profile
aws sso login --profile "$AWS_PROFILE"

aws rds describe-db-instance-automated-backups \
  --profile "$AWS_PROFILE" \
  --region us-east-1 \
  --db-instance-identifier techx-tf4-postgresql \
  --query 'DBInstanceAutomatedBackups[0].RestoreWindow'
```

Liệt kê subnet group, production SG và restore-only SG:

```bash
aws rds describe-db-instances \
  --profile "$AWS_PROFILE" \
  --region us-east-1 \
  --db-instance-identifier techx-tf4-postgresql \
  --query 'DBInstances[0].{Subnet:DBSubnetGroup.DBSubnetGroupName,ProductionSG:VpcSecurityGroups[*].VpcSecurityGroupId}'

aws ec2 describe-security-groups \
  --profile "$AWS_PROFILE" \
  --region us-east-1 \
  --filters Name=tag:Environment,Values=RestoreDrill \
  --query 'SecurityGroups[].{Id:GroupId,Name:GroupName,VpcId:VpcId}'
```

Không dùng SG được trả về ở cột `ProductionSG` làm
`RESTORE_SECURITY_GROUP_ID`. Restore SG phải có:

```text
Environment=RestoreDrill
Production=false
RestoreDrillId=<RESTORE_DRILL_ID>
Purpose=RestoreTarget
```

Ingress của restore SG chỉ được chứa TCP/5432 từ
`VALIDATION_CLIENT_SECURITY_GROUP_ID`; không được có CIDR, IPv6, prefix list
hoặc source SG khác.

Validation-client SG phải nằm cùng VPC và có:

```text
Environment=RestoreDrill
Production=false
RestoreDrillId=<RESTORE_DRILL_ID>
Purpose=RestoreValidationClient
```

Kiểm tra tags và ingress của hai SG trước khi xác nhận restore:

```bash
aws ec2 describe-security-groups \
  --profile "$AWS_PROFILE" \
  --region us-east-1 \
  --group-ids "$RESTORE_SECURITY_GROUP_ID" "$VALIDATION_CLIENT_SECURITY_GROUP_ID" \
  --query 'SecurityGroups[].{Id:GroupId,Name:GroupName,Tags:Tags,Ingress:IpPermissions}'
```

Kiểm tra script:

```bash
bash -n ./docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh

docker run --rm -v "$PWD:/repo:ro" koalaman/shellcheck:stable \
  /repo/docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh
```

## Chạy preflight-only, không tạo RDS

Sau khi đã có restore-only SG và validation-client SG, chạy:

```bash
export AWS_PROFILE=your-sso-profile
export EXPECTED_AWS_ACCOUNT_ID=provided-securely-by-platform
export EXPECTED_KUBE_CONTEXT=provided-securely-by-platform
export RESTORE_DRILL_ID=rel25-20260723
export RESTORE_TIMESTAMP=2026-07-23T08:45:00Z
export RESTORE_TARGET_IDENTIFIER=techx-tf4-drill-rel25-20260723-accounting-restore
export DB_SUBNET_GROUP_NAME=techx-tf4-postgresql-private
export RESTORE_SECURITY_GROUP_ID=sg-restore-only
export VALIDATION_CLIENT_SECURITY_GROUP_ID=sg-validation-client
export ACCOUNTING_TARGET_HOST=accounting-drill-target.internal
export PREFLIGHT_ONLY=true

bash ./docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh
```

Pass khi exit code bằng `0` và dòng cuối là:

```text
phase=complete message=preflight_only_passed no_rds_instance_created
```

Chế độ này chỉ gọi `sts get-caller-identity`, `rds describe-*` và
`ec2 describe-*`, cùng các lệnh `kubectl get/exec` read-only để xác minh
validation client. Nó không gọi
`restore-db-instance-to-point-in-time` hoặc `modify-db-instance`.

## Chạy internal dry run

Chỉ chạy sau khi restore-only SG đã tồn tại và được review:

```bash
export AWS_PROFILE=your-sso-profile
export EXPECTED_AWS_ACCOUNT_ID=provided-securely-by-platform
export EXPECTED_KUBE_CONTEXT=provided-securely-by-platform
export RESTORE_DRILL_ID=rel25-20260723
export RESTORE_TIMESTAMP=2026-07-23T08:45:00Z
export RESTORE_TARGET_IDENTIFIER=techx-tf4-drill-rel25-20260723-accounting-restore
export DB_SUBNET_GROUP_NAME=techx-tf4-postgresql-private
export RESTORE_SECURITY_GROUP_ID=sg-restore-only
export VALIDATION_CLIENT_SECURITY_GROUP_ID=sg-validation-client
export ACCOUNTING_TARGET_HOST=accounting-drill-target.internal
export CONFIRM_PITR_RESTORE=YES
export CONFIRM_ACCOUNTING_IMPORT=YES

set -o pipefail
bash ./docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh \
  2>&1 | tee "rel25-pitr-${RESTORE_DRILL_ID}.log"
```

Thay timestamp, account/context guardrail, endpoint drill và hai SG bằng giá
trị đã được duyệt. Account ID, context, endpoint và credential phải được cấp
qua kênh nội bộ/CI secret; không commit các giá trị thật. Không copy ví dụ
nguyên xi để chạy.

Log thành công phải có:

```text
phase=environment_preflight message=phase_start
phase=accounting_target_preflight message=accounting_drill_target_authentication_passed
phase=restore_preflight message=phase_start
phase=restore_request message=phase_start
phase=wait_initial_available message=phase_end duration_seconds=...
phase=apply_network_access message=phase_end duration_seconds=...
phase=validate_network_access message=network_probe_passed ...
phase=export_accounting_schema message=phase_end duration_seconds=...
phase=import_accounting_schema message=phase_end duration_seconds=...
phase=validate_accounting_integrity message=order_count=... shipping_orphans=0 item_orphans=0 unexpected_schemas=0
phase=complete message=rto_end rto_seconds=...
```

## Acceptance Criteria

| Tiêu chí | Trạng thái/Evidence |
| --- | --- |
| PITR toàn instance sang isolated RDS | Script tạo staging RDS private, có naming/SG guardrail; live dry run vẫn cần restore-only SG/quyền. |
| Không thay production endpoint | Script fail nếu RDS target trùng source identifier hoặc accounting target host trùng production endpoint. |
| Không restore catalog/reviews vào target accounting | Script chỉ dùng `pg_dump --schema=accounting`; validation fail nếu target có schema `catalog` hoặc `reviews`. |
| Workflow có error handling và cleanup | `set -euo pipefail`, trap log lỗi, cleanup dump tạm trên validation pod; RDS cleanup vẫn chạy theo cleanup checklist sau evidence để tránh tự xóa nhầm. |
| Tổng RTO tính đủ PITR + export + import + validation | `rto_seconds` bắt đầu trước `restore_request` và kết thúc sau `validate_accounting_integrity` + cleanup dump. |
| Restore thành công trong internal dry run | Chưa chạy: live scan chưa có restore-only SG; không dùng production SG để đóng giả tiêu chí. |
| Script không chứa secret thật | Đạt: script không có password/token/secret value. |
| Có log start/end để tính RTO | Đạt: log UTC từng phase và tổng `rto_seconds`. |
| Không đụng production instance | Đạt theo thiết kế: production chỉ được gọi bằng API `describe`; restore/modify chỉ dùng target identifier mới. |
| Network access hoạt động thật | Script chạy `pg_isready` từ validation-client pod tới endpoint restore và fail nếu quá timeout. |

## Verification đã thực hiện

Ngày 2026-07-23:

- Đã đọc toàn bộ file trong `docs/cdo08/week3/mandate20` trước khi triển khai.
- `bash -n` pass.
- ShellCheck pass.
- AWS CLI skeleton xác nhận có các input
  `DBSubnetGroupName`, `VpcSecurityGroupIds`, `PubliclyAccessible`, `MultiAZ`,
  `CopyTagsToSnapshot` và `Tags`.
- Scan source không thấy access key, session token, private key hoặc password
  hard-code.
- Negative check thiếu input trả exit code khác `0`.
- Negative check timestamp sai định dạng trả exit code khác `0`.
- Live read-only discovery xác nhận source đang `available`, private,
  `db.t4g.micro`, subnet group `techx-tf4-postgresql-private`, và automated
  backup có PITR window.
- Live read-only discovery chưa tìm thấy SG có tag
  `Environment=RestoreDrill`; vì vậy chưa chạy lệnh tạo RDS.

### Internal dry-run attempt

Ngày 2026-07-23, operator đã xác nhận:

- EKS có `SecurityGroupPolicy` API.
- VPC CNI có `ENABLE_POD_ENI=true`.
- Chưa có validation pod, restore-drill SG hoặc RDS drill target trùng tên.

Dry run dừng an toàn ở bước tạo validation-client SG. AWS trả
`UnauthorizedOperation` vì profile `tf4-cdo08-admin` đang assume role
`AWSReservedSSO_TF4-SecurityIAMSSOManager_7fec96c816beda10` và role này không
có `ec2:CreateSecurityGroup`. Không có SG, pod hoặc RDS nào được tạo.

Không dùng production SG để vượt qua blocker. Để tiếp tục, operator cần role
được duyệt có tối thiểu quyền tạo/tag/authorize/revoke/delete security group,
quyền PITR RDS, và quyền tạo/xóa `SecurityGroupPolicy` cùng validation pod.

Request dùng để leader/Platform cấp prerequisite:

```text
docs/cdo08/week3/mandate20/review-requests/CDO08-REL-25-REQUEST-INTERNAL-DRY-RUN-PREREQUISITES.md
```

## Cleanup sau dry run

Sau khi validation và lưu evidence, xóa target theo runbook cleanup đã được
review. Trước khi xóa, xác nhận identifier có `drill`, `accounting` và
`restore`; không chạy lệnh cleanup với production identifier.
