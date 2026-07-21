
resource "aws_iam_role" "redriver_exec" {
  name               = "SecuritySlackAlertsRedriverRole"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "redriver_basic_execution" {
  role       = aws_iam_role.redriver_exec.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "redriver_policy_doc" {
  statement {
    sid       = "AllowReadDLQ"
    effect    = "Allow"
    actions   = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes"
    ]
    resources = [aws_sqs_queue.lambda_dlq.arn]
  }

  statement {
    sid       = "AllowInvokeMainLambda"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.slack_formatter.arn]
  }
}

resource "aws_iam_role_policy" "redriver_policy" {
  name   = "SecuritySlackAlertsRedriverPolicy"
  role   = aws_iam_role.redriver_exec.id
  policy = data.aws_iam_policy_document.redriver_policy_doc.json
}
