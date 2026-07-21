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

output "cloudtrail_auto_remediation_eventbridge_rule_name" {
  description = "EventBridge rule that starts SSM Automation when CloudTrail StopLogging is detected"
  value       = aws_cloudwatch_event_rule.cloudtrail_stoplogging_auto_remediation.name
}

output "cloudtrail_auto_remediation_ssm_document_name" {
  description = "SSM Automation document used to re-enable CloudTrail logging"
  value       = aws_ssm_document.cloudtrail_auto_remediation.name
}

output "karpenter_controller_role_arn" {
  description = "IAM role ARN used by the Karpenter controller service account"
  value       = module.karpenter.iam_role_arn
}

output "karpenter_node_role_name" {
  description = "IAM role name used by Karpenter-provisioned worker nodes"
  value       = module.karpenter.node_iam_role_name
}

output "msk_orders_cluster_arn" {
  description = "MSK cluster ARN for the orders migration target"
  value       = aws_msk_cluster.orders.arn
}

output "msk_orders_cluster_name" {
  description = "MSK cluster name for the orders migration target"
  value       = aws_msk_cluster.orders.cluster_name
}

output "msk_orders_bootstrap_brokers_sasl_scram" {
  description = "SASL/SCRAM bootstrap brokers for MirrorMaker2 and Kafka clients"
  value       = aws_msk_cluster.orders.bootstrap_brokers_sasl_scram
}

output "msk_orders_broker_node_type" {
  description = "MSK broker node type for the orders migration target"
  value       = aws_msk_cluster.orders.broker_node_group_info[0].instance_type
}

output "msk_orders_broker_storage_gib" {
  description = "Initial EBS storage per MSK broker in GiB"
  value       = aws_msk_cluster.orders.broker_node_group_info[0].storage_info[0].ebs_storage_info[0].volume_size
}

output "msk_orders_storage_autoscaling_max_gib" {
  description = "Maximum EBS storage per broker configured through Application Auto Scaling"
  value       = aws_appautoscaling_target.msk_broker_storage.max_capacity
}

output "msk_orders_security_group_id" {
  description = "Security group ID attached to the MSK orders cluster"
  value       = aws_security_group.msk.id
}

output "msk_orders_kms_key_arn" {
  description = "KMS key ARN used by the MSK orders cluster"
  value       = aws_kms_key.msk.arn
}

output "msk_orders_app_secret_path" {
  description = "AWS Secrets Manager path expected for the SEC-13 MSK application secret contract"
  value       = "techx/tf4/msk-kafka"
}

output "msk_orders_kubernetes_secret_name" {
  description = "Kubernetes Secret name expected for the SEC-13 MSK application secret contract"
  value       = "msk-kafka-secret"
}

output "msk_orders_kubernetes_secret_namespace" {
  description = "Kubernetes namespace expected for the SEC-13 MSK application secret contract"
  value       = "techx-tf4"
}

output "msk_orders_scram_secret_handoff_note" {
  description = "SEC-13 owns creation of the MSK SCRAM credential secret and SCRAM secret association; REL-14 does not put credentials in Terraform state"
  value       = "REL-14 provisions the MSK baseline only. SEC-13 owns techx/tf4/msk-kafka -> techx-tf4/msk-kafka-secret and the SCRAM secret association."
}

output "msk_orders_authentication_protocol" {
  description = "Authentication and transport protocol expected by Kafka clients"
  value       = "SASL_SSL with SCRAM-SHA-512"
}

output "msk_orders_client_port" {
  description = "Client port expected for SASL/SCRAM bootstrap brokers"
  value       = 9096
}

output "elasticache_valkey_replication_group_id" {
  description = "ElastiCache Valkey replication group ID for the cart migration target"
  value       = aws_elasticache_replication_group.valkey_cart.replication_group_id
}

