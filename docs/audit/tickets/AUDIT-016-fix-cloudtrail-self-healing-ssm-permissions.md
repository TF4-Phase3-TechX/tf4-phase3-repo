# [AUDIT-016] Bổ sung quyền SSM Automation cho CloudTrail anti-blinding self-healing

**Trạng thái**: TO DO<br>
**Ngày xác minh runtime**: 21/07/2026<br>
**Reporter**: LÊ Trung Trực - Nhóm CDO07 (Auditability)<br>

**Assignee**: CDO08 / Platform Admin / IAM Owner<br>
**Nhóm phối hợp**: CDO07 (Audit), CDO04 (Terraform / Platform)<br>
**Độ ưu tiên**: P0 - Blocker nghiệm thu Mandate #12<br>
**Epic**: Mandate-12 / Anti-Blinding Audit Trail<br>
**Account / Region**: `511825856493` / `us-east-1`<br>
**Principal cần cập nhật**: `tf4-cloudtrail-auto-remediation-eventbridge-role`

---

## 1. Tóm tắt vấn đề

Luồng self-healing CloudTrail sử dụng:

```text
StopLogging
  -> EventBridge rule
  -> SSM Automation tf4-restore-cloudtrail-logging
  -> cloudtrail:StartLogging
```

EventBridge đã bắt đúng sự kiện `StopLogging`, nhưng không khởi tạo được SSM Automation execution. CloudTrail không tự bật lại và phải dùng `StartLogging` thủ công.

Payload EventBridge target đã được sửa sang direct-parameter và đã xuất hiện đúng ở runtime. Drill sau khi deploy vẫn ghi nhận `FailedInvocations`, vì vậy lỗi payload cũ đã được loại trừ.

Policy của EventBridge invocation role hiện chỉ cấp `ssm:StartAutomationExecution` trên resource type `automation-definition`. AWS Systems Manager hiện yêu cầu quyền này trên cả SSM `document` và resource `automation-execution` được sinh động khi bắt đầu runbook.

Ticket này chỉ yêu cầu bổ sung resource scope cho role dịch vụ hiện hữu. Không yêu cầu mở quyền cho user, Permission Set audit hoặc workload application.

---

## 2. Bằng chứng runtime

### 2.1. EventBridge target đã dùng payload đúng

Target:

```text
Rule:   tf4-cloudtrail-stoplogging-auto-remediation
Target: RestoreCloudTrailLogging
ARN:    arn:aws:ssm:us-east-1:511825856493:automation-definition/tf4-restore-cloudtrail-logging
Role:   arn:aws:iam::511825856493:role/tf4-cloudtrail-auto-remediation-eventbridge-role
```

Input runtime:

```json
{
  "AutomationAssumeRole": [
    "arn:aws:iam::511825856493:role/tf4-cloudtrail-auto-remediation-automation-role"
  ],
  "TrailName": [
    "tf4-general-cloudtrail"
  ]
}
```

Không còn wrapper `{"Parameters": {...}}` trong target input.

### 2.2. Kết quả drill ngày 21/07/2026

| Mốc | UTC | Kết quả |
|---|---|---|
| Gọi `StopLogging` | `11:25:39Z` | Thành công |
| EventBridge `TriggeredRules` | phút `11:25Z` | `1` |
| EventBridge `Invocations` | phút `11:25Z` | `1` |
| EventBridge `FailedInvocations` | phút `11:25Z` | `1` |
| SSM Automation execution | Sau drill | `0` execution |
| Manual fallback `StartLogging` | `11:26:20Z` | Thành công |
| Cửa sổ mù quan sát được | `11:25:39Z` - `11:26:20Z` | Khoảng `41 giây` |
| Trạng thái cuối | Sau fallback | `IsLogging=true` |

Kết luận từ evidence:

1. Event pattern đúng vì `TriggeredRules=1`.
2. EventBridge đã cố gọi target vì `Invocations=1`.
3. Target invocation thất bại vì `FailedInvocations=1`.
4. SSM chưa tạo execution, nên lỗi xảy ra trước khi step `cloudtrail:StartLogging` trong runbook được chạy.
5. Payload direct-parameter đã đúng tại runtime; lỗi payload không còn là nguyên nhân của drill này.

---

## 3. Policy hiện tại

Inline policy hiện tại của role:

```text
Role:       tf4-cloudtrail-auto-remediation-eventbridge-role
Policy:     tf4-cloudtrail-start-automation-policy
Trust:      events.amazonaws.com
```

Statement hiện tại:

```json
{
  "Sid": "AllowStartAutomationExecution",
  "Effect": "Allow",
  "Action": "ssm:StartAutomationExecution",
  "Resource": [
    "arn:aws:ssm:us-east-1:511825856493:automation-definition/tf4-restore-cloudtrail-logging",
    "arn:aws:ssm:us-east-1:511825856493:automation-definition/tf4-restore-cloudtrail-logging:*"
  ]
}
```

`iam:PassRole` hiện đã scope vào đúng automation role và không cần mở rộng:

