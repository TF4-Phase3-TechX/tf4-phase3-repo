
resource "aws_cloudwatch_event_rule" "redriver_schedule" {
  name                = "audit-security-alerts-redriver-schedule"
  description         = "Triggers the DLQ Redriver Lambda every 10 minutes"
  schedule_expression = "rate(10 minutes)"
  tags                = var.tags
}

resource "aws_cloudwatch_event_target" "redriver_target" {
  rule      = aws_cloudwatch_event_rule.redriver_schedule.name
  target_id = "RedriverLambda"
  arn       = aws_lambda_function.redriver.arn
}

resource "aws_lambda_permission" "allow_eventbridge_to_call_redriver" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.redriver.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.redriver_schedule.arn
}