output "elasticache_valkey_replication_group_arn" {
  description = "ElastiCache Valkey replication group ARN for handoff and evidence"
  value       = aws_elasticache_replication_group.valkey_cart.arn
}

output "elasticache_valkey_primary_endpoint" {
  description = "Primary endpoint address for the cart ElastiCache Valkey target"
  value       = aws_elasticache_replication_group.valkey_cart.primary_endpoint_address
}

output "elasticache_valkey_reader_endpoint" {
  description = "Reader endpoint address for the cart ElastiCache Valkey target"
  value       = aws_elasticache_replication_group.valkey_cart.reader_endpoint_address
}

output "elasticache_valkey_port" {
  description = "Port for the cart ElastiCache Valkey target"
  value       = aws_elasticache_replication_group.valkey_cart.port
}

output "elasticache_valkey_security_group_id" {
  description = "Security group ID attached to the cart ElastiCache Valkey target"
  value       = aws_security_group.elasticache_valkey.id
}

output "elasticache_valkey_subnet_group_name" {
  description = "Private subnet group name used by the cart ElastiCache Valkey target"
  value       = aws_elasticache_subnet_group.valkey_cart.name
}

output "elasticache_valkey_parameter_group_name" {
  description = "Parameter group name used by the cart ElastiCache Valkey target"
  value       = aws_elasticache_parameter_group.valkey_cart.name
}

output "elasticache_valkey_at_rest_encryption_enabled" {
  description = "Whether at-rest encryption is enabled for the cart ElastiCache Valkey target"
  value       = aws_elasticache_replication_group.valkey_cart.at_rest_encryption_enabled
}

output "elasticache_valkey_transit_encryption_enabled" {
  description = "Whether in-transit encryption is enabled for the current cart ElastiCache Valkey phase"
  value       = aws_elasticache_replication_group.valkey_cart.transit_encryption_enabled
}

output "elasticache_valkey_snapshot_retention_days" {
  description = "Snapshot retention period in days for the cart ElastiCache Valkey target"
  value       = aws_elasticache_replication_group.valkey_cart.snapshot_retention_limit
}

output "elasticache_valkey_auth_token_secret_expectation" {
  description = "Secret contract expectation for the cart ElastiCache Valkey target"
  value       = "REL-14 does not create the Valkey application secret. SEC-13 owns techx/tf4/elasticache-valkey -> techx-tf4/elasticache-valkey-secret for workloads."
}

output "elasticache_valkey_app_secret_path" {
  description = "AWS Secrets Manager path expected for the SEC-13 ElastiCache Valkey application secret contract"
  value       = "techx/tf4/elasticache-valkey"
}

output "elasticache_valkey_kubernetes_secret_name" {
  description = "Kubernetes Secret name expected for the SEC-13 ElastiCache Valkey application secret contract"
  value       = "elasticache-valkey-secret"
}

output "elasticache_valkey_kubernetes_secret_namespace" {
  description = "Kubernetes namespace expected for the SEC-13 ElastiCache Valkey application secret contract"
  value       = "techx-tf4"
}

output "elasticache_valkey_app_secret_payload_keys" {
  description = "Minimum payload keys expected in the SEC-13 ElastiCache Valkey application secret"
  value       = ["host", "port", "address"]
}

