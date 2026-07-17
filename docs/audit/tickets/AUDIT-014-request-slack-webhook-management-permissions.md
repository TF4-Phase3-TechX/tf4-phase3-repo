# [Permissions] Yêu cầu bổ sung quyền ghi/tạo Secrets và SSM Parameters cho Audit/DevOps Profile (AUDIT-014)

## 1. Tóm tắt vấn đề
Để thực hiện đề xuất tối ưu bảo mật (**Least Privilege**): Loại bỏ hoàn toàn bước đồng bộ tự động `Sync Slack Webhooks to AWS` từ GitHub Actions runner. Slack Webhook URL (thông tin tĩnh) sẽ được nạp thủ công một lần trực tiếp lên AWS. 

Tuy nhiên, tài khoản/profile hiện tại của CDO07 đang thiếu các quyền ghi/tạo đối với AWS Secrets Manager và SSM Parameter Store để có thể thực hiện thao tác nạp này.

## 2. Chi tiết các quyền cần bổ sung (Required Permissions)

Để tạo/cập nhật Slack Webhook URL cho hệ thống Alertmanager và AWS Security Alerts, cần các quyền sau cho 'TF4-AuditReadOnlyAndAnalyze' role:

### 2.1. AWS Secrets Manager (Cho Alertmanager Slack Webhook)
* **Resource:** `arn:aws:secretsmanager:*:*:secret:techx/tf4/alertmanager-slack-webhook` (hoặc prefix tương ứng)
* **Actions:**
  * `secretsmanager:CreateSecret`
  * `secretsmanager:PutSecretValue`
  * `secretsmanager:DescribeSecret`

### 2.2. AWS Systems Manager Parameter Store (Cho Security Alerts Webhook)
* **Resource:** `arn:aws:ssm:*:*:parameter/security-alerts/slack-webhook-url`
* **Actions:**
  * `ssm:PutParameter`
  * `ssm:GetParameter`
  * `ssm:DescribeParameters`

### 2.3. AWS SNS, EventBridge, Lambda (Quyền Audit Read-Only để debug hệ thống cảnh báo)
* **Resource:** `*`
* **Actions:**
  * `sns:ListTopics`
  * `sns:GetTopicAttributes`
  * `events:ListRules`
  * `events:DescribeRule`
  * `lambda:GetFunction`
  * `lambda:ListFunctions`

## 3. Yêu cầu hành động cho Admin/DevOps
Vui lòng cập nhật IAM Policy hoặc SSO Permission Set của 'TF4-AuditReadOnlyAndAnalyze' role để bổ sung thêm các quyền sau:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowManageSlackWebhooksSecrets",
            "Effect": "Allow",
            "Action": [
                "secretsmanager:CreateSecret",
                "secretsmanager:PutSecretValue",
                "secretsmanager:DescribeSecret",
                "ssm:PutParameter",
                "ssm:GetParameter",
                "ssm:DescribeParameters",
                "sns:ListTopics",
                "sns:GetTopicAttributes",
                "events:ListRules",
                "events:DescribeRule",
                "lambda:GetFunction",
                "lambda:ListFunctions"
            ],
            "Resource": [
                "arn:aws:secretsmanager:*:*:secret:techx/tf4/alertmanager-slack-webhook*",
                "arn:aws:ssm:*:*:parameter/security-alerts/slack-webhook-url"
            ]
        }
    ]
}
```

## 4. Tiêu chí nghiệm thu (DoD)
* CDO07 chạy thành công lệnh ghi Parameter lên SSM và Secret lên Secrets Manager thông qua AWS CLI/Console mà không gặp lỗi `AccessDeniedException`.
