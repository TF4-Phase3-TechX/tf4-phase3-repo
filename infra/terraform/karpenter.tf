# Owner: CDO08 Reliability / CDO04 Infrastructure
#
# Stage 1 installs the Karpenter controller and its AWS IAM prerequisites.
# NodePool and EC2NodeClass are intentionally added in a later reviewed step so
# the controller cannot provision nodes before capacity limits are approved.

module "karpenter" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "~> 20.0"

  cluster_name = module.eks.cluster_name

  enable_irsa                     = true
  irsa_oidc_provider_arn          = module.eks.oidc_provider_arn
  irsa_namespace_service_accounts = ["kube-system:karpenter"]

  iam_role_name            = "karpenter-controller-${var.cluster_name}"
  iam_role_use_name_prefix = false

  create_node_iam_role          = true
  node_iam_role_name            = "karpenter-node-${var.cluster_name}"
  node_iam_role_use_name_prefix = false
  create_access_entry           = true

  # Current mandate uses On-Demand worker capacity only. Spot interruption
  # handling can be enabled later if a Spot NodePool is introduced.
  enable_spot_termination = false

  tags = var.tags
}

resource "helm_release" "karpenter" {
  name             = "karpenter"
  namespace        = "kube-system"
  repository       = "oci://public.ecr.aws/karpenter"
  chart            = "karpenter"
  version          = "1.14.0"
  create_namespace = false
  wait             = true
  timeout          = 600

  set {
    name  = "settings.clusterName"
    value = module.eks.cluster_name
  }

  set {
    name  = "serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn"
    value = module.karpenter.iam_role_arn
  }

  set {
    name  = "controller.resources.requests.cpu"
    value = "500m"
  }

  set {
    name  = "controller.resources.requests.memory"
    value = "512Mi"
  }

  set {
    name  = "controller.resources.limits.cpu"
    value = "1"
  }

  set {
    name  = "controller.resources.limits.memory"
    value = "1Gi"
  }

  depends_on = [module.karpenter]
}
