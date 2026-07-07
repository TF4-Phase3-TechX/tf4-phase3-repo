# Owner: Huy Hoàng nhóm CDO_04
variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "state_bucket_name" {
  description = "Globally unique name for the S3 bucket to store Terraform state"
  type        = string
  default     = "tf4-phase3-state-bucket-511825856493"
}

variable "lock_table_name" {
  description = "Name of the DynamoDB table for state locking"
  type        = string
  default     = "tf4-phase3-state-locks"
}
