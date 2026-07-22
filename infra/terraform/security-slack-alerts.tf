module "security_slack_alerts" {
  source = "./modules/security-slack-alerts"

  kms_key_arn                  = aws_kms_key.cloudtrail.arn
  event_bus_name               = "default"
  slack_webhook_ssm_param_name = "/security-alerts/slack-webhook-url"
  sns_topic_name               = "audit-security-alerts"
  lambda_runtime               = "python3.12"
  alert_email_endpoint         = "Hoangkimhung2004@gmail.com"

  tags = var.tags
}
