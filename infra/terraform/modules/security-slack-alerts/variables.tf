variable "kms_key_arn" {
  type        = string
  description = "The ARN of the KMS key used for encryption of SNS topic and SSM parameters"
}

variable "event_bus_name" {
  type        = string
  description = "EventBridge bus name to attach the rules to"
  default     = "default"
}

variable "slack_webhook_ssm_param_name" {
  type        = string
  description = "Name of the SSM parameter storing the Slack webhook URL"
  default     = "/security-alerts/slack-webhook-url"
}

variable "sns_topic_name" {
  type        = string
  description = "Name of the SNS topic for security alerts"
  default     = "audit-security-alerts"
}

variable "lambda_runtime" {
  type        = string
  description = "Runtime environment for the Lambda function"
  default     = "python3.12"
}

variable "tags" {
  type        = map(string)
  description = "A map of tags to add to all resources"
  default     = {}
}
