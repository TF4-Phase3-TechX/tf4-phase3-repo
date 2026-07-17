terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

resource "aws_ssm_parameter" "slack_webhook" {
  name   = var.slack_webhook_ssm_param_name
  type   = "SecureString"
  key_id = var.kms_key_arn
  value  = "PLACEHOLDER_SET_MANUALLY"

  lifecycle {
    ignore_changes = [value]
  }
}
