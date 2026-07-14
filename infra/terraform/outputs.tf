# Owner: Huy Hoàng nhóm CDO_04
output "cluster_name" {
  description = "Kubernetes Cluster Name"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "Endpoint for EKS control plane"
  value       = module.eks.cluster_endpoint
}

output "cluster_security_group_id" {
  description = "Security group ids attached to the cluster control plane"
  value       = module.eks.cluster_security_group_id
}

output "vpc_id" {
  description = "The ID of the VPC"
  value       = module.vpc.vpc_id
}

output "aws_account_id" {
  description = "AWS account ID"
  value       = data.aws_caller_identity.current.account_id
}

output "ecr_repository_url" {
  description = "ECR repository URL for TechX images"
  value       = aws_ecr_repository.techx_corp.repository_url
}

output "eks_oidc_provider_arn" {
  description = "EKS OIDC provider ARN"
  value       = module.eks.oidc_provider_arn
}

output "eks_oidc_issuer_url" {
  description = "EKS OIDC issuer URL"
  value       = module.eks.cluster_oidc_issuer_url
}

output "budget_name" {
  description = "Name of the AWS Budget for monthly cost guardrails"
  value       = aws_budgets_budget.monthly_cost.name
}

output "budget_monthly_limit" {
  description = "Monthly AWS Budget limit in USD"
  value       = var.budget_monthly_limit
}

# Ref: AUDIT-010 — CloudTrail tamper-evident outputs
output "cloudtrail_kms_key_arn" {
  description = "ARN of the KMS CMK used to encrypt CloudTrail logs"
  value       = aws_kms_key.cloudtrail.arn
}

output "cloudtrail_kms_key_id" {
  description = "Key ID of the CloudTrail KMS CMK (for key policy review)"
  value       = aws_kms_key.cloudtrail.key_id
}

output "cloudtrail_log_group_name" {
  description = "CloudWatch Log Group name receiving CloudTrail events"
  value       = aws_cloudwatch_log_group.cloudtrail.name
}

output "cloudtrail_log_group_arn" {
  description = "CloudWatch Log Group ARN for CloudTrail"
  value       = aws_cloudwatch_log_group.cloudtrail.arn
}

output "karpenter_controller_role_arn" {
  description = "IAM role ARN used by the Karpenter controller service account"
  value       = module.karpenter.iam_role_arn
}

output "karpenter_node_role_name" {
  description = "IAM role name used by Karpenter-provisioned worker nodes"
  value       = module.karpenter.node_iam_role_name
}
