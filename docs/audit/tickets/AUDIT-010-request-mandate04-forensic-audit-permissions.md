# [AUDIT-010] Yêu cầu bổ sung quyền read-only phục vụ forensic audit cho Mandate #4

**Trạng thái**: TO DO  
**Người yêu cầu (Reporter)**: Trần Minh Quang - Nhóm CDO07 (Audit)  
**Người thực hiện (Assignee)**: Nhóm CDO08 (Security/SSO/IAM)  
**Nhóm phối hợp**: Nhóm CDO07 (nghiệm thu evidence), Nhóm CDO04 (Observability/Platform, nếu cần đối chiếu CloudWatch alarm path)  
**Độ ưu tiên (Priority)**: P0 (Blocker nghiệm thu Mandate #4 forensic audit)  
**Epic**: Mandate-04 / Auditability - forensic audit, log integrity, change trail

---

## 1. Bối cảnh (Context)

Mandate #4 yêu cầu TF4 chứng minh được: khi có một hành động hoặc sự cố đã xảy ra, team có thể dựng lại timeline "ai làm gì, khi nào" từ audit log / trace, đồng thời chứng minh dấu vết đó đáng tin và không bị sửa/xóa tùy tiện.

Theo file phân công trụ:

- `docs/epic-01-addressing-system-gap/GAP-TO-PILLAR-MAPPING.md`: CDO07 là owner trụ Auditability, chịu trách nhiệm K8s audit, CloudTrail, change management, log integrity và evidence collection.
- CDO08 là owner trụ Security + Reliability, trong đó Security chịu trách nhiệm hardening, least-privilege, credentials và access control.
- `docs/audit/TEAM_ASSIGNMENT.md`: Team Audit chỉ làm audit/evidence/change trace; các vấn đề thiết lập Security, Network, Reliability thuộc về CDO08.

Vì vậy, ticket này do CDO07 tạo để yêu cầu CDO08 cập nhật quyền read-only cho SSO Permission Set `TF4-AuditReadOnlyAndAnalyze`. CDO07 sẽ nghiệm thu lại bằng AWS CLI và lưu evidence cho Mandate #4.

Trong lần kiểm tra bằng AWS CLI ngày 2026-07-14, profile SSO `TF4-AuditReadOnlyAndAnalyze` đã xác minh được các dấu vết cơ bản từ CloudTrail, EKS audit log và SSM session. Tuy nhiên, profile này vẫn thiếu một số quyền read-only cần thiết để chứng minh log integrity, bucket protection, alert coverage và mapping danh tính người dùng.

Một số quyền liên quan đã xuất hiện trong ticket cũ:

- `AUDIT-002-fix-iam-cloudwatch.md` đã yêu cầu `cloudwatch:DescribeAlarms`.
- `AUDIT-004-request-cloudtrail-s3-permissions.md` đã yêu cầu `s3:GetObject`.

Tuy nhiên, chưa có ticket nào bao phủ đầy đủ nhóm quyền forensic cho Mandate #4 bên dưới. Ticket này gom các quyền read-only còn thiếu và vẫn giữ lại các quyền bị trùng để tiện nghiệm thu end-to-end.

## 2. Yêu cầu từ CDO08 (The What)

Team CDO08 vui lòng cập nhật SSO Permission Set `TF4-AuditReadOnlyAndAnalyze` để bổ sung các quyền read-only sau.

| Quyền | Mục đích |
|---|---|
| `s3:GetBucketPolicyStatus` | Kiểm tra CloudTrail log bucket có public hay không. |
| `s3:GetBucketPolicy` | Kiểm tra bucket policy, đặc biệt các kiểm soát deny-delete / tamper-evident. |
| `s3:GetLifecycleConfiguration` | Kiểm tra retention và lifecycle rule của audit logs. |
| `s3:GetBucketLogging` | Kiểm tra access logging của CloudTrail log bucket. |
| `cloudwatch:DescribeAlarms` | Kiểm tra alarm và alert coverage liên quan audit/logging. |
| `cloudtrail:ListPublicKeys` | Lấy CloudTrail public keys để phục vụ log integrity validation. |
| `cloudtrail:GetInsightSelectors` | Kiểm tra CloudTrail Insights có được cấu hình hay không. |
| `cloudtrail:ValidateLogs` | Xác minh CloudTrail log files không bị sửa đổi. |
| `s3:GetObject` | Đọc CloudTrail log objects trong S3 khi cần raw log evidence. |
| `identitystore:DescribeUser` | Map Identity Store user ID về người dùng cụ thể. |
| `identitystore:ListUsers` | Tra cứu user phục vụ human accountability mapping. |

Các quyền trên chỉ phục vụ thu thập evidence và kiểm chứng audit; không cấp quyền thay đổi tài nguyên.

## 3. Evidence từ kiểm tra bằng AWS CLI

Các kiểm tra sau đã chạy thành công:

- `aws cloudtrail describe-trails` hiển thị trail `tf4-general-cloudtrail`.
- `aws cloudtrail get-trail-status` hiển thị `IsLogging: true`.
- `aws eks describe-cluster` xác nhận EKS audit logging đã bật cho `api`, `audit`, và `authenticator`.
- `aws logs filter-log-events` đọc được sample event từ `kube-apiserver-audit`.
- `aws cloudtrail lookup-events` truy được SSM `StartSession` event về user `quang.tranminh`.
- `aws ssm describe-sessions` liệt kê được SSM session history của bastion `i-072084d1cf0b2f1c9`.

Các kiểm tra sau bị chặn bởi thiếu quyền:

- `s3:GetBucketPolicyStatus`
- `s3:GetBucketPolicy`
- `s3:GetLifecycleConfiguration`
- `s3:GetBucketLogging`
- `cloudwatch:DescribeAlarms`
- `cloudtrail:ListPublicKeys`
- `cloudtrail:GetInsightSelectors`

Các quyền bổ sung cần có để hoàn tất drill Mandate #4:

- `cloudtrail:ValidateLogs`
- `identitystore:DescribeUser`
- `identitystore:ListUsers`

## 4. Policy statement đề xuất

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Mandate04CloudTrailLogBucketAuditRead",
      "Effect": "Allow",
      "Action": [
        "s3:GetBucketPolicyStatus",
        "s3:GetBucketPolicy",
        "s3:GetLifecycleConfiguration",
        "s3:GetBucketLogging",
        "s3:GetObject"
      ],
      "Resource": [
        "arn:aws:s3:::tf4-cloudtrail-logs-bucket-*",
        "arn:aws:s3:::tf4-cloudtrail-logs-bucket-*/*"
      ]
    },
    {
      "Sid": "Mandate04CloudTrailIntegrityRead",
      "Effect": "Allow",
      "Action": [
        "cloudtrail:ListPublicKeys",
        "cloudtrail:GetInsightSelectors",
        "cloudtrail:ValidateLogs"
      ],
      "Resource": "*"
    },
    {
      "Sid": "Mandate04CloudWatchAlarmRead",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:DescribeAlarms"
      ],
      "Resource": "*"
    },
    {
      "Sid": "Mandate04IdentityStoreUserRead",
      "Effect": "Allow",
      "Action": [
        "identitystore:DescribeUser",
        "identitystore:ListUsers"
      ],
      "Resource": "*"
    }
  ]
}
```

## 5. Ranh giới trách nhiệm

- CDO08 owns cập nhật SSO Permission Set / IAM policy vì đây là phần Security, access control và least-privilege.
- CDO07 owns audit/evidence: chạy lại CLI checks, xác nhận hết `AccessDenied`, lưu evidence và cập nhật forensic runbook cho Mandate #4.
- CDO04 chỉ phối hợp nếu cần đối chiếu CloudWatch alarm path hoặc dữ liệu observability liên quan.
- Ticket này không yêu cầu CDO07 tự thay đổi IAM/SSO permission, đúng với ranh giới "Audit chỉ đọc và nghiệm thu".

## 6. Tiêu chí nghiệm thu (Acceptance Criteria / Evidence)

- [ ] CDO08 cập nhật permission set `TF4-AuditReadOnlyAndAnalyze`.
- [ ] CDO07 chạy lại được toàn bộ read-only CLI checks từng bị chặn mà không còn lỗi `AccessDenied`.
- [ ] CDO07 có thể validate CloudTrail log integrity hoặc ghi nhận rõ platform control gap còn lại.
- [ ] CDO07 có thể map Identity Store user ID trong trường CloudTrail `onBehalfOf` về người dùng cụ thể.
- [ ] Mandate #4 forensic runbook có đủ evidence từ CloudTrail, EKS audit, SSM session, alarm và identity mapping.

## 7. Ghi chú cho implementation sau khi được approve

Sau khi CDO08 cập nhật permission set, CDO07 sẽ chạy lại tối thiểu các nhóm lệnh sau:

- S3 bucket protection: `get-bucket-policy-status`, `get-bucket-policy`, `get-bucket-lifecycle-configuration`, `get-bucket-logging`.
- CloudTrail integrity: `list-public-keys`, `get-insight-selectors`, `validate-logs`.
- CloudWatch alarm evidence: `describe-alarms`.
- Identity mapping: `identitystore describe-user` hoặc `identitystore list-users`.

Kết quả pass/fail sẽ được lưu làm evidence cho Mandate #4. Nếu vẫn còn quyền thiếu, CDO07 sẽ mở ticket bổ sung hoặc cập nhật ticket này với output `AccessDenied` mới.

*(Sau khi hoàn thành, vui lòng tag CDO07 để nghiệm thu evidence Mandate #4.)*
