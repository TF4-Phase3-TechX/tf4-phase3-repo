resource "aws_cloudwatch_event_rule" "cloudtrail_alerts_global" {
  name           = "security-alerts-cloudtrail-global"
  description    = "Capture IAM, Secrets Manager, and SSM sensitive events"
  event_bus_name = var.event_bus_name
  state          = "ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS"

  event_pattern = jsonencode({
    source      = ["aws.cloudtrail"]
    detail-type = ["AWS API Call via CloudTrail"]
    detail = {
      "$or" = [
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
          eventSource = ["signin.amazonaws.com"]
          eventName   = ["ConsoleLogin"]
          userIdentity = {
            type = ["Root"]
          }
        },
        {
          eventSource = ["secretsmanager.amazonaws.com"]
          eventName   = ["GetSecretValue"]
        },
        {
          eventSource = ["ssm.amazonaws.com"]
          eventName   = ["GetParameter", "GetParameters", "GetParametersByPath"]
        }
      ]
    }
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "sns_target_cloudtrail_global" {
  rule           = aws_cloudwatch_event_rule.cloudtrail_alerts_global.name
  event_bus_name = var.event_bus_name
  target_id      = "SendToSNSGlobal"
  arn            = aws_sns_topic.alerts.arn
}

resource "aws_cloudwatch_event_rule" "cloudtrail_alerts_regional" {
  name           = "security-alerts-cloudtrail-regional"
  description    = "Capture EC2, S3, Config, EKS sensitive events"
  event_bus_name = var.event_bus_name
  state          = "ENABLED"

  event_pattern = jsonencode({
    source      = ["aws.cloudtrail"]
    detail-type = ["AWS API Call via CloudTrail"]
    detail = {
      "$or" = [
        {
          eventSource = ["cloudtrail.amazonaws.com"]
          eventName   = ["StopLogging", "DeleteTrail"]
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
          eventSource = ["eks.amazonaws.com"]
          eventName = [
            "CreateAccessEntry",
            "AssociateAccessPolicy"
          ]
        }
      ]
    }
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "sns_target_cloudtrail_regional" {
  rule           = aws_cloudwatch_event_rule.cloudtrail_alerts_regional.name
  event_bus_name = var.event_bus_name
  target_id      = "SendToSNSRegional"
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
