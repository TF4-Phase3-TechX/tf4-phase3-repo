# [Permissions] Yêu cầu bổ sung quyền tạo/cập nhật SMTP Secret cho Alertmanager Gmail SMTP (AUDIT-017)

## 1. Tóm tắt vấn đề

CDO07 đang chuẩn bị triển khai luồng gửi email thật cho Kubernetes Alertmanager:

```text
Prometheus alert rules -> Prometheus -> Alertmanager -> Gmail SMTP -> Google Group -> team members
```

GitOps đã có sẵn wiring External Secrets Operator cho SMTP secret:

```text
AWS Secrets Manager: techx/tf4/alertmanager
property: smtp-password
-> Kubernetes Secret: alertmanager-smtp-auth
-> Alertmanager file: /etc/alertmanager/secrets/smtp-password
```

Tuy nhiên role hiện tại `TF4-AuditReadOnlyAndAnalyze` chưa có quyền đọc/tạo/cập nhật secret `techx/tf4/alertmanager`.

Ticket quyền hiện có cho Slack webhook chỉ scope tới:

```text
arn:aws:secretsmanager:*:*:secret:techx/tf4/alertmanager-slack-webhook*
```

Scope trên không bao phủ SMTP secret:

```text
arn:aws:secretsmanager:us-east-1:511825856493:secret:techx/tf4/alertmanager*
```

Vì vậy CDO07 chưa thể tự nạp Gmail App Password vào AWS Secrets Manager để Alertmanager gửi email qua Gmail SMTP.

## 2. Chi tiết quyền cần bổ sung

Vui lòng bổ sung quyền tối thiểu sau cho role `TF4-AuditReadOnlyAndAnalyze` hoặc SSO Permission Set tương ứng.

### 2.1. AWS Secrets Manager

* **Resource:** `arn:aws:secretsmanager:us-east-1:511825856493:secret:techx/tf4/alertmanager*`
* **Actions:**
  * `secretsmanager:DescribeSecret`
  * `secretsmanager:CreateSecret`
  * `secretsmanager:PutSecretValue`
  * `secretsmanager:ListSecretVersionIds`

Ghi chú:

* `CreateSecret` chỉ cần thiết nếu secret `techx/tf4/alertmanager` chưa tồn tại.
* Nếu admin xác nhận secret đã tồn tại, có thể cấp tối thiểu `DescribeSecret`, `PutSecretValue`, và `ListSecretVersionIds`.
* Dấu `*` cuối ARN là cần thiết vì AWS Secrets Manager thường thêm suffix ngẫu nhiên vào ARN sau tên secret.

### 2.2. AWS KMS nếu dùng customer managed key

Nếu secret dùng AWS managed key `aws/secretsmanager`, không cần bổ sung KMS policy riêng.

Nếu secret dùng customer managed KMS key, vui lòng cấp thêm quyền KMS tối thiểu trên key tương ứng:

* `kms:Encrypt`
* `kms:Decrypt`
* `kms:GenerateDataKey`
* `kms:DescribeKey`

## 3. Policy đề xuất

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowManageAlertmanagerSmtpSecret",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:DescribeSecret",
        "secretsmanager:CreateSecret",
        "secretsmanager:PutSecretValue",
        "secretsmanager:ListSecretVersionIds"
      ],
      "Resource": "arn:aws:secretsmanager:us-east-1:511825856493:secret:techx/tf4/alertmanager*"
    }
  ]
}
```

## 4. Yêu cầu hành động cho Admin/DevOps

Vui lòng cập nhật IAM Policy hoặc SSO Permission Set của role `TF4-AuditReadOnlyAndAnalyze` để bổ sung quyền quản lý secret SMTP cho Alertmanager.

Không yêu cầu `Resource: "*"`. Quyền chỉ cần áp dụng cho secret:

```text
techx/tf4/alertmanager
```

Không cấp quyền quản lý các secret khác như Slack webhook, database credentials, application secrets, hoặc secret ngoài scope này.

## 5. Cách sử dụng sau khi được cấp quyền

Không commit Gmail App Password vào Git, Terraform state, ticket, log, hoặc terminal transcript dùng chung.

Nếu secret đã tồn tại:

```bash
aws secretsmanager put-secret-value \
  --secret-id techx/tf4/alertmanager \
  --secret-string '{"smtp-password":"<GMAIL_APP_PASSWORD>"}' \
  --region us-east-1
```

Nếu secret chưa tồn tại:

```bash
aws secretsmanager create-secret \
  --name techx/tf4/alertmanager \
  --secret-string '{"smtp-password":"<GMAIL_APP_PASSWORD>"}' \
  --region us-east-1
```

## 6. Tiêu chí nghiệm thu (DoD)

* CDO07 chạy thành công `aws secretsmanager describe-secret --secret-id techx/tf4/alertmanager --region us-east-1`.
* CDO07 tạo hoặc cập nhật được secret `techx/tf4/alertmanager` mà không gặp lỗi `AccessDeniedException`.
* Secret chứa JSON property `smtp-password`.
* External Secrets Operator sync được property `smtp-password` xuống Kubernetes Secret `alertmanager-smtp-auth` trong namespace `techx-observability`.
* Alertmanager pod mount được file `/etc/alertmanager/secrets/smtp-password`.

## 7. Ghi chú vận hành

* Gmail App Password là secret nhạy cảm, chỉ nhập qua phương thức được team duyệt.
* Sau smoke test có thể rotate/revoke App Password nếu cần.
* Pipeline AWS Security Slack Alert là luồng riêng và không bị thay đổi bởi ticket này.