output "elasticache_valkey_app_address_key" {
  description = "Application-facing key expected for the Valkey connection address"
  value       = "valkey-address"
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

# REL-15 - PostgreSQL migration backup outputs
output "postgresql_migration_backup_bucket_name" {
  description = "S3 bucket used for REL-15 PostgreSQL migration backup artifacts"
  value       = aws_s3_bucket.postgresql_migration_backups.id
}

output "postgresql_migration_backup_bucket_arn" {
  description = "ARN of the S3 bucket used for REL-15 PostgreSQL migration backup artifacts"
  value       = aws_s3_bucket.postgresql_migration_backups.arn
}

output "postgresql_migration_backup_prefix" {
  description = "Prefix used for REL-15 PostgreSQL migration backup artifacts; lifecycle expires this prefix after 7 days"
  value       = local.postgresql_migration_backup_prefix
}

# REL-15 - PostgreSQL DMS baseline outputs
output "postgresql_dms_replication_instance_arn" {
  description = "AWS DMS replication instance ARN for PostgreSQL migration"
  value       = aws_dms_replication_instance.postgresql.replication_instance_arn
}

output "postgresql_dms_replication_instance_id" {
  description = "AWS DMS replication instance ID for PostgreSQL migration"
  value       = aws_dms_replication_instance.postgresql.replication_instance_id
}

output "postgresql_dms_replication_instance_class" {
  description = "AWS DMS replication instance class for PostgreSQL migration"
  value       = aws_dms_replication_instance.postgresql.replication_instance_class
}

output "postgresql_dms_multi_az_enabled" {
  description = "Whether the PostgreSQL DMS replication instance uses Multi-AZ"
  value       = aws_dms_replication_instance.postgresql.multi_az
}

output "postgresql_dms_subnet_group_id" {
  description = "AWS DMS private subnet group ID for PostgreSQL migration"
  value       = aws_dms_replication_subnet_group.postgresql.id
}

output "postgresql_dms_security_group_id" {
  description = "Security group ID attached to the PostgreSQL DMS replication instance"
  value       = aws_security_group.dms_postgresql_migration.id
}

output "postgresql_dms_source_host" {
  description = "Temporary internal NLB hostname used by DMS to reach the self-hosted PostgreSQL source"
  value       = local.postgresql_dms_source_host
}

output "postgresql_dms_source_port" {
  description = "PostgreSQL source listener port exposed through the temporary internal NLB bridge"
  value       = 5432
}

output "postgresql_dms_source_secret_path" {
  description = "Expected AWS Secrets Manager path for the PostgreSQL source DMS credential; secret value is created outside Terraform"
  value       = local.postgresql_dms_source_secret_path
}

output "postgresql_dms_secrets_access_role_arn" {
  description = "IAM role ARN that AWS DMS can use to read PostgreSQL migration endpoint secrets"
  value       = aws_iam_role.postgresql_dms_secrets_access.arn
}

output "postgresql_dms_endpoint_task_handoff_note" {
  description = "Handoff note for DMS endpoint/task creation"
  value       = "REL-15 DMS endpoints/tasks use Secrets Manager ARNs for source/target credentials. PostgreSQL passwords are not stored directly in Terraform configuration/state."
}

output "postgresql_dms_source_endpoint_arn" {
  description = "AWS DMS source endpoint ARN for the self-hosted PostgreSQL source"
  value       = aws_dms_endpoint.postgresql_source.endpoint_arn
}

output "postgresql_dms_target_endpoint_arn" {
  description = "AWS DMS target endpoint ARN for the RDS PostgreSQL target"
  value       = aws_dms_endpoint.postgresql_target.endpoint_arn
}

output "postgresql_dms_forward_task_arn" {
  description = "AWS DMS forward full-load-and-cdc task ARN for PostgreSQL EKS to RDS"
  value       = aws_dms_replication_task.postgresql_forward.replication_task_arn
}

output "postgresql_dms_forward_task_id" {
  description = "AWS DMS forward full-load-and-cdc task ID for PostgreSQL EKS to RDS"
  value       = aws_dms_replication_task.postgresql_forward.replication_task_id
}

output "postgresql_dms_target_secret_path" {
  description = "AWS Secrets Manager path used by DMS target endpoint for RDS PostgreSQL"
  value       = local.postgresql_dms_target_secret_path
}

output "postgresql_dms_reverse_task_note" {
  description = "Reverse CDC readiness note for rollback planning"
  value       = "Reverse RDS-to-EKS DMS task is not created in this PR because EKS target write-back credential is not ready. Create a separate reverse target credential/task before post-write cutover if rollback requires reverse CDC."
}
