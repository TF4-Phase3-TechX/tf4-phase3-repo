output "sns_topic_arn" {
  description = "ARN of the SNS topic"
  value       = aws_sns_topic.alerts.arn
}

output "eventbridge_rule_global_arn" {
  description = "ARN of the EventBridge Rule for Global CloudTrail events"
  value       = aws_cloudwatch_event_rule.cloudtrail_alerts_global.arn
}

output "eventbridge_rule_regional_arn" {
  description = "ARN of the EventBridge Rule for Regional CloudTrail events"
  value       = aws_cloudwatch_event_rule.cloudtrail_alerts_regional.arn
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
