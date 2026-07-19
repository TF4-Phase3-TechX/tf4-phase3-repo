data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda_src"
  output_path = "${path.module}/lambda_function.zip"
}

resource "aws_cloudwatch_log_group" "lambda_log_group" {
  name              = "/aws/lambda/audit-security-slack-alerts"
  retention_in_days = 365
  tags              = var.tags
}

resource "aws_lambda_function" "slack_formatter" {
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  function_name    = "audit-security-slack-alerts"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "handler.lambda_handler"
  runtime          = var.lambda_runtime
  timeout          = 10
  memory_size      = 128

  environment {
    variables = {
      SLACK_WEBHOOK_SSM_PARAM          = var.slack_webhook_ssm_param_name
      SLACK_WEBHOOK_ALLOWED_HOSTS      = join(",", var.slack_webhook_allowed_hosts)
      DETECTION_METRIC_NAMESPACE       = var.detection_metric_namespace
      DETECTION_LATENCY_TARGET_SECONDS = tostring(var.detection_latency_target_seconds)
    }
  }

  tags = var.tags

  depends_on = [aws_cloudwatch_log_group.lambda_log_group]
}

resource "aws_lambda_permission" "sns_invoke" {
  statement_id  = "AllowExecutionFromSNS"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.slack_formatter.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.alerts.arn
}

resource "aws_sns_topic_subscription" "lambda_subscription" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.slack_formatter.arn
}
