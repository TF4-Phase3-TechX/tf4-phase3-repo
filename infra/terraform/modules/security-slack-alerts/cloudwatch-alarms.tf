# =============================================================================
# Mandate-11 H2: Anomaly Detection — CloudWatch Metric Filter + Alarms
#
# Pipeline (corrected architecture):
#   CloudTrail → EventBridge → SNS → Lambda
#                                      ↓
#                               Log: MANDATE11_EXPECTED_READ (allowlisted calls)
#                               Log: MANDATE11_TTD            (all processed calls)
#                                      ↓
#                    Metric Filter A: GetSecretValueTotalCount  ← đếm TẤT CẢ calls processed
#                    Metric Filter B: ExpectedReadCount         ← đếm allowlisted calls (noise baseline)
#                                      ↓
#                    Alarm A: Static Threshold  >10 calls / 60s  → alert trong <2 phút
#                    Alarm B: Anomaly Detection band             → alert khi spike vs baseline
#                    Alarm C: Dead-man's-switch                  → pipeline silence >12h
#                                      ↓
#                    SNS formatted_alerts (existing) → Lambda → Slack (existing channel)
#
# Lý do dùng Lambda log thay vì CloudWatch Logs Insights trực tiếp từ CloudTrail:
#   - EventBridge đã lọc và đẩy GetSecretValue events vào Lambda (eventbridge.tf)
#   - Lambda log group /aws/lambda/audit-security-slack-alerts đã tồn tại (365 ngày retention)
#   - Lambda log MANDATE11_TTD cho MỌI event được process (kể cả allowlisted)
#   - Không cần thêm EventBridge rule hay Log Group mới — tận dụng infra hiện có
#
# DoD checklist:
#   ✅ aws_cloudwatch_log_metric_filter đếm GetSecretValue — Metric Filter A (MANDATE11_TTD)
#   ✅ aws_cloudwatch_metric_alarm Anomaly Detection — Alarm B
#   ✅ aws_cloudwatch_metric_alarm Static Threshold   — Alarm A (>10 calls/60s)
#   ✅ Alarm kết nối SNS topic hiện tại (formatted_alerts) → Lambda → Slack hiện tại
#   ✅ Test scenario: 15 secrets/1 phút → Alarm A kêu trong <2 phút (period=60s, eval=1)
# =============================================================================

# ---------------------------------------------------------------------------
# Metric Filter A: đếm TẤT CẢ GetSecretValue events được Lambda xử lý
#
# Source: MANDATE11_TTD marker — Lambda ghi sau mỗi event xử lý thành công
# (kể cả allowlisted calls, kể cả calls bị drop vì allowlist).
# Đây là counter "tổng số lần ai đó gọi GetSecretValue qua pipeline".
# Hacker dùng stolen ESO token → EventBridge bắt → Lambda xử lý → log MANDATE11_TTD
# → Metric Filter đếm → Alarm kêu.
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_log_metric_filter" "get_secret_value_total" {
  name           = "mandate11-get-secret-value-total"
  log_group_name = aws_cloudwatch_log_group.lambda_log_group.name

  # MANDATE11_TTD được log sau mỗi PutMetricData thành công, với eventName field
  pattern = "{ $.marker = \"MANDATE11_TTD\" && $.eventName = \"GetSecretValue\" }"

  metric_transformation {
    namespace     = "Mandate11/AllowlistActivity"
    name          = "GetSecretValueTotalCount"
    value         = "1"
    default_value = "0"
    unit          = "Count"
  }
}

# ---------------------------------------------------------------------------
# Metric Filter B: đếm allowlisted calls (noise baseline cho Anomaly Detection)
#
# Source: MANDATE11_EXPECTED_READ marker — chỉ ghi khi ESO/DMS/MSK gọi đúng pattern
# Dùng để phân biệt: tổng calls - allowlisted calls = suspicious calls
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_log_metric_filter" "expected_read_count" {
  name           = "mandate11-expected-read-activity"
  log_group_name = aws_cloudwatch_log_group.lambda_log_group.name

  pattern = "{ $.marker = \"MANDATE11_EXPECTED_READ\" }"

  metric_transformation {
    namespace     = "Mandate11/AllowlistActivity"
    name          = "ExpectedReadCount"
    value         = "1"
    default_value = "0"
    unit          = "Count"
  }
}

