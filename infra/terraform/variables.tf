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

variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
  default     = "techx-tf4-cluster"

  validation {
    condition     = can(regex("^[a-zA-Z][a-zA-Z0-9-]{0,99}$", var.cluster_name))
    error_message = "cluster_name must start with a letter and contain only alphanumeric chars and hyphens, max 100 chars."
  }
}

variable "cluster_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
  default     = "1.34"

  validation {
    condition     = can(regex("^[0-9]+[.][0-9]+$", var.cluster_version))
    error_message = "cluster_version must be a valid Kubernetes version (e.g., 1.30)."
  }
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "vpc_cidr must be a valid IPv4 CIDR block."
  }
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets (one per AZ)"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]

  validation {
    condition     = length(var.private_subnet_cidrs) >= 2
    error_message = "At least 2 private subnets are required for multi-AZ resilience."
  }
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets (one per AZ)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]

  validation {
    condition     = length(var.public_subnet_cidrs) >= 2
    error_message = "At least 2 public subnets are required for ALB multi-AZ."
  }
}

variable "allowed_cluster_endpoint_cidrs" {
  description = "List of CIDR blocks allowed to access the EKS cluster public endpoint"
  type        = list(string)
  default     = ["0.0.0.0/0"]

  validation {
    condition     = alltrue([for cidr in var.allowed_cluster_endpoint_cidrs : can(cidrhost(cidr, 0))])
    error_message = "All entries in allowed_cluster_endpoint_cidrs must be valid CIDR blocks."
  }
}

variable "tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default = {
    Owner       = "CDO_04"
    Team        = "CDO_04"
    Project     = "TF4"
    Environment = "Phase3"
  }
}

variable "budget_monthly_limit" {
  description = "Monthly AWS cost budget limit in USD"
  type        = string
  default     = "300"

  validation {
    condition     = try(tonumber(var.budget_monthly_limit), 0) > 0
    error_message = "budget_monthly_limit must be a positive number represented as a string."
  }
}

variable "budget_notification_emails" {
  description = "Email addresses that receive AWS Budget threshold notifications"
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for email in var.budget_notification_emails : can(regex("^[^@\\s]+@[^@\\s]+[.][^@\\s]+$", email))])
    error_message = "Each budget_notification_emails entry must be a valid email address."
  }
}

variable "external_secrets_chart_version" {
  description = "Version of the External Secrets Operator Helm chart"
  type        = string
  default     = "0.9.20"

  validation {
    condition     = can(regex("^[0-9]+[.][0-9]+[.][0-9]+$", var.external_secrets_chart_version))
    error_message = "external_secrets_chart_version must be a valid semver version string."
  }
}

variable "argocd_chart_version" {
  description = "Version of the Argo CD Helm chart"
  type        = string
  default     = "7.3.7"

  validation {
    condition     = can(regex("^[0-9]+[.][0-9]+[.][0-9]+$", var.argocd_chart_version))
    error_message = "argocd_chart_version must be a valid semver version string."
  }
}
