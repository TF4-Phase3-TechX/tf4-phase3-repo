# WARNING: The readonly rule depends on CloudTrail logging read-only events.
# If someone adds `field_selector { field = "readOnly", equals = ["false"] }` to cloudtrail.tf,
# this rule will silently stop receiving read-only events. Do not disable read-only events in CloudTrail!
resource "aws_cloudwatch_event_rule" "cloudtrail_alerts_readonly_sensitive" {
  name           = "security-alerts-cloudtrail-readonly-sensitive"
  description    = "Capture read-only sensitive events (e.g., Secrets Manager, SSM Parameter Store)"
  event_bus_name = var.event_bus_name
  state          = "ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS" # CRITICAL for read-only events

  event_pattern = jsonencode({
    source      = ["aws.secretsmanager", "aws.ssm"]
    detail-type = ["AWS API Call via CloudTrail"]
    detail = {
      errorCode = [{ "exists" = true }, { "exists" = false }]
      "$or" = [
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

resource "aws_cloudwatch_event_target" "sns_target_cloudtrail_readonly" {
  rule           = aws_cloudwatch_event_rule.cloudtrail_alerts_readonly_sensitive.name
  event_bus_name = var.event_bus_name
  target_id      = "SendToSNSReadOnly"
  arn            = aws_sns_topic.alerts.arn
}

resource "aws_cloudwatch_event_rule" "cloudtrail_alerts_writeonly_sensitive" {
  name           = "security-alerts-cloudtrail-writeonly-sensitive"
  description    = "Capture write-only sensitive events (IAM, EC2, S3, Config, EKS, CloudTrail)"
  event_bus_name = var.event_bus_name
  state          = "ENABLED"

  event_pattern = jsonencode({
    source      = ["aws.iam", "aws.signin", "aws.cloudtrail", "aws.ec2", "aws.s3", "aws.config", "aws.eks"]
    detail-type = ["AWS API Call via CloudTrail", "AWS Console Sign In via CloudTrail"]
    detail = {
      errorCode = [{ "exists" = true }, { "exists" = false }]
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
          eventSource = ["cloudtrail.amazonaws.com"]
          eventName   = ["StopLogging", "DeleteTrail", "UpdateTrail", "PutEventSelectors"]
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

resource "aws_cloudwatch_event_target" "sns_target_cloudtrail_writeonly" {
  rule           = aws_cloudwatch_event_rule.cloudtrail_alerts_writeonly_sensitive.name
  event_bus_name = var.event_bus_name
  target_id      = "SendToSNSWriteOnly"
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
