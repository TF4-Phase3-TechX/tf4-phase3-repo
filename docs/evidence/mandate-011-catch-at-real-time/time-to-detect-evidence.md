# Bằng chứng Time-to-Detect - MANDATE-11

## 1. Trạng thái

| Thuộc tính | Giá trị |
| --- | --- |
| Owner | Bá Huân - CDO07 Auditability |
| Luồng đo | CloudTrail -> EventBridge -> SNS -> Lambda -> Slack |
| CloudWatch namespace | `Mandate11/DetectionLatency` |
| Mục tiêu | p95 `NotificationLatencySeconds < 60 giây` |
| Số lần test tối thiểu | 3 lần chạy thật |
| Trạng thái hiện tại | **IMPLEMENTED - CÓ 3 MẪU SƠ BỘ, CHỜ CUSTOM METRIC RUNTIME EVIDENCE** |

Không đánh dấu tài liệu này `PASS` trước khi phiên bản Lambda mới được deploy và bảng ở mục 6 có ít nhất ba lần đo thực tế.

## 2. Định nghĩa phép đo

Lambda lấy thời điểm gốc từ `detail.eventTime` của CloudTrail. Chỉ khi payload không có trường này mới fallback sang trường `time` của EventBridge.

Hai metric được ghi với dimension `Pipeline=CloudTrailToSlack`:

| Metric | Công thức | Ý nghĩa |
| --- | --- | --- |
| `DetectionLatencySeconds` | `lambda_received_at - cloudtrail_event_time` | Thời gian từ hành động AWS đến khi Lambda bắt đầu xử lý cảnh báo |
| `NotificationLatencySeconds` | `slack_accepted_at - cloudtrail_event_time` | Thời gian từ hành động AWS đến khi Slack webhook trả HTTP 2xx |

`NotificationLatencySeconds` là metric dùng để nghiệm thu mục tiêu p95. HTTP 2xx chứng minh Slack đã chấp nhận webhook, không chứng minh một người đã đọc tin nhắn.

Logic triển khai nằm tại:

- [`handler.py`](../../../infra/terraform/modules/security-slack-alerts/lambda_src/handler.py)
- [`lambda.tf`](../../../infra/terraform/modules/security-slack-alerts/lambda.tf)
- [`iam.tf`](../../../infra/terraform/modules/security-slack-alerts/iam.tf)

## 3. Cách ghi metric

Lambda gửi tối đa hai datapoint bằng một lệnh `cloudwatch:PutMetricData` sau khi thử gửi Slack. IAM chỉ cho phép ghi vào namespace `Mandate11/DetectionLatency`.

Mỗi datapoint cũng có một structured log với marker `MANDATE11_TTD`:

```json
{
  "marker": "MANDATE11_TTD",
  "namespace": "Mandate11/DetectionLatency",
  "metricName": "NotificationLatencySeconds",
  "pipeline": "CloudTrailToSlack",
  "eventId": "11111111-2222-3333-4444-555555555555",
  "eventName": "CreateUser",
  "eventTime": "2026-07-18T01:00:00Z",
  "observedAt": "2026-07-18T01:00:12.450000+00:00",
  "latencySeconds": 12.45
}
```

Nếu publish metric lỗi, Lambda ghi lỗi nhưng không làm mất cảnh báo Slack. Nếu Slack không trả 2xx, Lambda chỉ ghi `DetectionLatencySeconds`, không tạo `NotificationLatencySeconds` giả và trả lỗi invocation để AWS retry việc gửi cảnh báo.

Các kiểm soát security/reliability đi kèm:

- IAM chỉ cho phép `cloudwatch:PutMetricData` trong namespace của Mandate 11; `Resource = "*"` là yêu cầu của API và được thu hẹp bằng condition `cloudwatch:namespace`.
- Webhook lấy từ SSM Parameter Store, chỉ chấp nhận HTTPS và hostname thuộc allowlist mặc định `hooks.slack.com`.
- Lambda không ghi toàn bộ SNS/CloudTrail payload vào log; structured log chỉ chứa metadata cần cho đối chiếu TTD.
- Allowlist giảm nhiễu phải khớp actor, API và resource; role automation không được bypass các critical event.
- Event ID và pipeline không được dùng làm CloudWatch dimension để tránh cardinality cao và chi phí metric tăng ngoài kiểm soát.

## 4. Kịch bản test an toàn

Ưu tiên sự kiện `CreateUser` với IAM user tạm không có policy. Không dùng `StopLogging` trên trail chính chỉ để đo latency.

Chạy ba lần, mỗi lần dùng tên khác nhau và cách nhau ít nhất 60 giây để dễ đối chiếu datapoint:

```powershell
$Run = Get-Date -Format "yyyyMMddHHmmss"
$User = "mandate11-ttd-$Run"

aws iam create-user `
  --user-name $User `
  --profile <mentor-or-test-profile>

# Chỉ cleanup sau khi cảnh báo và metric đã xuất hiện.
aws iam delete-user `
  --user-name $User `
  --profile <mentor-or-test-profile>
```

Với mỗi lần chạy, lưu:

1. CloudTrail `eventTime`, `eventID`, actor và source IP của `CreateUser`.
2. Tin nhắn Slack có actor, event, source IP, event time và detection latency.
3. Structured logs của cả hai metric.
4. Datapoint `NotificationLatencySeconds` trong CloudWatch.

