# Owner: Huy Hoàng nhóm CDO_04
variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]{1}$", var.aws_region))
    error_message = "aws_region must be a valid AWS region identifier (e.g., us-east-1)."
  }
}

variable "state_bucket_name" {
  description = "Globally unique name for the S3 bucket to store Terraform state"
  type        = string
  default     = "tf4-phase3-state-bucket-511825856493"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.state_bucket_name))
    error_message = "state_bucket_name must be a valid S3 bucket name (3-63 chars, lowercase alphanumeric, dots, hyphens)."
  }
}

variable "lock_table_name" {
  description = "Name of the DynamoDB table for state locking"
  type        = string
  default     = "tf4-phase3-state-locks"

  validation {
    condition     = can(regex("^[a-zA-Z0-9_.-]{3,255}$", var.lock_table_name))
    error_message = "lock_table_name must be a valid DynamoDB table name (3-255 chars, alphanumeric, underscores, dots, hyphens)."
  }
}

variable "tags" {
  description = "Common tags to apply to all bootstrap resources"
  type        = map(string)
  default = {
    Owner       = "CDO_04"
    Team        = "CDO_04"
    Project     = "TF4"
    Environment = "Phase3"
  }
}
