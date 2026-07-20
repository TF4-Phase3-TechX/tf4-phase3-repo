# Runbook: Cách tính Time-to-Detect (MANDATE-11)

Tài liệu này mô tả thiết kế đo thời gian phát hiện của luồng cảnh báo bảo mật. Tài liệu không chứa kết quả chạy thật; người phụ trách evidence ghi Event ID, ảnh Slack và datapoint CloudWatch vào [time-to-detect-evidence.md](../../evidence/mandate-011-catch-at-real-time/time-to-detect-evidence.md).

## 1. Phạm vi

- Luồng đo: CloudTrail -> EventBridge -> SNS -> Lambda -> Slack.
- CloudWatch namespace: `Mandate11/DetectionLatency`.
- Mục tiêu nghiệm thu: p95 `NotificationLatencySeconds < 60 giây`.
- Owner phần tính toán và custom metric: Bá Huân - CDO07.
- Kết quả `PASS/FAIL` chỉ do evidence runtime quyết định sau khi deploy.

## 2. Mốc thời gian

Lambda dùng ba mốc UTC:

| Mốc | Nguồn | Ý nghĩa |
| --- | --- | --- |
| `cloudtrail_event_time` | `detail.eventTime` | Thời điểm hành động AWS thực sự xảy ra |
| `lambda_received_at` | `datetime.now(timezone.utc)` | Thời điểm Lambda bắt đầu xử lý SNS record |
| `slack_accepted_at` | `datetime.now(timezone.utc)` sau HTTP 2xx | Thời điểm Slack webhook chấp nhận thông báo |

Nếu payload không có `detail.eventTime`, handler mới fallback sang `time` của EventBridge. Không dùng thời điểm Lambda làm mốc bắt đầu vì cách đó bỏ qua độ trễ CloudTrail, EventBridge và SNS.

## 3. Công thức

```text
DetectionLatencySeconds
= lambda_received_at - cloudtrail_event_time

NotificationLatencySeconds
= slack_accepted_at - cloudtrail_event_time
```

`DetectionLatencySeconds` cho biết pipeline mất bao lâu để đưa sự kiện đến Lambda. `NotificationLatencySeconds` đo toàn bộ đường đi đến khi Slack trả HTTP 2xx và là metric dùng để tính p95 nghiệm thu.

HTTP 2xx chỉ chứng minh Slack đã nhận webhook, không chứng minh một người đã đọc tin nhắn.

## 4. Cách publish metric

Logic nằm tại:

- [`handler.py`](../../../infra/terraform/modules/security-slack-alerts/lambda_src/handler.py)
- [`lambda.tf`](../../../infra/terraform/modules/security-slack-alerts/lambda.tf)
- [`iam.tf`](../../../infra/terraform/modules/security-slack-alerts/iam.tf)

Hai metric sử dụng dimension cố định:

```text
Pipeline=CloudTrailToSlack
```

Access Analyzer dùng `Pipeline=AccessAnalyzerToSlack` riêng. Actor, source IP và Event ID chỉ được ghi trong log/evidence, không dùng làm dimension để tránh cardinality và chi phí tăng theo số sự kiện.

Lambda publish metric sau khi thử gửi Slack:

- Slack trả HTTP 2xx: publish cả Detection và Notification latency.
- Slack lỗi: chỉ publish Detection latency, không tạo Notification latency giả và trả lỗi để AWS retry.
- CloudWatch lỗi: ghi lỗi nhưng không làm mất cảnh báo Slack đã gửi thành công.

Structured log dùng marker `MANDATE11_TTD` để đối chiếu Event ID với datapoint.

## 5. Kiểm soát security

- IAM chỉ cho phép `cloudwatch:PutMetricData` trong namespace `Mandate11/DetectionLatency` bằng condition `cloudwatch:namespace`.
- Webhook được đọc từ SSM Parameter Store và chỉ chấp nhận HTTPS tới hostname trong allowlist, mặc định là `hooks.slack.com`.
- Lambda không ghi toàn bộ SNS hoặc CloudTrail payload vào CloudWatch Logs.
- Allowlist giảm nhiễu phải khớp actor, API và resource; role automation không được bypass critical event.
- Metric không chứa secret, request payload hoặc thông tin định danh dưới dạng dimension.

## 6. Query CloudWatch

### Xem từng datapoint

Thay cửa sổ UTC bằng thời gian chạy test:

```powershell
aws cloudwatch get-metric-statistics `
  --namespace "Mandate11/DetectionLatency" `
  --metric-name "NotificationLatencySeconds" `
  --dimensions Name=Pipeline,Value=CloudTrailToSlack `
  --start-time "<START_UTC>" `
  --end-time "<END_UTC>" `
  --period 60 `
  --statistics Minimum Maximum Average `
  --region us-east-1 `
  --profile <AUDIT_READONLY_PROFILE>
```

### Tính p95

```powershell
aws cloudwatch get-metric-statistics `
  --namespace "Mandate11/DetectionLatency" `
  --metric-name "NotificationLatencySeconds" `
  --dimensions Name=Pipeline,Value=CloudTrailToSlack `
  --start-time "<START_UTC>" `
  --end-time "<END_UTC>" `
  --period 3600 `
  --extended-statistics p95 `
  --region us-east-1 `
  --profile <AUDIT_READONLY_PROFILE>
```

### Đối chiếu structured log

Chạy Logs Insights trên log group `/aws/lambda/audit-security-slack-alerts`:

```text
fields @timestamp, @message
| filter @message like /MANDATE11_TTD/
| sort @timestamp asc
| limit 50
```

## 7. Bàn giao cho người thu evidence

Sau khi Lambda mới được deploy:

1. Chạy ít nhất ba sự kiện test an toàn, ưu tiên `CreateUser` với IAM user tạm không có policy.
2. Với mỗi lần chạy, lưu CloudTrail Event ID, `eventTime`, actor, source IP và ảnh Slack.
3. Lấy `DetectionLatencySeconds` và `NotificationLatencySeconds` tương ứng từ CloudWatch.
4. Tính p95 và đối chiếu với ngưỡng 60 giây.
5. Ghi toàn bộ kết quả vào [time-to-detect-evidence.md](../../evidence/mandate-011-catch-at-real-time/time-to-detect-evidence.md).

Không ghi số từ unit test hoặc số ước lượng vào evidence runtime.

## 8. Kiểm tra local

```powershell
python -m unittest discover `
  -s infra/terraform/modules/security-slack-alerts/tests `
  -p "test_*.py" -v

python -m py_compile `
  infra/terraform/modules/security-slack-alerts/lambda_src/handler.py `
  infra/terraform/modules/security-slack-alerts/tests/test_handler.py

terraform -chdir=infra/terraform fmt -check -recursive
terraform -chdir=infra/terraform validate
```

Phần tính toán hoàn thành khi code, IAM, query và unit test đều hợp lệ. MANDATE-11 chỉ đạt khi file evidence có ít nhất ba lần đo runtime và kết luận p95 `PASS` hoặc `FAIL`.