```json
{
  "Sid": "AllowPassAutomationRoleToSSM",
  "Effect": "Allow",
  "Action": "iam:PassRole",
  "Resource": "arn:aws:iam::511825856493:role/tf4-cloudtrail-auto-remediation-automation-role",
  "Condition": {
    "StringEquals": {
      "iam:PassedToService": "ssm.amazonaws.com"
    }
  }
}
```

Automation role cũng đã có quyền tối thiểu trên đúng trail:

```json
{
  "Effect": "Allow",
  "Action": "cloudtrail:StartLogging",
  "Resource": "arn:aws:cloudtrail:us-east-1:511825856493:trail/tf4-general-cloudtrail"
}
```

---

## 4. Cơ sở kỹ thuật AWS

AWS Systems Manager nêu rõ:

- Resource type `automation-definition` đang được deprecate.
- Policy dùng `ssm:StartAutomationExecution` cần cho phép trên `document` và `automation-execution`.
- AWS policy example cho phép chạy một automation document sử dụng đồng thời:
  - `arn:aws:ssm:<region>:<account>:document/<DocumentName>`
  - `arn:aws:ssm:<region>:<account>:automation-execution/*`

Tài liệu tham chiếu:

- AWS Systems Manager IAM integration: <https://docs.aws.amazon.com/en_en/systems-manager/latest/userguide/security_iam_service-with-iam.html>
- AWS identity-based policy examples for Automation: <https://docs.aws.amazon.com/en_us/systems-manager/latest/userguide/automation-setup-identity-based-policies.html>

Execution ARN có dạng:

```text
arn:aws:ssm:us-east-1:511825856493:automation-execution/<AWS-generated-execution-id>
```

Execution ID chỉ tồn tại sau khi API bắt đầu tạo execution, nên không thể liệt kê ARN cụ thể trước. Wildcard `automation-execution/*` là cần thiết nhưng vẫn giới hạn theo service, region, account và resource type.

---

## 5. Yêu cầu thay đổi

CDO08 / Platform Admin cập nhật inline policy `tf4-cloudtrail-start-automation-policy` của role:

```text
arn:aws:iam::511825856493:role/tf4-cloudtrail-auto-remediation-eventbridge-role
```

### 5.1. Policy delta bắt buộc

Thêm hai resource sau vào statement `ssm:StartAutomationExecution`:

```json
[
  "arn:aws:ssm:us-east-1:511825856493:document/tf4-restore-cloudtrail-logging",
  "arn:aws:ssm:us-east-1:511825856493:automation-execution/*"
]
```

### 5.2. Statement đề xuất trong giai đoạn chuyển đổi

Giữ ARN `automation-definition` hiện tại trong lần triển khai đầu để tránh rủi ro tương thích với EventBridge target; bổ sung resource types mới theo hướng dẫn AWS:

```json
{
  "Sid": "AllowStartCloudTrailRestoreAutomation",
  "Effect": "Allow",
  "Action": "ssm:StartAutomationExecution",
  "Resource": [
    "arn:aws:ssm:us-east-1:511825856493:document/tf4-restore-cloudtrail-logging",
    "arn:aws:ssm:us-east-1:511825856493:automation-execution/*",
    "arn:aws:ssm:us-east-1:511825856493:automation-definition/tf4-restore-cloudtrail-logging",
    "arn:aws:ssm:us-east-1:511825856493:automation-definition/tf4-restore-cloudtrail-logging:*"
  ]
}
```

Sau khi nghiệm thu thành công, CDO07/CDO08 có thể tạo follow-up để kiểm tra và loại hai ARN `automation-definition` cũ.

### 5.3. Terraform delta đề xuất

Trong `infra/terraform/cloudtrail-auto-remediation.tf`, cập nhật resource list của `AllowStartAutomationExecution`:

```hcl
Resource = [
  "arn:${data.aws_partition.current.partition}:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:document/${local.cloudtrail_auto_remediation_document_name}",
  "arn:${data.aws_partition.current.partition}:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:automation-execution/*",
  local.cloudtrail_automation_definition_arn,
  "${local.cloudtrail_automation_definition_arn}:*"
]
```

---

## 6. Ranh giới least privilege

Ticket này **không yêu cầu**:

```text
ssm:*
iam:*
events:*
cloudtrail:*
Resource: "*"
```

Các giới hạn phải được giữ:

- `ssm:StartAutomationExecution` chỉ cho đúng document `tf4-restore-cloudtrail-logging` và execution trong account TF4 / `us-east-1`.
- `iam:PassRole` chỉ cho `tf4-cloudtrail-auto-remediation-automation-role`.
- `iam:PassedToService` phải là `ssm.amazonaws.com`.
- Automation role chỉ được `cloudtrail:StartLogging` trên `tf4-general-cloudtrail`.
- Không cấp thêm quyền cho `TF4-AuditReadOnlyAndAnalyze` trong ticket này.
- Không thay đổi S3 Object Lock, retention, KMS, CloudTrail event selectors, EKS, application workload hoặc `flagd`.

---

## 7. Kế hoạch triển khai an toàn

