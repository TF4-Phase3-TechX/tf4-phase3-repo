resource "aws_sqs_queue" "lambda_dlq" {
  name                      = "audit-security-alerts-dlq"
  message_retention_seconds = 1209600 # 14 days
  kms_master_key_id         = var.kms_key_arn

  tags = var.tags
}

resource "aws_sqs_queue_policy" "lambda_dlq_policy" {
  queue_url = aws_sqs_queue.lambda_dlq.id

  policy = jsonencode({
    Version = "2012-10-17"
    Id      = "sqs-lambda-dlq-policy"
    Statement = [
      {
        Sid    = "AllowLambdaToSendToDLQ"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.lambda_dlq.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" : aws_lambda_function.slack_formatter.arn
          }
        }
      }
    ]
  })
}