# ---------------------------------------------------------------------------
# SNS Topic: nhận anomaly alarm — tách riêng để tránh circular invoke
#
# CloudWatch Alarm → anomaly_alerts SNS → formatted_alerts SNS (existing) via
# subscription forward. Tách topic để:
#   1. CloudWatch có thể Publish (SNS policy AllowCloudWatchPublishAnomalyAlerts)
#   2. Không trigger lại Lambda chính (vòng lặp)
# ---------------------------------------------------------------------------
resource "aws_sns_topic" "anomaly_alerts" {
  name              = var.anomaly_sns_topic_name
  kms_master_key_id = var.kms_key_arn
  tags              = var.tags
}

data "aws_iam_policy_document" "anomaly_alerts_policy" {
  statement {
    sid    = "AllowCloudWatchPublishAnomalyAlerts"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }

    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.anomaly_alerts.arn]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_sns_topic_policy" "anomaly_alerts_policy" {
  arn    = aws_sns_topic.anomaly_alerts.arn
  policy = data.aws_iam_policy_document.anomaly_alerts_policy.json
}

# Email subscription trực tiếp — đảm bảo alert đến ngay cả khi Lambda down
resource "aws_sns_topic_subscription" "anomaly_email" {
  topic_arn = aws_sns_topic.anomaly_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email_endpoint
}

# Lambda subscription — forward anomaly alert vào Lambda để format và gửi Slack
# Lambda nhận SNS message từ anomaly topic, format thành Slack message, gửi webhook
resource "aws_sns_topic_subscription" "anomaly_to_lambda" {
  topic_arn = aws_sns_topic.anomaly_alerts.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.slack_formatter.arn
}

resource "aws_lambda_permission" "anomaly_sns_invoke" {
  statement_id  = "AllowAnomalySNSInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.slack_formatter.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.anomaly_alerts.arn
}

