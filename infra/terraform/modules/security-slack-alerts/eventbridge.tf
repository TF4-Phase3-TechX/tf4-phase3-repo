resource "aws_cloudwatch_event_rule" "cloudtrail_alerts" {
  name           = "security-alerts-cloudtrail"
  description    = "Capture sensitive CloudTrail management events for security alerting"
  event_bus_name = var.event_bus_name
  state          = "ENABLED"

  event_pattern = jsonencode({
    detail-type = ["AWS API Call via CloudTrail"]
    detail = {
      "$or" = [
        {
          eventSource = ["cloudtrail.amazonaws.com"]
          eventName   = ["StopLogging", "DeleteTrail"]
        },
        {
          eventSource = ["signin.amazonaws.com"]
          eventName   = ["ConsoleLogin"]
          userIdentity = {
            type = ["Root"]
          }
        },
        {
          eventSource = ["ec2.amazonaws.com"]
          eventName   = ["AuthorizeSecurityGroupIngress"]
        },
        {
          eventSource = ["s3.amazonaws.com"]
          eventName   = ["PutBucketPolicy", "PutBucketAcl"]
        },
        {
          eventSource = ["config.amazonaws.com"]
          eventName   = ["DeleteConfigurationRecorder"]
        },
        {
          eventSource = ["iam.amazonaws.com"]
          eventName = [
            "CreateAccessKey",
            "AttachRolePolicy",
            "PutRolePolicy",
            "CreateUser",
            "CreateRole",
            "UpdateAssumeRolePolicy"
          ]
        },
        {
          eventSource = ["eks.amazonaws.com"]
          eventName = [
            "CreateAccessEntry",
            "AssociateAccessPolicy"
          ]
        },
        {
          eventSource = ["secretsmanager.amazonaws.com"]
          eventName   = ["GetSecretValue"]
        }
      ]
    }
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "sns_target_cloudtrail" {
  rule           = aws_cloudwatch_event_rule.cloudtrail_alerts.name
  event_bus_name = var.event_bus_name
  target_id      = "SendToSNS"
  arn            = aws_sns_topic.alerts.arn
}

resource "aws_cloudwatch_event_rule" "access_analyzer_alerts" {
  name           = "security-alerts-access-analyzer"
  description    = "Capture Access Analyzer findings for security alerting"
  event_bus_name = var.event_bus_name
  state          = "ENABLED"

  event_pattern = jsonencode({
    source      = ["aws.access-analyzer"]
    detail-type = ["Access Analyzer Finding"]
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "sns_target_access_analyzer" {
  rule           = aws_cloudwatch_event_rule.access_analyzer_alerts.name
  event_bus_name = var.event_bus_name
  target_id      = "SendToSNS"
  arn            = aws_sns_topic.alerts.arn
}