1. Cập nhật Terraform theo mục 5.3.
2. Chạy `terraform plan`.
3. Xác nhận plan chỉ update inline IAM policy của EventBridge role; không add/destroy resource.
4. Apply bằng Terraform deployment role đã được phê duyệt.
5. Đọc lại inline policy runtime và xác nhận có ARN `document` cùng `automation-execution/*`.
6. Xác nhận EventBridge rule/target vẫn `ENABLED` và payload direct-parameter không bị revert.
7. Chạy preflight trước khi thực hiện `StopLogging`.
8. Chuẩn bị sẵn manual fallback `StartLogging` và người chịu trách nhiệm theo dõi `IsLogging`.
9. Thực hiện một drill có kiểm soát; fallback thủ công nếu chưa recovery trong 15 giây.
10. Thu thập evidence ở mục 9.

---

## 8. Lệnh nghiệm thu

### 8.1. Xác minh target và trail trước drill

```powershell
aws events list-targets-by-rule `
  --rule tf4-cloudtrail-stoplogging-auto-remediation `
  --region us-east-1 `
  --profile TF4-AuditReadOnlyAndAnalyze

aws cloudtrail get-trail-status `
  --name tf4-general-cloudtrail `
  --region us-east-1 `
  --profile TF4-AuditReadOnlyAndAnalyze
```

Điều kiện trước drill:

- Target input là direct-parameter.
- Rule ở trạng thái `ENABLED`.
- Trail có `IsLogging=true`.
- Có người trực manual fallback.

### 8.2. Manual fallback chuẩn bị sẵn

```powershell
aws cloudtrail start-logging `
  --name tf4-general-cloudtrail `
  --region us-east-1 `
  --profile TF4-AuditReadOnlyAndAnalyze
```

### 8.3. Drill

```powershell
aws cloudtrail stop-logging `
  --name tf4-general-cloudtrail `
  --region us-east-1 `
  --profile TF4-AuditReadOnlyAndAnalyze
```

Poll `get-trail-status` liên tục. Nếu chưa tự phục hồi trong 15 giây, chạy manual fallback ngay.

### 8.4. Kiểm tra SSM execution

```powershell
aws ssm describe-automation-executions `
  --filters Key=DocumentNamePrefix,Values=tf4-restore-cloudtrail-logging `
  --region us-east-1 `
  --profile TF4-AuditReadOnlyAndAnalyze
```

---

## 9. Evidence cần đính kèm khi đóng ticket

| Evidence ID | Nội dung | Kết quả đạt |
|---|---|---|
| `AUDIT-016-E01` | Terraform plan IAM policy delta | Chỉ update in-place policy của EventBridge role |
| `AUDIT-016-E02` | Inline policy runtime sau apply | Có exact document ARN và `automation-execution/*` |
| `AUDIT-016-E03` | EventBridge target runtime | Direct-parameter, đúng target và role ARN |
| `AUDIT-016-E04` | CloudWatch metric của drill | `TriggeredRules=1`, `Invocations=1`, `FailedInvocations=0` |
| `AUDIT-016-E05` | SSM Automation execution | Có execution ID, status `Success` |
| `AUDIT-016-E06` | CloudTrail Event History | `StopLogging` bởi tester và `StartLogging` bởi automation role |
| `AUDIT-016-E07` | Trail status sau drill | `IsLogging=true` không cần manual fallback |
| `AUDIT-016-E08` | Timeline UTC | Recovery time được tính và ghi rõ |

---

## 10. Rollback

Nếu thay đổi IAM gây lỗi ngoài dự kiến:

1. Khôi phục resource list cũ của inline policy bằng Terraform.
2. Xác nhận EventBridge rule/target không bị xóa.
3. Xác nhận CloudTrail vẫn `IsLogging=true`.
4. Không chạy thêm `StopLogging` cho tới khi nguyên nhân được điều tra.
5. Lưu plan/apply output và EventBridge metrics làm evidence sự cố.

Rollback policy không xóa SSM document, EventBridge rule, CloudTrail trail hoặc audit logs.

---

## 11. Definition of Done

- Inline policy của `tf4-cloudtrail-auto-remediation-eventbridge-role` cho phép `ssm:StartAutomationExecution` trên:
  - Exact document `tf4-restore-cloudtrail-logging`.
  - `automation-execution/*` trong account `511825856493`, region `us-east-1`.
- `iam:PassRole` vẫn chỉ áp dụng cho automation role và `ssm.amazonaws.com`.
- Terraform plan không add/destroy resource ngoài phạm vi.
- EventBridge drill có `FailedInvocations=0`.
- SSM tạo automation execution với trạng thái `Success`.
- `StartLogging` được quy về `tf4-cloudtrail-auto-remediation-automation-role`.
- CloudTrail tự trở về `IsLogging=true` mà không cần fallback thủ công.
- Recovery time được đo và đưa vào evidence Mandate #12.
- Evidence `AUDIT-016-E01` đến `AUDIT-016-E08` được lưu trong PR/Jira/tài liệu nghiệm thu.