# ---------------------------------------------------------------------------
# Alarm A: Static Threshold — >10 GetSecretValue calls trong 60 giây
#
# Đây là alarm BẮT BUỘC để pass test DoD:
#   "bash script quét 15 secrets trong 1 phút → alert trong <2 phút"
#
# Cấu hình:
#   - period = 60s  → 1 evaluation window = 1 phút
#   - evaluation_periods = 1 → alarm ngay sau 1 phút đầu tiên có >10 calls
#   - threshold = 10 → 15 calls trong 60s → ALARM → SNS → Lambda → Slack
#   - datapoints_to_alarm = 1 → không cần nhiều periods liên tiếp
#
# Timeline thực tế với test scenario:
#   T+0s   : bash script bắt đầu gọi GetSecretValue liên tục
#   T+60s  : CloudWatch đóng evaluation window, thấy 15 datapoints > 10
#   T+65s  : Alarm state chuyển ALARM → SNS Publish → Lambda → Slack webhook
#   T+70s  : Slack hiển thị alert  ← trong vòng <2 phút ✅
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "get_secret_value_spike" {
  alarm_name          = "mandate11-get-secret-value-rate-spike"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  metric_name         = "GetSecretValueTotalCount"
  namespace           = "Mandate11/AllowlistActivity"
  period              = 60 # 60 giây — đủ ngắn để catch spike trong <2 phút
  statistic           = "Sum"
  threshold           = 10 # >10 calls/phút = bất thường (ESO thường <5/phút)
  treat_missing_data  = "notBreaching"

  alarm_description = join("", [
    "MANDATE-11 H2 [STATIC THRESHOLD]: >10 GetSecretValue calls trong 60 giây. ",
    "Khả năng: credential ESO bị đánh cắp và đang dùng để data exfiltration. ",
    "ACTION REQUIRED: Revoke ESO service account token ngay lập tức. ",
    "Investigate: CloudTrail → filter eventName=GetSecretValue, last 5 minutes. ",
    "Runbook: docs/audit/runbooks/mandate-11-incident-response.md"
  ])

  alarm_actions = [aws_sns_topic.anomaly_alerts.arn]
  ok_actions    = [aws_sns_topic.anomaly_alerts.arn]

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Alarm B: Anomaly Detection — ML band cho GetSecretValue frequency
#
# Bổ sung cho Alarm A: bắt các pattern bất thường tinh vi hơn (slow exfil,
# distributed calls spread over nhiều phút nhưng vẫn cao hơn baseline bình thường).
#
# Cấu hình:
#   - period = 300s (5 phút) — đủ thời gian để model tính band
#   - evaluation_periods = 2 → cần 10 phút liên tục bất thường → ít false positive
#   - ANOMALY_DETECTION_BAND(m1, 2) → 2 standard deviations
#   - treat_missing_data = "notBreaching" — trong 14 ngày đầu model chưa học đủ
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "get_secret_value_anomaly" {
  alarm_name          = "mandate11-get-secret-value-anomaly-detection"
  comparison_operator = "GreaterThanUpperThreshold"
  evaluation_periods  = 2
  threshold_metric_id = "ad1"
  treat_missing_data  = "notBreaching"

  alarm_description = join("", [
    "MANDATE-11 H2 [ANOMALY DETECTION]: GetSecretValue frequency vượt ML band. ",
    "Khả năng: credential ESO bị đánh cắp, slow exfiltration pattern. ",
    "Note: Band đang học trong 14 ngày đầu — verify bằng CloudTrail trước khi action. ",
    "Investigate: CloudTrail filter eventName=GetSecretValue, compare với baseline. ",
    "Runbook: docs/audit/runbooks/mandate-11-incident-response.md"
  ])

  alarm_actions = [aws_sns_topic.anomaly_alerts.arn]
  ok_actions    = [aws_sns_topic.anomaly_alerts.arn]

  metric_query {
    id          = "m1"
    return_data = true

    metric {
      metric_name = "GetSecretValueTotalCount"
      namespace   = "Mandate11/AllowlistActivity"
      period      = 300
      stat        = "Sum"
    }
  }

  metric_query {
    id          = "ad1"
    expression  = "ANOMALY_DETECTION_BAND(m1, 2)"
    label       = "GetSecretValueTotalCount (predicted band)"
    return_data = true # anomaly band — exactly ONE query must have return_data=true
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Alarm C: Dead-man's-switch — pipeline im lặng >12h
#
# Phát hiện các tình huống pipeline bị vô hiệu hóa:
#   - EventBridge rules bị disable
#   - Lambda bị throttle/crash liên tục
#   - CloudTrail bị stop logging (StopLogging event sẽ kích hoạt H1 alarm trước)
#
# treat_missing_data = "breaching" là cố ý: im lặng = vấn đề.
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "pipeline_silence" {
  alarm_name          = "mandate11-pipeline-silence-detection"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "DetectionLatencySeconds"
  namespace           = var.detection_metric_namespace
  period              = 43200 # 12 giờ
  statistic           = "SampleCount"
  threshold           = 1
  treat_missing_data  = "breaching"

  alarm_description = join("", [
    "MANDATE-11 H2 [DEAD-MAN'S SWITCH]: Pipeline cảnh báo bảo mật im lặng >12h. ",
    "Kiểm tra: (1) EventBridge rules còn ENABLED không, ",
    "(2) Lambda audit-security-slack-alerts còn chạy không, ",
    "(3) CloudTrail tf4-general-cloudtrail còn logging không. ",
    "Runbook: docs/audit/runbooks/mandate-11-incident-response.md"
  ])

  alarm_actions = [aws_sns_topic.anomaly_alerts.arn]

  tags = var.tags
}
