# CDO08-REL-25 - Automate RDS Accounting Point-in-Time Restore

**Mandate:** [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md)
**Subtask:** Automate RDS accounting point-in-time restore
**Owner:** CDO08 Reliability
**Updated:** 2026-07-23

## Mục tiêu

Khôi phục dữ liệu `accounting` về timestamp trước sự cố bằng RDS PITR, tạo
instance mới trong môi trường drill và không sửa instance production
`techx-tf4-postgresql`.

Theo inventory hiện tại, `accounting`, `catalog` và `reviews` vẫn nằm chung
instance. RDS PITR hoạt động ở cấp instance nên target tạm thời chứa cả ba
schema; bước validation chỉ tập trung vào `accounting`. Sau GAP-06/REL-32,
script có thể dùng source instance riêng của `accounting`.

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
5. Gọi `restore-db-instance-to-point-in-time` để tạo instance private mới.
6. Chờ target `available`.
7. Áp lại restore-only security group và chờ `available`.
8. Xác minh target không public và xuất metadata.
9. Log UTC start/end/duration của từng phase cùng tổng `rto_seconds`.

Script không đọc hoặc chứa database password. Master credential của target do
RDS restore quản lý; validation credential được xử lý bằng temporary secret ở
subtask guardrail.

## Input bắt buộc

| Biến | Ý nghĩa |
| --- | --- |
| `AWS_PROFILE` | Profile SSO của operator. |
| `RESTORE_DRILL_ID` | ID drill, ví dụ `rel25-20260723`. |
| `RESTORE_TIMESTAMP` | Timestamp UTC trước sự cố và nằm trong PITR window. |
| `RESTORE_TARGET_IDENTIFIER` | Instance mới theo naming contract. |
| `RESTORE_SECURITY_GROUP_IDS` | Một hoặc nhiều restore-only SG, cách nhau bằng khoảng trắng. |
| `CONFIRM_PITR_RESTORE=YES` | Xác nhận rõ trước khi tạo tài nguyên có chi phí. |

`DB_SUBNET_GROUP_NAME` mặc định là `techx-tf4-postgresql-private`.
`DB_INSTANCE_CLASS` mặc định lấy từ production source. Drill mặc định
`MultiAZ=false`, private, TTL 24 giờ để giảm chi phí.

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

Không dùng production SG `sg-0fbc6edd9ae2742d1` làm
`RESTORE_SECURITY_GROUP_IDS`.

Kiểm tra script:

```bash
bash -n ./docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh

docker run --rm -v "$PWD:/repo:ro" koalaman/shellcheck:stable \
  /repo/docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh
```

## Chạy internal dry run

Chỉ chạy sau khi restore-only SG đã tồn tại và được review:

```bash
export AWS_PROFILE=your-sso-profile
export RESTORE_DRILL_ID=rel25-20260723
export RESTORE_TIMESTAMP=2026-07-23T08:45:00Z
export RESTORE_TARGET_IDENTIFIER=techx-tf4-drill-rel25-20260723-accounting-restore
export DB_SUBNET_GROUP_NAME=techx-tf4-postgresql-private
export RESTORE_SECURITY_GROUP_IDS=sg-restore-only
export CONFIRM_PITR_RESTORE=YES

bash ./docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh \
  | tee "rel25-pitr-${RESTORE_DRILL_ID}.log"
```

Thay timestamp và restore-only SG bằng giá trị đã được duyệt. Không copy ví dụ
nguyên xi để chạy.

Log thành công phải có:

```text
phase=preflight message=phase_start
phase=restore_request message=phase_start
phase=wait_initial_available message=phase_end duration_seconds=...
phase=apply_network_access message=phase_end duration_seconds=...
phase=complete message=rto_end rto_seconds=...
```

## Acceptance Criteria

| Tiêu chí | Trạng thái/Evidence |
| --- | --- |
| Restore thành công trong internal dry run | Chưa chạy: live scan chưa có restore-only SG; không dùng production SG để đóng giả tiêu chí. |
| Script không chứa secret thật | Đạt: script không có password/token/secret value. |
| Có log start/end để tính RTO | Đạt: log UTC từng phase và tổng `rto_seconds`. |
| Không đụng production instance | Đạt theo thiết kế: production chỉ được gọi bằng API `describe`; restore/modify chỉ dùng target identifier mới. |

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

## Cleanup sau dry run

Sau khi validation và lưu evidence, xóa target theo runbook cleanup đã được
review. Trước khi xóa, xác nhận identifier có `drill`, `accounting` và
`restore`; không chạy lệnh cleanup với production identifier.
