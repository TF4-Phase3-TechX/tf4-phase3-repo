# =============================================================================
# Mandate-11 H2: Anomaly Detection — CloudWatch Metric Filter + Alarms
#
# Pipeline:
#   Lambda log → Metric Filter (MANDATE11_EXPECTED_READ)
#              → Custom Metric (Mandate11/AllowlistActivity)
#              → Anomaly Detection Alarm (ML band)
#              → SNS anomaly topic → Slack
#
# Design notes:
#   - Metric Filter đếm mỗi lần ESO gọi GetSecretValue hợp lệ được allowlist.
#     Bất kỳ spike bất thường nào (token bị đánh cắp, replay attack) sẽ vượt
#     band ML → alarm kêu.
#   - Dead-man's-switch alarm bắt trường hợp pipeline im lặng >12h (EventBridge
#     bị disable hoặc Lambda crash liên tục).
#   - SNS topic anomaly tách riêng khỏi topic cảnh báo chính để tránh loop.
#   - Alarm dùng treat_missing_data = "notBreaching" trong 7-14 ngày đầu khi
#     band đang học; sau khi ổn định có thể đổi sang "breaching".
# =============================================================================

# ---------------------------------------------------------------------------
# Metric Filter: đếm MANDATE11_EXPECTED_READ từ Lambda log
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_log_metric_filter" "expected_read_count" {
  name           = "mandate11-expected-read-activity"
  log_group_name = aws_cloudwatch_log_group.lambda_log_group.name

  # JSON structured log: { "marker": "MANDATE11_EXPECTED_READ", "eventName": "...", "actor": "..." }
  pattern = "{ $.marker = \"MANDATE11_EXPECTED_READ\" }"

  metric_transformation {
    namespace = "Mandate11/AllowlistActivity"
    name      = "ExpectedReadCount"
    value     = "1"
    unit      = "Count"
    # NOTE: dimensions and default_value are mutually exclusive in AWS API.
    # InvalidParameterException: dimensions and default value are mutually exclusive.
    # treat_missing_data = "notBreaching" on the alarm handles zero-data periods.
  }
}

# ---------------------------------------------------------------------------
# SNS Topic: nhận anomaly alarm — tách riêng khỏi audit-security-alerts
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

# Email subscription cho anomaly topic (dùng chung email với H1)
resource "aws_sns_topic_subscription" "anomaly_email" {
  topic_arn = aws_sns_topic.anomaly_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email_endpoint
}

# ---------------------------------------------------------------------------
# Anomaly Detection Alarm: GetSecretValue bởi external-secrets
#
# Alarm kêu khi tần suất ESO gọi GetSecretValue vượt band ML dự đoán
# (comparison_operator = GreaterThanUpperThreshold).
#
# Cấu hình band:
#   - anomaly_band(m1, 2) → band 2 standard deviations (khuyến nghị AWS default)
#   - evaluation_periods = 3 × period 5 phút → cần bất thường liên tục 15 phút
#     để tránh spike ngắn hạn gây false positive
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "eso_read_anomaly" {
  alarm_name          = "mandate11-eso-read-frequency-anomaly"
  comparison_operator = "GreaterThanUpperThreshold"
  evaluation_periods  = 3
  threshold_metric_id = "ad1"
  treat_missing_data  = "notBreaching"

  alarm_description = join("", [
    "MANDATE-11 H2: external-secrets đọc secret với tần suất bất thường. ",
    "Khả năng: token ESO bị đánh cắp và dùng bên ngoài cluster, hoặc replay attack. ",
    "Investigate: CloudTrail filter eventName=GetSecretValue, ",
    "userIdentity.sessionContext.sessionIssuer.userName=external-secrets-techx-tf4-cluster"
  ])

  alarm_actions = [aws_sns_topic.anomaly_alerts.arn]
  ok_actions    = [aws_sns_topic.anomaly_alerts.arn]

  # m1: metric thực tế từ Metric Filter (tất cả actor, chỉ filter EventName=GetSecretValue)
  metric_query {
    id          = "m1"
    return_data = true

    metric {
      metric_name = "ExpectedReadCount"
      namespace   = "Mandate11/AllowlistActivity"
      period      = 300 # 5 phút — khớp với chu kỳ ESO sync secrets
      stat        = "Sum"
    }
  }

  # ad1: band ML dự đoán — 2 standard deviations
  metric_query {
    id          = "ad1"
    expression  = "ANOMALY_DETECTION_BAND(m1, 2)"
    label       = "ExpectedReadCount (predicted band)"
    return_data = true
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Dead-man's-switch Alarm: phát hiện pipeline im lặng
#
# Nếu không có bất kỳ DetectionLatencySeconds nào trong 12h:
#   - EventBridge rules bị disable
#   - Lambda bị throttle/crash liên tục
#   - CloudTrail bị stop logging
# → Alarm kêu để on-call kiểm tra ngay.
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
    "MANDATE-11 H2: Pipeline cảnh báo bảo mật im lặng >12h. ",
    "Kiểm tra: (1) EventBridge rules còn ENABLED không, ",
    "(2) Lambda audit-security-slack-alerts còn chạy không, ",
    "(3) CloudTrail tf4-general-cloudtrail còn logging không. ",
    "Runbook: docs/audit/runbooks/mandate-11-incident-response.md"
  ])

  alarm_actions = [aws_sns_topic.anomaly_alerts.arn]

  tags = var.tags
}
