# Owner: Huy Hoàng nhóm CDO_04
# Preserve existing Terraform state addresses while moving EKS access entries
# from implicit/module-specific resources to explicit role-based resources.

moved {
  from = module.eks.aws_eks_access_entry.this["cluster_creator"]
  to   = aws_eks_access_entry.admin["github_actions_terraform_apply"]
}

moved {
  from = module.eks.aws_eks_access_policy_association.this["cluster_creator_admin"]
  to   = aws_eks_access_policy_association.admin["github_actions_terraform_apply"]
}

moved {
  from = aws_eks_access_entry.github_actions_deploy
  to   = aws_eks_access_entry.admin["github_actions_deploy"]
}

moved {
  from = aws_eks_access_policy_association.github_actions_deploy_admin
  to   = aws_eks_access_policy_association.admin["github_actions_deploy"]
}

moved {
  from = aws_eks_access_policy_association.sec_reliability_secret_reader
  to   = aws_eks_access_policy_association.secret_reader["sso_sec_reliability_readonly_audit"]
}
