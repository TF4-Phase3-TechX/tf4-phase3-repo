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

output "aws_config_recorder_name" {
  description = "Tên configuration recorder của AWS Config cho AUDIT-009"
  value       = aws_config_configuration_recorder.main.name
}

output "aws_config_staging_bucket_name" {
  description = "Tên S3 staging bucket nhận dữ liệu do AWS Config phân phối"
  value       = aws_s3_bucket.config_staging.id
}

output "aws_config_staging_bucket_arn" {
  description = "ARN của S3 staging bucket dành cho AWS Config"
  value       = aws_s3_bucket.config_staging.arn
}

output "aws_config_archive_bucket_name" {
  description = "Tên S3 archive bucket WORM nhận bản sao AWS Config"
  value       = aws_s3_bucket.config_archive.id
}

output "aws_config_archive_bucket_arn" {
  description = "ARN của S3 archive bucket WORM dành cho AWS Config"
  value       = aws_s3_bucket.config_archive.arn
}

output "aws_config_evidence_prefix" {
  description = "S3 prefix chứa evidence AWS Config trong staging bucket và archive bucket"
  value       = local.aws_config_evidence_prefix
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
