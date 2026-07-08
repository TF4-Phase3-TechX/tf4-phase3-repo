# Owner: Huy Hoàng nhóm CDO_04
# EKS access entries for GitHub Actions deploy role.
# Deploy role starts cluster-admin to prove CI path.
# Upgrade path: namespace-scoped RBAC for techx-tf4 and techx-observability after first deploy works.

resource "aws_eks_access_entry" "github_actions_deploy" {
  cluster_name  = module.eks.cluster_name
  principal_arn = "arn:aws:iam::511825856493:role/tf4-github-actions-eks-deploy"
  type          = "STANDARD"
}

resource "aws_eks_access_policy_association" "github_actions_deploy_admin" {
  cluster_name  = module.eks.cluster_name
  principal_arn = aws_eks_access_entry.github_actions_deploy.principal_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"

  access_scope {
    type = "cluster"
  }
}