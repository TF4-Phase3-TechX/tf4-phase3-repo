# Owner: CDO07 Audit
# Ref: AUDIT-010 - Auto-remediate CloudTrail StopLogging via EventBridge + SSM Automation

locals {
  cloudtrail_auto_remediation_document_name = "tf4-restore-cloudtrail-logging"
  cloudtrail_auto_remediation_rule_name     = "tf4-cloudtrail-stoplogging-auto-remediation"
  cloudtrail_automation_definition_arn      = "arn:${data.aws_partition.current.partition}:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:automation-definition/${local.cloudtrail_auto_remediation_document_name}"
}

resource "aws_iam_role" "cloudtrail_auto_remediation_automation" {
  name = "tf4-cloudtrail-auto-remediation-automation-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "AllowSSMAutomationAssume"
      Effect = "Allow"
      Principal = {
        Service = "ssm.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "cloudtrail_auto_remediation_automation" {
  name = "tf4-cloudtrail-start-logging-policy"
  role = aws_iam_role.cloudtrail_auto_remediation_automation.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowRestartManagedTrail"
        Effect = "Allow"
        Action = [
          "cloudtrail:StartLogging"
        ]
        Resource = "arn:${data.aws_partition.current.partition}:cloudtrail:${var.aws_region}:${data.aws_caller_identity.current.account_id}:trail/${aws_cloudtrail.main.name}"
      }
    ]
  })
}

resource "aws_ssm_document" "cloudtrail_auto_remediation" {
  name            = local.cloudtrail_auto_remediation_document_name
  document_type   = "Automation"
  document_format = "JSON"

  content = jsonencode({
    schemaVersion = "0.3"
    description   = "Re-enable logging for the managed TF4 CloudTrail trail after StopLogging is detected."
    assumeRole    = "{{ AutomationAssumeRole }}"
    parameters = {
      TrailName = {
        type        = "String"
        description = "CloudTrail trail name to re-enable."
        default     = aws_cloudtrail.main.name
      }
      AutomationAssumeRole = {
        type        = "String"
        description = "IAM role assumed by SSM Automation to call CloudTrail StartLogging."
        default     = aws_iam_role.cloudtrail_auto_remediation_automation.arn
      }
    }
    mainSteps = [
      {
        name           = "StartCloudTrailLogging"
        action         = "aws:executeAwsApi"
        maxAttempts    = 3
        timeoutSeconds = 30
        inputs = {
          Service = "cloudtrail"
          Api     = "StartLogging"
          Name    = "{{ TrailName }}"
        }
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role" "cloudtrail_auto_remediation_eventbridge" {
  name = "tf4-cloudtrail-auto-remediation-eventbridge-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "AllowEventBridgeAssume"
      Effect = "Allow"
      Principal = {
        Service = "events.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "cloudtrail_auto_remediation_eventbridge" {
  name = "tf4-cloudtrail-start-automation-policy"
  role = aws_iam_role.cloudtrail_auto_remediation_eventbridge.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowStartAutomationExecution"
        Effect = "Allow"
        Action = [
          "ssm:StartAutomationExecution"
        ]
        Resource = [
          local.cloudtrail_automation_definition_arn,
          "${local.cloudtrail_automation_definition_arn}:*"
        ]
      },
      {
        Sid    = "AllowPassAutomationRoleToSSM"
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = aws_iam_role.cloudtrail_auto_remediation_automation.arn
        Condition = {
          StringEquals = {
            "iam:PassedToService" = "ssm.amazonaws.com"
          }
        }
      }
    ]
  })
}

resource "aws_cloudwatch_event_rule" "cloudtrail_stoplogging_auto_remediation" {
  name        = local.cloudtrail_auto_remediation_rule_name
  description = "Start SSM Automation when CloudTrail logging is stopped."
  state       = "ENABLED"

  event_pattern = jsonencode({
    source      = ["aws.cloudtrail"]
    detail-type = ["AWS API Call via CloudTrail"]
    detail = {
      eventSource = ["cloudtrail.amazonaws.com"]
      eventName   = ["StopLogging"]
    }
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "cloudtrail_stoplogging_auto_remediation" {
  rule      = aws_cloudwatch_event_rule.cloudtrail_stoplogging_auto_remediation.name
  target_id = "RestoreCloudTrailLogging"
  arn       = local.cloudtrail_automation_definition_arn
  role_arn  = aws_iam_role.cloudtrail_auto_remediation_eventbridge.arn

  input = jsonencode({
    Parameters = {
      TrailName            = [aws_cloudtrail.main.name]
      AutomationAssumeRole = [aws_iam_role.cloudtrail_auto_remediation_automation.arn]
    }
  })

  depends_on = [
    aws_ssm_document.cloudtrail_auto_remediation,
    aws_iam_role_policy.cloudtrail_auto_remediation_eventbridge
  ]
}
