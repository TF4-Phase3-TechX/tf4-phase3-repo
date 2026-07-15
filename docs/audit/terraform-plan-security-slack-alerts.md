# Kế hoạch Triển khai Terraform: Hệ thống Cảnh báo Bảo mật qua Slack Thời gian thực (CloudTrail → EventBridge → SNS → Lambda → Slack)

## 1. Mục tiêu & Vấn đề giải quyết
**Vấn đề:** Đội Audit cần khả năng phát hiện và nhận thông báo ngay lập tức đối với các hành vi nhạy cảm trên AWS (như tắt ghi log, mở port ra Internet, thay đổi policy của S3, hoặc đăng nhập bằng root). Việc chờ đợi các báo cáo định kỳ (weekly report) là quá chậm để có thể phản ứng với một rủi ro bảo mật nghiêm trọng.

**Giải pháp & Lợi ích cho Team Audit:**
- Xây dựng hạ tầng tự động phát hiện các API call nhạy cảm trong thời gian thực (near real-time) và gửi cảnh báo đã được định dạng chuẩn về một kênh Slack thông qua Incoming Webhook.
- **Tối ưu chi phí:** Kiến trúc không yêu cầu chạy server liên tục (no polling). Quan trọng hơn, không phải tốn chi phí đẩy log vào CloudWatch Logs (Log ingestion). Hệ thống chỉ phát sinh chi phí (gần như 0đ) khi một sự kiện nhạy cảm thực sự diễn ra.

## 2. Kiến trúc
```
CloudTrail (hiện có) --> EventBridge Rule(s) --> SNS Topic (audit-security-alerts) --> Lambda (format) --> Slack Incoming Webhook
```
Cần sử dụng 2 rules EventBridge riêng biệt (do khác nguồn sự kiện) cùng trỏ về một SNS topic:
- **Rule A**: Các pattern liên quan đến CloudTrail management event (6 pattern bên dưới).
- **Rule B**: Các phát hiện từ IAM Access Analyzer (`source` khác nhau, không gộp chung vào Rule A được).

## 3. Giả định & Lưu ý trước khi viết Terraform
- Đã có sẵn tổ chức/tài khoản CloudTrail và đẩy sự kiện vào event bus `default`. KHÔNG TẠO MỚI trail — chỉ thêm EventBridge rules vào bus `default`.
- URL của Slack Incoming Webhook sẽ được lưu dưới dạng `SecureString` trong SSM Parameter Store (tương tự cờ circuit-breaker hiện có), được mã hóa bằng KMS key của dự án.
- Vùng (Region) và Tài khoản (Account) mục tiêu sẽ lấy theo cấu hình của module gốc đang gọi — không hardcode.
- Xây dựng dưới dạng một **Terraform module có khả năng tái sử dụng** nằm trong `infra/terraform/modules/`, không viết trực tiếp ở root.

## 4. Cấu trúc Module
```
infra/terraform/modules/security-slack-alerts/
├── main.tf          # Cấu hình provider chung, mô tả module
├── variables.tf
├── outputs.tf
├── eventbridge.tf   # aws_cloudwatch_event_rule x2, aws_cloudwatch_event_target x2
├── sns.tf           # aws_sns_topic, aws_sns_topic_policy, aws_sns_topic_subscription
├── lambda.tf        # aws_lambda_function, aws_lambda_permission, archive_file
├── iam.tf           # role cho Lambda và các policies
└── lambda_src/
    └── handler.py   # Code Python xử lý message
```
Root module (tại `infra/terraform/security-slack-alerts.tf`) sẽ gọi: `module "security_slack_alerts" { source = "./modules/security-slack-alerts" ... }`.

## 5. Các Pattern Theo Dõi

| # | Tín hiệu | Dịch vụ nguồn | Điều kiện bổ sung |
|---|---|---|---|
| 1 | StopLogging | cloudtrail.amazonaws.com | - |
| 2 | DeleteTrail | cloudtrail.amazonaws.com | - |
| 3 | ConsoleLogin | signin.amazonaws.com | `userIdentity.type = Root` |
| 4 | AuthorizeSecurityGroupIngress | ec2.amazonaws.com | Kiểm tra 0.0.0.0/0 được thực hiện ở Lambda, không nằm trong pattern của EventBridge |
| 5 | PutBucketPolicy / PutBucketAcl | s3.amazonaws.com | Kiểm tra quyền "public" được thực hiện ở Lambda (đọc body của policy/ACL) |
| 6 | DeleteConfigurationRecorder | config.amazonaws.com | - |
| 7 | Access Analyzer — new finding | aws.access-analyzer (sự kiện native, KHÔNG QUA CloudTrail) | Rule riêng biệt |

