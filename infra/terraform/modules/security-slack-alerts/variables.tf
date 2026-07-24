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

variable "detection_metric_namespace" {
  type        = string
  description = "CloudWatch custom metric namespace for MANDATE-11 detection latency"
  default     = "Mandate11/DetectionLatency"
}

variable "slack_webhook_allowed_hosts" {
  type        = list(string)
  description = "HTTPS hosts allowed for the Slack webhook to prevent outbound alert exfiltration"
  default     = ["hooks.slack.com"]

  validation {
    condition = (
      length(var.slack_webhook_allowed_hosts) > 0 &&
      alltrue([
        for host in var.slack_webhook_allowed_hosts :
        length(trimspace(host)) > 0 && !strcontains(host, "://")
      ])
    )
    error_message = "slack_webhook_allowed_hosts must contain hostnames without URL schemes."
  }
}

variable "detection_latency_target_seconds" {
  type        = number
  description = "Target p95 latency in seconds from CloudTrail event time to Slack webhook acceptance"
  default     = 60

  validation {
    condition     = var.detection_latency_target_seconds > 0
    error_message = "detection_latency_target_seconds must be greater than zero."
  }
}

variable "tags" {
  type        = map(string)
  description = "A map of tags to add to all resources"
  default     = {}
}

variable "formatted_sns_topic_name" {
  type        = string
  description = "Name of the SNS topic that delivers human-readable formatted security alert emails"
  default     = "audit-security-alerts-formatted"
}

variable "alert_email_endpoint" {
  type        = string
  description = "Email address that receives human-readable security alert notifications"

  validation {
    condition     = can(regex("^[^@]+@[^@]+\\.[^@]+$", var.alert_email_endpoint))
    error_message = "alert_email_endpoint must be a valid email address."
  }
}

variable "anomaly_sns_topic_name" {
  type        = string
  description = "Name of the SNS topic for Mandate-11 H2 anomaly detection alarms (separate from main alert topic)"
  default     = "audit-security-alerts-anomaly"
}
