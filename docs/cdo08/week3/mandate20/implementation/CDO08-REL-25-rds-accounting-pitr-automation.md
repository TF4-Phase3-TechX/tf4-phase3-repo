# CDO08 REL-25 - RDS accounting PITR automation

## Mục tiêu

Khôi phục schema `accounting` về một timestamp được chọn mà không thay đổi
production RDS:

```text
production automated backup
  -> private RDS PITR target
  -> dump riêng accounting
  -> accounting_drill trên restored RDS
  -> validation và RTO
  -> cleanup
```

RDS PITR hoạt động ở cấp instance nên database `otel` trên target tạm thời vẫn
có `catalog` và `reviews`. Workflow chỉ export `accounting`; database đích
`accounting_drill` chỉ được chứa schema `accounting`.

## Script

```text
docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh
```

Script dùng temporary private EC2 qua SSM, không dùng EKS Pod SG, EKS node SG,
public IP hoặc SSH.

## Input bắt buộc

| Biến | Ý nghĩa |
| --- | --- |
| `AWS_PROFILE` | AWS SSO profile của operator. |
| `EXPECTED_AWS_ACCOUNT_ID` | Guardrail account ID. |
| `RESTORE_DRILL_ID` | Dạng `rel25-YYYYMMDD`, có thể thêm suffix. |
| `RESTORE_TIMESTAMP` | Timestamp UTC nằm trong PITR window. |
| `RESTORE_TARGET_IDENTIFIER` | `techx-tf4-drill-${RESTORE_DRILL_ID}-accounting-restore`. |

Live run còn yêu cầu:

```text
CONFIRM_PITR_RESTORE=YES
```

Các default an toàn:

```text
SOURCE_DB_IDENTIFIER=techx-tf4-postgresql
DB_SUBNET_GROUP_NAME=techx-tf4-postgresql-private
ACCOUNTING_SOURCE_DB=otel
ACCOUNTING_TARGET_DB=accounting_drill
VALIDATION_INSTANCE_TYPE=t3.nano
AUTO_CLEANUP=true
TTL_HOURS=6
```

## Workflow

1. Kiểm tra account, source status, private RDS, subnet và PITR window.
2. Fail nếu target trùng production, sai prefix hoặc đã tồn tại.
3. Tạo temporary EC2 IAM role/profile chỉ cho SSM.
4. Tạo validation SG và restore SG.
5. Restore SG chỉ nhận TCP/5432 từ validation SG.
6. Tạo EC2 private, encrypted EBS, IMDSv2, không ingress/public IP/SSH.
7. Chờ SSM Online và kiểm tra PostgreSQL 17 client.
8. Gọi `restore-db-instance-to-point-in-time`.
9. Chờ `available`, apply lại SG và xác minh target private.
10. Cấp validation role quyền đọc đúng source RDS managed master secret.
11. PITR target dùng credential được kế thừa; nếu AWS trả target secret ARN riêng,
    script chỉ dùng đúng ARN đó.
12. Qua SSM, tạo database `accounting_drill`.
13. Dump `--schema=accounting` từ `otel`.
14. Tạo schema `accounting` rõ ràng trong database đích vì `pg_restore
    --schema=accounting` không tạo schema khi filter archive theo schema.
15. Restore dump vào `accounting_drill`.
16. So row counts và kiểm tra duplicate, orphan, unexpected schema, sequence.
17. Ghi duration từng phase và tổng RTO.
18. EXIT trap cleanup toàn bộ tài nguyên tạm.

## RTO

`rto_start` được ghi ngay trước lệnh PITR. `rto_end` chỉ được ghi sau khi:

- RDS available;
- network verified;
- accounting export hoàn tất;
- import hoàn tất;
- validation pass.

Thời gian chuẩn bị EC2 nằm ngoài RTO nhưng vẫn có phase duration riêng. Đây là
validation client được chuẩn bị trước khi yêu cầu recovery bắt đầu.

## Error handling và cleanup

Script dùng `set -Eeuo pipefail` và EXIT trap. Mặc định `AUTO_CLEANUP=true`, kể
cả khi workflow lỗi.

Cleanup theo thứ tự:

```text
RDS -> EC2/EBS -> restore SG -> validation SG -> instance profile -> IAM role
```

Nếu cleanup lỗi, script trả non-zero và ghi `cleanup_remaining_*` cùng resource
ID. Không được đánh dấu dry run thành công khi còn resource này.

Chỉ đặt `AUTO_CLEANUP=false` khi leader yêu cầu giữ resource để điều tra. Chế độ
này ghi toàn bộ resource ID còn lại và phát sinh chi phí.

## Acceptance Criteria mapping

| Tiêu chí | Cách đáp ứng |
| --- | --- |
| Nhận restore timestamp | `RESTORE_TIMESTAMP`, parse UTC và kiểm tra PITR window. |
| PITR sang instance mới | Naming contract và `restore-db-instance-to-point-in-time`. |
| Wait và apply network | Poll status, `modify-db-instance`, verify private/SG/endpoint. |
| Timestamp từng phase | UTC start/end và `duration_seconds`. |
| Internal dry run | Chỉ đạt sau live log có validation pass, RTO và cleanup pass. |
| Không có secret thật | Secret lấy runtime trong EC2, không trả ra output. |
| Không đụng production | Production chỉ dùng với `describe` và làm PITR source. |
| Accounting-only | `pg_dump --schema=accounting`; target database chặn catalog/reviews. |

## Giới hạn

- Script dùng GNU `date`, phù hợp Git Bash/Linux.
- Local cần AWS CLI v2, Bash, `base64` và `tee`.
- EC2 bootstrap cần private subnet có NAT hoặc VPC endpoints/package mirror.
- Live run phát sinh chi phí ngắn hạn cho RDS và EC2 cho tới khi cleanup xong.

## Live verification

Internal dry run `rel25-20260726-b` ngày 2026-07-26 đã PASS:

```text
PITR target available: PASS
Accounting source counts: 205891,205891,377846
Accounting target counts: 205891,205891,377846
Duplicate/orphan/unexpected schema: 0
RTO: 1572 seconds
Exit code: 0
Cleanup: PASS
```

Evidence:

```text
docs/cdo08/week3/mandate20/evidence/CDO08-REL-25-INTERNAL-DRY-RUN-EVIDENCE.md
```