### Pattern cho Rule A (CloudTrail management events)
```json
{
  "source": ["aws.cloudtrail"],
  "detail-type": ["AWS API Call via CloudTrail"],
  "detail": {
    "$or": [
      { "eventSource": ["cloudtrail.amazonaws.com"], "eventName": ["StopLogging", "DeleteTrail"] },
      { "eventSource": ["signin.amazonaws.com"], "eventName": ["ConsoleLogin"], "userIdentity": { "type": ["Root"] } },
      { "eventSource": ["ec2.amazonaws.com"], "eventName": ["AuthorizeSecurityGroupIngress"] },
      { "eventSource": ["s3.amazonaws.com"], "eventName": ["PutBucketPolicy", "PutBucketAcl"] },
      { "eventSource": ["config.amazonaws.com"], "eventName": ["DeleteConfigurationRecorder"] }
    ]
  }
}
```

### Pattern cho Rule B (Access Analyzer)
```json
{
  "source": ["aws.access-analyzer"],
  "detail-type": ["Access Analyzer Finding"]
}
```

## 6. Đặc tả Resource

### 6.1 SNS Topic
- Tên: `audit-security-alerts`
- Mã hóa bằng KMS: Dùng lại KMS key của dự án.
- Topic policy: Cho phép `events.amazonaws.com` gọi `Publish`, với điều kiện `aws:SourceArn` bị giới hạn ở 2 ARN của EventBridge rule trên.

### 6.2 EventBridge Rules + Targets
- Cả 2 rules nằm trên event bus `default`, trạng thái `state = "ENABLED"`.
- Target là ARN của SNS topic (không cần thiết lập Input Transformer; đẩy nguyên raw event).

### 6.3 Lambda
- Runtime: Python 3.12 (Phiên bản ổn định mới nhất).
- Kích hoạt (Trigger): Đăng ký nhận từ SNS (protocol = `lambda`).
- Timeout: 10s, Bộ nhớ: 128MB.
- Biến môi trường:
  - `SLACK_WEBHOOK_SSM_PARAM` = Tên của tham số SSM (không chứa trực tiếp mã bí mật).
- Logic xử lý:
  1. Phân giải SNS `Message` (JSON dạng chuỗi) thành EventBridge event.
  2. Rẽ nhánh theo `source`: `aws.cloudtrail` hoặc `aws.access-analyzer`.
  3. Đối với các sự kiện SG ingress hoặc bucket-policy, kiểm tra `requestParameters` xem có thực sự public không (0.0.0.0/0, `::/0`, hoặc `AllUsers`/`AuthenticatedUsers`). Bỏ qua nếu không public để tránh gây nhiễu (alert fatigue).
  4. Lấy URL webhook từ SSM (`with_decryption=True`), thực hiện lưu cache để tái sử dụng ở các lần chạy warm (warm invocations).
  5. Xây dựng tin nhắn Block Kit của Slack: hiển thị Mức độ (Severity), eventName, Tác nhân (`userIdentity.arn`), IP (`sourceIPAddress`), Account, Region, Timestamp.
  6. POST lên webhook URL; nếu response khác 2xx thì ghi log vào CloudWatch Logs.

### 6.4 IAM (Role thực thi cho Lambda)
- `AWSLambdaBasicExecutionRole` (để ghi log).
- `ssm:GetParameter` giới hạn theo ARN của tham số chứa webhook URL.
- `kms:Decrypt` giới hạn theo project KMS key (để giải mã SecureString).
- Không cần cấp quyền đọc CloudTrail/EC2/S3 — toàn bộ dữ liệu cần thiết đều nằm sẵn trong payload mà SNS gửi.

### 6.5 SSM Parameter
- Tên: `/security-alerts/slack-webhook-url`
- Kiểu: `SecureString`, mã hóa bằng project KMS.
- **KHÔNG THIẾT LẬP VALUE QUA TERRAFORM** để tránh lộ webhook URL ở state/plan — Tạo tham số với placeholder ảo kết hợp `lifecycle { ignore_changes = [value] }`. Webhook URL thực sẽ được thiết lập thủ công qua dòng lệnh CLI.

## 7. Variables (Các biến đầu vào module)
| Tên | Kiểu | Mô tả |
|---|---|---|
| `kms_key_arn` | string | KMS key hiện có của project |
| `event_bus_name` | string | mặc định = `"default"` |
| `slack_webhook_ssm_param_name` | string | mặc định = `/security-alerts/slack-webhook-url` |
| `sns_topic_name` | string | mặc định = `audit-security-alerts` |
| `lambda_runtime` | string | mặc định = `python3.12` |
| `tags` | map(string) | Các tag chuẩn của dự án |

