# Owner: Huy Hoàng nhóm CDO_04
output "state_bucket_arn" {
  description = "ARN of the S3 bucket storing Terraform state"
  value       = aws_s3_bucket.terraform_state.arn
}

output "state_bucket_name" {
  description = "Name of the S3 bucket storing Terraform state"
  value       = aws_s3_bucket.terraform_state.id
}

output "lock_table_name" {
  description = "Name of the DynamoDB lock table"
  value       = aws_dynamodb_table.terraform_locks.name
}

output "github_actions_plan_role_arn" {
  description = "ARN of GitHub Actions role for PR terraform plan"
  value       = aws_iam_role.github_actions_plan.arn
}

output "github_actions_build_role_arn" {
  description = "ARN of GitHub Actions role for ECR image builds"
  value       = aws_iam_role.github_actions_build.arn
}

output "github_actions_deploy_role_arn" {
  description = "ARN of GitHub Actions role for EKS Helm deploy"
  value       = aws_iam_role.github_actions_deploy.arn
}

output "github_actions_terraform_apply_role_arn" {
  description = "ARN of GitHub Actions role for Terraform apply on main"
  value       = aws_iam_role.github_actions_terraform_apply.arn
}

output "rel24_ci_recovery_asset_guardrail_policy_arn" {
  description = "CDO08-REL-24 permissions boundary policy ARN protecting recovery assets from CI deletion"
  value       = aws_iam_policy.rel24_recovery_asset_guardrail.arn
}

output "rel24_ci_recovery_asset_explicit_deny_policy_arn" {
  description = "CDO08-REL-24 explicit deny policy ARN attached to the Terraform apply role"
  value       = aws_iam_policy.rel24_ci_protected_recovery_assets_deny.arn
}
