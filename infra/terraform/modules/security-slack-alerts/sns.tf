resource "aws_sns_topic" "alerts" {
  name              = var.sns_topic_name
  kms_master_key_id = var.kms_key_arn
  tags              = var.tags
}

resource "aws_sns_topic_policy" "alerts_policy" {
  arn    = aws_sns_topic.alerts.arn
  policy = data.aws_iam_policy_document.sns_topic_policy.json
}

data "aws_iam_policy_document" "sns_topic_policy" {
  statement {
    sid    = "AllowEventBridgePublish"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }

    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values = [
        aws_cloudwatch_event_rule.cloudtrail_alerts_readonly_sensitive.arn,
        aws_cloudwatch_event_rule.cloudtrail_alerts_writeonly_sensitive.arn,
        aws_cloudwatch_event_rule.access_analyzer_alerts.arn
      ]
    }
  }
}

# ---------------------------------------------------------------------------
# Formatted alert topic — Lambda publishes human-readable messages here.
# Email subscribers receive plain-text alerts instead of raw CloudTrail JSON.
# ---------------------------------------------------------------------------
resource "aws_sns_topic" "formatted_alerts" {
  name              = var.formatted_sns_topic_name
  kms_master_key_id = var.kms_key_arn
  tags              = var.tags
}

data "aws_iam_policy_document" "formatted_alerts_policy" {
  statement {
    sid    = "AllowLambdaPublishFormattedAlerts"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = [aws_iam_role.lambda_exec.arn]
    }

    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.formatted_alerts.arn]
  }
}

resource "aws_sns_topic_policy" "formatted_alerts_policy" {
  arn    = aws_sns_topic.formatted_alerts.arn
  policy = data.aws_iam_policy_document.formatted_alerts_policy.json
}

resource "aws_sns_topic_subscription" "email_subscription" {
  topic_arn = aws_sns_topic.formatted_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email_endpoint
}
