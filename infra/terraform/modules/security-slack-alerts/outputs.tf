output "sns_topic_arn" {
  description = "ARN of the SNS topic"
  value       = aws_sns_topic.alerts.arn
}

output "eventbridge_rule_readonly_arn" {
  description = "ARN of the EventBridge Rule for Read-Only Sensitive CloudTrail events"
  value       = aws_cloudwatch_event_rule.cloudtrail_alerts_readonly_sensitive.arn
}

output "eventbridge_rule_writeonly_arn" {
  description = "ARN of the EventBridge Rule for Write-Only Sensitive CloudTrail events"
  value       = aws_cloudwatch_event_rule.cloudtrail_alerts_writeonly_sensitive.arn
}

output "eventbridge_rule_b_arn" {
  description = "ARN of the EventBridge Rule for Access Analyzer findings"
  value       = aws_cloudwatch_event_rule.access_analyzer_alerts.arn
}

output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.slack_formatter.function_name
}

output "lambda_execution_role_arn" {
  description = "ARN of the Lambda execution role"
  value       = aws_iam_role.lambda_exec.arn
}

output "detection_metric_namespace" {
  description = "CloudWatch namespace containing MANDATE-11 detection latency metrics"
  value       = var.detection_metric_namespace
}

output "detection_latency_metric_names" {
  description = "Metric names for Lambda detection and Slack webhook acceptance latency"
  value = [
    "DetectionLatencySeconds",
    "NotificationLatencySeconds",
  ]
}

output "formatted_sns_topic_arn" {
  description = "ARN of the SNS topic that delivers human-readable formatted security alert emails"
  value       = aws_sns_topic.formatted_alerts.arn
}

output "alert_email_endpoint" {
  description = "Email address subscribed to receive human-readable security alerts"
  value       = var.alert_email_endpoint
}

output "anomaly_sns_topic_arn" {
  description = "ARN of the SNS topic for Mandate-11 H2 anomaly detection alarms"
  value       = aws_sns_topic.anomaly_alerts.arn
}

output "anomaly_alarm_rate_spike_arn" {
  description = "ARN of the static-threshold CloudWatch Alarm for GetSecretValue rate spike (>10 calls/60s)"
  value       = aws_cloudwatch_metric_alarm.get_secret_value_spike.arn
}

output "anomaly_alarm_anomaly_detection_arn" {
  description = "ARN of the ML Anomaly Detection CloudWatch Alarm for GetSecretValue frequency"
  value       = aws_cloudwatch_metric_alarm.get_secret_value_anomaly.arn
}

output "anomaly_alarm_pipeline_silence_arn" {
  description = "ARN of the dead-man's-switch CloudWatch Alarm for pipeline silence detection"
  value       = aws_cloudwatch_metric_alarm.pipeline_silence.arn
}

output "metric_filter_total_count_name" {
  description = "Name of the CloudWatch Metric Filter counting all GetSecretValue calls (MANDATE11_TTD)"
  value       = aws_cloudwatch_log_metric_filter.get_secret_value_total.name
}

output "metric_filter_expected_read_name" {
  description = "Name of the CloudWatch Metric Filter counting allowlisted MANDATE11_EXPECTED_READ events"
  value       = aws_cloudwatch_log_metric_filter.expected_read_count.name
}
