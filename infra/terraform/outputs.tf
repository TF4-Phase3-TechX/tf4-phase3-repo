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

output "karpenter_controller_role_arn" {
  description = "IAM role ARN used by the Karpenter controller service account"
  value       = module.karpenter.iam_role_arn
}

output "karpenter_node_role_name" {
  description = "IAM role name used by Karpenter-provisioned worker nodes"
  value       = module.karpenter.node_iam_role_name
}

# REL-14 — Managed PostgreSQL baseline outputs for SEC-13 / REL-15 handoff
output "rds_postgresql_endpoint" {
  description = "Private RDS PostgreSQL endpoint for TechX managed PostgreSQL target"
  value       = aws_db_instance.postgresql.address
}

output "rds_postgresql_port" {
  description = "RDS PostgreSQL listener port"
  value       = aws_db_instance.postgresql.port
}

output "rds_postgresql_database_name" {
  description = "Initial database name for the RDS PostgreSQL target"
  value       = aws_db_instance.postgresql.db_name
}

output "rds_postgresql_instance_arn" {
  description = "ARN of the RDS PostgreSQL instance"
  value       = aws_db_instance.postgresql.arn
}

output "rds_postgresql_security_group_id" {
  description = "Security group ID attached to the RDS PostgreSQL target"
  value       = aws_security_group.rds_postgresql.id
}

output "rds_postgresql_subnet_group_name" {
  description = "DB subnet group name used by the RDS PostgreSQL target"
  value       = aws_db_subnet_group.postgresql.name
}

output "rds_postgresql_parameter_group_name" {
  description = "DB parameter group name used by the RDS PostgreSQL target"
  value       = aws_db_parameter_group.postgresql.name
}

output "rds_postgresql_master_user_secret_arn" {
  description = "RDS-managed master user secret ARN for admin/bootstrap reference only; application workloads must use the SEC-13 app secret contract instead"
  value       = try(aws_db_instance.postgresql.master_user_secret[0].secret_arn, null)
  sensitive   = true
}

output "rds_postgresql_app_secret_path" {
  description = "AWS Secrets Manager path expected for the SEC-13 PostgreSQL application secret contract"
  value       = "techx/tf4/rds-postgres"
}

output "rds_postgresql_kubernetes_secret_name" {
  description = "Kubernetes Secret name expected for the SEC-13 PostgreSQL application secret contract"
  value       = "rds-postgres-secret"
}

output "rds_postgresql_kubernetes_secret_namespace" {
  description = "Kubernetes namespace expected for the SEC-13 PostgreSQL application secret contract"
  value       = "techx-tf4"
}

output "rds_postgresql_credential_handoff_note" {
  description = "Credential handoff note for SEC-13"
  value       = "REL-14 does not create the PostgreSQL application secret. The RDS-managed master secret is admin/bootstrap only; SEC-13 owns techx/tf4/rds-postgres -> techx-tf4/rds-postgres-secret for workloads."
}
