# Owner: Huy Hoàng nhóm CDO_04
# EKS access entries for CI/CD and AWS SSO roles.
# Admin roles get cluster-wide admin access for phase 3 operations.
# Read-only roles get cluster-wide view access for audit and troubleshooting.

locals {
  eks_admin_access_entries = {
    github_actions_terraform_apply = "arn:aws:iam::511825856493:role/tf4-github-actions-terraform-apply"
    github_actions_deploy          = "arn:aws:iam::511825856493:role/tf4-github-actions-eks-deploy"
    sso_admin_breakglass           = "arn:aws:iam::511825856493:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_TF4-Admin-BreakGlass_99a0fe2c9d050d5d"
    sso_deploy_operator            = "arn:aws:iam::511825856493:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_TF4-DeployOperator_eb819e1d80dc6016"
    sso_security_iam_manager       = "arn:aws:iam::511825856493:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_TF4-SecurityIAMSSOManager_7fec96c816beda10"
  }

  eks_view_access_entries = {
    sso_ai_readonly_limited_invoke     = "arn:aws:iam::511825856493:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_4536cac35e2c79b6"
    sso_audit_readonly_analyze         = "arn:aws:iam::511825856493:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882"
    sso_base_readonly                  = "arn:aws:iam::511825856493:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_TF4-BaseReadOnly_5e03394d61df47e7"
    sso_cost_perf_readonly_alerting    = "arn:aws:iam::511825856493:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_TF4-CostPerfReadOnlyAlerting_9122727d2f4b2e86"
    sso_sec_reliability_readonly_audit = "arn:aws:iam::511825856493:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155"
  }
}

resource "aws_eks_access_entry" "admin" {
  for_each = local.eks_admin_access_entries

  cluster_name  = module.eks.cluster_name
  principal_arn = each.value
  type          = "STANDARD"

  tags = var.tags
}

resource "aws_eks_access_policy_association" "admin" {
  for_each = local.eks_admin_access_entries

  cluster_name  = module.eks.cluster_name
  principal_arn = aws_eks_access_entry.admin[each.key].principal_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"

  access_scope {
    type = "cluster"
  }
}

resource "aws_eks_access_entry" "view" {
  for_each = local.eks_view_access_entries

  cluster_name  = module.eks.cluster_name
  principal_arn = each.value
  type          = "STANDARD"

  tags = var.tags
}

resource "aws_eks_access_policy_association" "view" {
  for_each = local.eks_view_access_entries

  cluster_name  = module.eks.cluster_name
  principal_arn = aws_eks_access_entry.view[each.key].principal_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy"

  access_scope {
    type = "cluster"
  }
}
