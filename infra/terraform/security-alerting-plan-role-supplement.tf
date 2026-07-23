# Supplement permissions for tf4-github-actions-plan so Terraform plan can
# refresh state for the security-alerting module resources (SQS DLQ, SNS topics).
#
# The plan role's base policy lives in infra/bootstrap/github-actions-oidc.tf.
# Adding read-only permissions here avoids a bootstrap apply dependency while
# still keeping the change in version control and under Terraform management.
# The apply role (PowerUserAccess + IAMFullAccess) can create this inline policy.

data "aws_iam_policy_document" "plan_role_security_alerting_read" {
  statement {
    sid    = "ReadSecurityAlertingSqsState"
    effect = "Allow"

    actions = [
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
      "sqs:ListQueueTags",
    ]

    resources = [
      "arn:aws:sqs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:audit-security-alerts-dlq",
    ]
  }

  statement {
    sid    = "ReadSecurityAlertingSnsState"
    effect = "Allow"

    actions = [
      "sns:GetTopicAttributes",
      "sns:ListTagsForResource",
      "sns:ListSubscriptionsByTopic",
    ]

    resources = [
      "arn:aws:sns:${var.aws_region}:${data.aws_caller_identity.current.account_id}:audit-security-alerts",
      "arn:aws:sns:${var.aws_region}:${data.aws_caller_identity.current.account_id}:audit-security-alerts-formatted",
    ]
  }

  statement {
    sid    = "ReadSecurityAlertingCloudWatchState"
    effect = "Allow"

    actions = [
      "cloudwatch:ListTagsForResource",
      "cloudwatch:DescribeAlarms",
    ]

    resources = [
      "arn:aws:cloudwatch:${var.aws_region}:${data.aws_caller_identity.current.account_id}:alarm:*",
    ]
  }
}

resource "aws_iam_role_policy" "plan_role_security_alerting_read" {
  name   = "SecurityAlertingReadForPlan"
  role   = "tf4-github-actions-plan"
  policy = data.aws_iam_policy_document.plan_role_security_alerting_read.json
}
