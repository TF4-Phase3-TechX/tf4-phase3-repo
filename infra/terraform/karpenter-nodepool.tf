# Owner: CDO08 Reliability / CDO04 Infrastructure
#
# Stage 2: NodePool + EC2NodeClass, brought under Terraform so the security
# group and capacity limits are reviewed here instead of applied ad hoc with
# kubectl. Capped at 16 vCPU total dynamic capacity for the reviewed mandate.

resource "kubernetes_manifest" "karpenter_ec2nodeclass_general" {
  manifest = {
    apiVersion = "karpenter.k8s.aws/v1"
    kind       = "EC2NodeClass"
    metadata = {
      name = "techx-general"
    }
    spec = {
      role = module.karpenter.node_iam_role_name

      # Karpenter v1 EC2NodeClass requires amiSelectorTerms explicitly; an
      # alias term both selects the latest AL2023 AMI and implies amiFamily,
      # so amiFamily itself is no longer set here.
      amiSelectorTerms = [
        { alias = "al2023@latest" }
      ]

      subnetSelectorTerms = [
        { tags = { "karpenter.sh/discovery" = var.cluster_name } }
      ]

      # Matches node_security_group_tags in eks.tf. Selecting by tag here
      # (rather than the cluster security group id) keeps this in sync with
      # whichever security group the EKS-managed node group actually uses.
      securityGroupSelectorTerms = [
        { tags = { "karpenter.sh/discovery" = var.cluster_name } }
      ]

      tags = merge(var.tags, {
        "karpenter.sh/discovery" = var.cluster_name
      })
    }
  }

  depends_on = [helm_release.karpenter]
}

resource "kubernetes_manifest" "karpenter_nodepool_general" {
  manifest = {
    apiVersion = "karpenter.sh/v1"
    kind       = "NodePool"
    metadata = {
      name = "techx-general"
    }
    spec = {
      template = {
        spec = {
          nodeClassRef = {
            group = "karpenter.k8s.aws"
            kind  = "EC2NodeClass"
            name  = "techx-general"
          }

          requirements = [
            { key = "kubernetes.io/arch", operator = "In", values = ["amd64"] },
            { key = "kubernetes.io/os", operator = "In", values = ["linux"] },
            { key = "karpenter.sh/capacity-type", operator = "In", values = ["on-demand"] },
            { key = "node.kubernetes.io/instance-type", operator = "In", values = ["t3.large", "t3a.large"] },
          ]

          expireAfter = "720h"
        }
      }

      # Current mandate uses On-Demand only (see karpenter.tf); cap total
      # dynamic capacity until a higher limit is separately reviewed.
      limits = {
        cpu = "16"
      }

      disruption = {
        consolidationPolicy = "WhenEmptyOrUnderutilized"
        consolidateAfter    = "5m"
      }
    }
  }

  depends_on = [kubernetes_manifest.karpenter_ec2nodeclass_general]
}