## 5. Query tái kiểm tra

### 5.1. Xem từng datapoint

Thay cửa sổ UTC bằng thời gian test thực tế:

```powershell
aws cloudwatch get-metric-statistics `
  --namespace "Mandate11/DetectionLatency" `
  --metric-name "NotificationLatencySeconds" `
  --dimensions Name=Pipeline,Value=CloudTrailToSlack `
  --start-time "2026-07-18T00:00:00Z" `
  --end-time "2026-07-18T02:00:00Z" `
  --period 60 `
  --statistics Minimum Maximum Average `
  --region us-east-1 `
  --profile cdo07-tf4-auditreadonly
```

### 5.2. Xem p95

Chọn `period` bao phủ chung cửa sổ test để nhận một giá trị p95 tổng hợp. Ví dụ các test nằm trong cùng một giờ:

```powershell
aws cloudwatch get-metric-statistics `
  --namespace "Mandate11/DetectionLatency" `
  --metric-name "NotificationLatencySeconds" `
  --dimensions Name=Pipeline,Value=CloudTrailToSlack `
  --start-time "2026-07-18T00:00:00Z" `
  --end-time "2026-07-18T01:00:00Z" `
  --period 3600 `
  --extended-statistics p95 `
  --region us-east-1 `
  --profile cdo07-tf4-auditreadonly
```

### 5.3. Đối chiếu structured logs

CloudWatch Logs Insights trên log group `/aws/lambda/audit-security-slack-alerts`:

```text
fields @timestamp, @message
| filter @message like /MANDATE11_TTD/
| filter @message like /NotificationLatencySeconds/
| sort @timestamp asc
| limit 50
```

## 6. Kết quả đo thực tế

### 6.1. Số đo sơ bộ từ Slack ngày 18/07/2026

Các số dưới đây đã có trên `main` trước khi bổ sung custom metric. Chúng chứng minh luồng cảnh báo đã chạy thật, nhưng chưa đủ để nghiệm thu metric mới vì còn thiếu Event ID, timestamp đối chiếu và datapoint CloudWatch.

| Run | Actor | Event | Latency hiển thị trên Slack | Severity | Trạng thái evidence |
| ---: | --- | --- | ---: | --- | --- |
| 1 | `nghia.bui` | `StopLogging` | 2.49 s | CRITICAL | Sơ bộ, cần bổ sung ảnh và Event ID |
| 2 | `nghia.bui` | `CreateUser` | 2.15 s | HIGH | Sơ bộ, cần bổ sung ảnh và Event ID |
| 3 | `nghia.bui` | `GetParameter` | 2.85 s | HIGH | Sơ bộ, cần bổ sung ảnh và Event ID |

**p95 sơ bộ với 3 mẫu:** `2.85 giây` (nearest-rank). Kết quả này chưa thay thế bảng nghiệm thu custom metric bên dưới.

### 6.2. Nghiệm thu custom metric

Không điền số ước lượng hoặc số từ unit test vào bảng này.

| Run | Event ID / Event name | CloudTrail eventTime (UTC) | Lambda nhận (UTC) | Slack chấp nhận (UTC) | Detection (s) | Notification (s) | Evidence | Kết quả |
| ---: | --- | --- | --- | --- | ---: | ---: | --- | --- |
| 1 | PENDING | PENDING | PENDING | PENDING | - | - | PENDING | PENDING |
| 2 | PENDING | PENDING | PENDING | PENDING | - | - | PENDING | PENDING |
| 3 | PENDING | PENDING | PENDING | PENDING | - | - | PENDING | PENDING |

**p95 thực tế:** `PENDING`

**Đánh giá so với mục tiêu p95 < 60 giây:** `PENDING`

## 7. Acceptance Criteria

- [x] Lambda tính latency từ CloudTrail `detail.eventTime`.
- [x] Lambda publish custom metrics trong namespace `Mandate11/DetectionLatency`.
- [x] Có metric riêng cho thời điểm Lambda phát hiện và thời điểm Slack webhook chấp nhận.
- [x] IAM `PutMetricData` bị giới hạn theo namespace.
- [x] Có query xem datapoint, p95 và structured logs.
- [ ] Phiên bản Lambda mới đã deploy thành công.
- [x] Có ít nhất ba số đo thực tế sơ bộ từ luồng Slack hiện hữu.
- [ ] Có ít nhất ba lần chạy test sau khi deploy custom metric.
- [ ] Có đủ CloudTrail, CloudWatch và Slack evidence cho từng lần chạy.
- [ ] Đã tính p95 và kết luận `PASS` hoặc `FAIL` so với ngưỡng 60 giây.

## 8. Chi phí và giảm nhiễu

Đối với luồng CloudTrail, thiết kế tạo hai metric time series cố định. Luồng Access Analyzer dùng cùng hai metric name nhưng có dimension `Pipeline=AccessAnalyzerToSlack` riêng để không làm nhiễu p95 của CloudTrail. Actor, IP và event ID chỉ nằm trong log/evidence, không được dùng làm dimension, nhờ đó cardinality và chi phí không tăng theo số người dùng. Metric chỉ được tạo cho sự kiện vượt qua logic allowlist/filter và thực sự đi vào luồng cảnh báo.