## 8. Outputs (Giá trị đầu ra)
- `sns_topic_arn`
- `eventbridge_rule_a_arn`, `eventbridge_rule_b_arn`
- `lambda_function_name`
- `lambda_execution_role_arn`

## 9. Các bước thực hiện (Execution Order)
1. Khởi tạo cấu trúc thư mục module tại `infra/terraform/modules/security-slack-alerts`.
2. Viết `variables.tf` và `outputs.tf`.
3. Viết `sns.tf` (tạo topic và cấu hình policy).
4. Viết `iam.tf` (tạo role và gán các inline/managed policies).
5. Viết `lambda.tf` (tạo function, zip code bằng `archive_file`, quyền trigger).
6. Viết `lambda_src/handler.py` với logic Python.
7. Viết `eventbridge.tf` (tạo 2 rules + 2 targets, gắn pattern JSON chính xác).
8. Viết `main.tf` liên kết các resource và tóm tắt mô tả module.
9. Đăng ký module tại thư mục `infra/terraform` ở file `security-slack-alerts.tf`.
10. Kiểm tra cú pháp bằng `terraform validate` và `terraform plan`. Không được can thiệp vào tính năng cờ lỗi flagd (MANDATE-01).

## 10. Checklist Kiểm tra (Validation Checklist)
- [ ] Lệnh `terraform validate` chạy thành công.
- [ ] Cả 2 EventBridge rules đều có target trỏ vào ARN của SNS.
- [ ] SNS topic policy đã được siết chặt để chỉ nhận tin từ 2 EventBridge rules.
- [ ] Role của Lambda không thừa quyền (chỉ ghi log, đọc SSM và giải mã KMS).
- [ ] Có thể trigger thử (bằng cách xóa trail hoặc login root trên sandbox) và Slack nhận được tin trong vòng vài giây.
- [ ] Xác nhận không sinh thêm chi phí kéo log (ingestion) bằng cách kiểm tra việc không dùng CloudWatch Log Filters hay chức năng polling của Lambda.

## 11. Lưu ý về Chi phí
EventBridge + SNS + Lambda chỉ thu phí theo số lượng lần chạy (invocation) — không có chi phí cơ sở (baseline) khi rảnh rỗi, không tốn phí nạp log vào CloudWatch Logs, hoàn toàn thỏa mãn yêu cầu "chi phí gần mức $0" của hệ thống này.

## 12. Không thuộc phạm vi thực hiện (Out of Scope)
- Tạo CloudTrail trail (đã có sẵn).
- Nhân bản cảnh báo ra đa vùng (nếu cần sẽ tạo thêm các module instance sau này).
- Cảnh báo qua kênh khác ngoài Slack (SNS vẫn có thể mở rộng sau này, vd qua Email).

## 13. Kế hoạch Hoàn tác (Rollback Plan)
Trong trường hợp việc triển khai gặp sự cố không mong muốn (ví dụ: Lambda code lỗi, sai format tin nhắn Slack, gây báo động giả (spam) liên tục), bạn có thể tiến hành hoàn tác theo các bước an toàn sau:

**Phương án 1: Tạm ngắt khẩn cấp (Không cần Terraform)**
- Truy cập vào AWS Console -> Amazon EventBridge -> Rules.
- Tìm 2 rules: `security-alerts-cloudtrail` và `security-alerts-access-analyzer`.
- Chọn "Disable". Hành động này sẽ lập tức cắt đứt luồng sự kiện truyền xuống SNS và Lambda mà không làm hỏng cấu hình, cho phép bạn debug lỗi từ từ.

**Phương án 2: Gỡ bỏ hoàn toàn khỏi hạ tầng (Revert Terraform)**
1. Mở file root `infra/terraform/security-slack-alerts.tf`.
2. Xóa hoặc bình luận (comment-out) toàn bộ nội dung block gọi `module "security_slack_alerts"`.
3. Chạy lệnh `terraform plan` để đảm bảo Terraform sẽ thực hiện xóa bỏ module này (destroy - EventBridge rules, SNS, IAM Role, Lambda).
4. Chạy `terraform apply` để hoàn tất việc gỡ bỏ gọn gàng, hệ thống sẽ trở về trạng thái như trước khi triển khai mà không ảnh hưởng tới bất kỳ cấu trúc CloudTrail nào đang chạy.
