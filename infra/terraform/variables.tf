# Owner: Huy Hoàng nhóm CDO_04

# REL-22 (CDO08): MSK Connect provisioned capacity is blocked at the AWS account
# level with "AccessDeniedException: We are unable to process your request"
# even when called with Admin/BreakGlass credentials. All IAM, SCP, quota, VPC
# and DNS checks pass — this is a backend account-level restriction.
# Set to true only after AWS Support enables MSK Connect for account 511825856493.
variable "msk_connect_connector_enabled" {
  description = "Enable MSK Connect provisioned connector for REL-22 orders S3 archive. Set false until AWS Support enables MSK Connect capacity for this account."
  type        = bool
  default     = false
}
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

variable "valkey_auth_token" {
  description = "Sensitive auth token for the managed ElastiCache Valkey replication group. Provide through TF_VAR_valkey_auth_token only; do not commit the value."
  type        = string
  sensitive   = true
  default     = null

  validation {
    condition = (
      var.valkey_auth_token == null ||
      can(regex("^[^@\"/ ]{16,128}$", var.valkey_auth_token))
    )
    error_message = "valkey_auth_token must be 16-128 characters and must not contain spaces, double quotes, slash, or @."
  }
}

variable "valkey_transit_encryption_mode" {
  description = "ElastiCache Valkey transit encryption mode. Mandate 08 final target is required after Cart is confirmed TLS-capable."
  type        = string
  default     = "required"

  validation {
    condition     = contains(["preferred", "required"], var.valkey_transit_encryption_mode)
    error_message = "valkey_transit_encryption_mode must be preferred or required."
  }
}

variable "karpenter_arm64_spot_zones" {
  description = "Allowed AZs for the arm64 Spot NodePool. Keep default empty for normal multi-AZ operation; set temporarily during REL-35 AZ-loss drill to block Spot replacement in the target AZ."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for zone in var.karpenter_arm64_spot_zones :
      can(regex("^[a-z]{2}-[a-z]+-[0-9][a-z]$", zone))
    ])
    error_message = "karpenter_arm64_spot_zones entries must be full AZ names, for example us-east-1a."
  }
}

variable "karpenter_arm64_protected_zones" {
  description = "Allowed AZs for the arm64 protected On-Demand NodePool. Keep default empty for normal protected capacity in us-east-1b; set temporarily during REL-35 AZ-loss drill to block replacement in the target AZ."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for zone in var.karpenter_arm64_protected_zones :
      can(regex("^[a-z]{2}-[a-z]+-[0-9][a-z]$", zone))
    ])
    error_message = "karpenter_arm64_protected_zones entries must be full AZ names, for example us-east-1a."
  }
}

variable "managed_node_group_arm64_1b_size" {
  description = "Desired/min size for the managed arm64 node group in us-east-1b. Set to 0 only during REL-35 AZ-loss drill to prevent managed-node replacement in the target AZ."
  type        = number
  default     = 1

  validation {
    condition     = contains([0, 1], var.managed_node_group_arm64_1b_size)
    error_message = "managed_node_group_arm64_1b_size must be 0 for REL-35 drill isolation or 1 for normal operation."
  }
}

variable "karpenter_general_zones" {
  description = "Allowed AZs for the general amd64 On-Demand NodePool. Keep default empty for normal multi-AZ operation; set temporarily during REL-35 AZ-loss drill to block replacement in the target AZ."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for zone in var.karpenter_general_zones :
      can(regex("^[a-z]{2}-[a-z]+-[0-9][a-z]$", zone))
    ])
    error_message = "karpenter_general_zones entries must be full AZ names, for example us-east-1a."
  }
}

variable "karpenter_arm64_canary_zones" {
  description = "Allowed AZs for the arm64 canary On-Demand NodePool. Keep default empty for normal multi-AZ operation; set temporarily during REL-35 AZ-loss drill to block replacement in the target AZ."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for zone in var.karpenter_arm64_canary_zones :
      can(regex("^[a-z]{2}-[a-z]+-[0-9][a-z]$", zone))
    ])
    error_message = "karpenter_arm64_canary_zones entries must be full AZ names, for example us-east-1a."
  }
}
