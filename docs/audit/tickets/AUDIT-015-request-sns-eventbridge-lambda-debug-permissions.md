# [Permissions] Yêu cầu bổ sung quyền Debug SNS, EventBridge, Lambda và thực thi Security Alerts Test Plan cho Audit Profile (AUDIT-015)

## 1. Tóm tắt vấn đề
Hiện tại, trong quá trình triển khai và kiểm toán (audit), hệ thống cảnh báo bảo mật được định tuyến qua EventBridge -> SNS -> Lambda (để bắn về Slack). Khi tiến hành kiểm thử và xác thực các cơ chế cảnh báo này, tài khoản của vai trò `TF4-AuditReadOnlyAndAnalyze` liên tục gặp lỗi `AccessDeniedException`.

Quyền hiện tại quá hạn chế, không cho phép giả lập các sự kiện bảo mật, publish tin nhắn test lên SNS, hoặc xem/debug chi tiết Lambda logs. Để thực hiện audit đầy đủ luồng cảnh báo này và chạy các kế hoạch kiểm thử bảo mật (Security Alerts Test Plan), cần phải được cấp thêm các quyền mở rộng.

## 2. Chi tiết các quyền cần bổ sung (Required Permissions)

Để hoàn tất việc kiểm thử hệ thống cảnh báo, cần bổ sung các quyền sau cho role `TF4-AuditReadOnlyAndAnalyze`:

### 2.1. AWS EventBridge & SNS (Để giả lập và kiểm tra luồng tin nhắn)
* **Resource:** `*` (hoặc giới hạn cho arn prefix tương ứng)
* **Actions:**
  * `events:PutEvents`
  * `events:ListRules`
  * `events:DescribeRule`
  * `events:ListTargetsByRule`
  * `sns:ListTopics`
  * `sns:GetTopicAttributes`
  * `sns:Publish`
  * `sns:ListSubscriptionsByTopic`

### 2.2. AWS Lambda & CloudWatch Logs (Để debug luồng Lambda đẩy về Slack)
* **Resource:** `*` (hoặc giới hạn cho các function/log groups liên quan đến slack alerts)
* **Actions:**
  * `lambda:GetFunction`
  * `lambda:ListFunctions`
  * `lambda:InvokeFunction`
  * `logs:FilterLogEvents`
  * `logs:DescribeLogStreams`
  * `logs:GetLogEvents`

### 2.3. Các AWS Services phục vụ Kế hoạch kiểm thử (Test Plan)
*(Các thao tác gây ra sự kiện bảo mật để EventBridge bắt)*
* **Resource:** `*` (Sử dụng trên môi trường phi sản xuất hoặc tài nguyên test)
* **Actions:**
  * `cloudtrail:StopLogging`, `cloudtrail:StartLogging`, `cloudtrail:DeleteTrail`
  * `iam:CreateUser`, `iam:DeleteUser`, `iam:CreateAccessKey`, `iam:DeleteAccessKey`, `iam:CreateRole`, `iam:AttachRolePolicy`
  * `s3:PutBucketPolicy`, `s3:PutBucketAcl`
  * `ec2:AuthorizeSecurityGroupIngress`, `ec2:RevokeSecurityGroupIngress`
  * `config:DeleteConfigurationRecorder`
  * `eks:CreateAccessEntry`, `eks:AssociateAccessPolicy`
  * `secretsmanager:GetSecretValue`
  * `ssm:StartSession`

## 3. Yêu cầu hành động cho Admin/DevOps
Vui lòng cập nhật IAM Policy hoặc SSO Permission Set của 'TF4-AuditReadOnlyAndAnalyze' role (hoặc tạo role temporary phục vụ audit) với các quyền sau:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowDebugSecurityAlertsPipeline",
            "Effect": "Allow",
            "Action": [
                "events:PutEvents",
                "events:ListRules",
                "events:DescribeRule",
                "events:ListTargetsByRule",
                "sns:ListTopics",
                "sns:GetTopicAttributes",
                "sns:Publish",
                "sns:ListSubscriptionsByTopic",
                "lambda:GetFunction",
                "lambda:ListFunctions",
                "lambda:InvokeFunction",
                "logs:FilterLogEvents",
                "logs:DescribeLogStreams",
                "logs:GetLogEvents",
                "ssm:StartSession"
            ],
            "Resource": "*"
        },
        {
            "Sid": "AllowTriggerSecurityAlertsForTesting",
            "Effect": "Allow",
            "Action": [
                "cloudtrail:StopLogging",
                "cloudtrail:StartLogging",
                "cloudtrail:DeleteTrail",
                "iam:CreateUser",
                "iam:DeleteUser",
                "iam:CreateAccessKey",
                "iam:DeleteAccessKey",
                "iam:CreateRole",
                "iam:AttachRolePolicy",
                "s3:PutBucketPolicy",
                "s3:PutBucketAcl",
                "ec2:AuthorizeSecurityGroupIngress",
                "ec2:RevokeSecurityGroupIngress",
                "config:DeleteConfigurationRecorder",
                "eks:CreateAccessEntry",
                "eks:AssociateAccessPolicy",
                "secretsmanager:GetSecretValue"
            ],
            "Resource": "*"
        }
    ]
}
```

## 4. Tiêu chí nghiệm thu (DoD)
* Auditor chạy thành công lệnh `aws events put-events` hoặc `aws sns publish` mà không gặp lỗi `AccessDeniedException`.
* Có thể kiểm tra được CloudWatch logs của Lambda gửi Slack để debug.
* Các hành động giả lập (ví dụ `aws cloudtrail stop-logging`) chạy thành công, kích hoạt EventBridge, chuyển tới SNS và Lambda đẩy thông báo lên Slack hoàn chỉnh.

---

## Phụ lục: Kế hoạch kiểm thử cảnh báo bảo mật (Security Alert Test Plan)

Các kịch bản kiểm thử dưới đây sẽ được thực thi ngay sau khi quyền được cấp, nhằm mục đích giả lập sự cố.

### 4.1 Cảnh báo hành vi né tránh CloudTrail
* **Kịch bản 1:** Dừng CloudTrail Logging (`aws cloudtrail stop-logging --name tf4-general-cloudtrail`)
* **Kịch bản 2:** Xoá CloudTrail Trail

### 4.2 Cảnh báo sự thay đổi IAM và leo thang đặc quyền
* **Kịch bản 1:** Tạo người dùng IAM mới (`aws iam create-user ...`)
* **Kịch bản 2:** Tạo Access Key cho người dùng
* **Kịch bản 3:** Tạo hoặc thay đổi Role & Policy (`aws iam attach-role-policy ...`)

### 4.3 Cảnh báo thay đổi Policy của S3 Bucket
* **Kịch bản 1:** Chỉnh sửa Bucket Policy (`aws s3api put-bucket-policy ...`)
* **Kịch bản 2:** Chỉnh sửa Bucket ACL sang Public Read

### 4.4 Các kịch bản khác
* Đăng nhập Root bằng Console.
* Mở cổng mạng nguy hiểm: Ingress `0.0.0.0/0` qua Security Group.
* Lấy giá trị Secret (`aws secretsmanager get-secret-value` hoặc `aws ssm get-parameter`).
* Cố tình tạo S3 public bucket để Access Analyzer phát hiện và bắn cảnh báo.
