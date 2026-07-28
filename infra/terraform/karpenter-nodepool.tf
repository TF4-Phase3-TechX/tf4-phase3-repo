# Owner: CDO08 Reliability / CDO04 Infrastructure
#
# Capacity is split by role so protected workloads cannot land on ARM64 Spot
# nodes until their chart placement policy is separately reviewed.

resource "kubernetes_manifest" "karpenter_ec2nodeclass_general" {
  manifest = {
    apiVersion = "karpenter.k8s.aws/v1"
    kind       = "EC2NodeClass"
    metadata = {
      name = "techx-general"
    }
    spec = {
      role = module.karpenter.node_iam_role_name

      # Karpenter v1 EC2NodeClass requires amiSelectorTerms explicitly.
      # Pin the AL2023 AMI release currently resolved in runtime to avoid
      # unreviewed node image drift from a moving alias.
      amiSelectorTerms = [
        { alias = "al2023@v20260709" }
      ]

      subnetSelectorTerms = [
        { tags = { "karpenter.sh/discovery" = var.cluster_name } }
      ]

      # Select only the EKS node security group. The shared discovery tag is
      # also present on cluster SGs and must not be used for SG selection.
      securityGroupSelectorTerms = [
        { tags = { "karpenter.sh/node-security-group" = var.cluster_name } }
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
        metadata = {
          labels = {
            "optimization.techx.io/tier" = "protected"
          }
        }
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
            { key = "node.kubernetes.io/instance-type", operator = "In", values = ["t3a.large"] },
            { key = "topology.kubernetes.io/zone", operator = "In", values = ["${var.aws_region}a", "${var.aws_region}b"] },
          ]

          expireAfter = "720h"
        }
      }

      limits = {
        cpu = "8"
      }

      disruption = {
        consolidationPolicy = "WhenEmptyOrUnderutilized"
        consolidateAfter    = "5m"
        budgets = [
          { nodes = "1" }
        ]
      }
    }
  }

  field_manager {
    force_conflicts = true
  }

  depends_on = [kubernetes_manifest.karpenter_ec2nodeclass_general]
}

resource "kubernetes_manifest" "karpenter_nodepool_arm64_canary" {
  manifest = {
    apiVersion = "karpenter.sh/v1"
    kind       = "NodePool"
    metadata = {
      name = "techx-arm64-canary"
    }
    spec = {
      template = {
        metadata = {
          labels = {
            "optimization.techx.io/tier" = "arm64-canary"
          }
        }
        spec = {
          nodeClassRef = {
            group = "karpenter.k8s.aws"
            kind  = "EC2NodeClass"
            name  = "techx-general"
          }

          requirements = [
            { key = "kubernetes.io/arch", operator = "In", values = ["arm64"] },
            { key = "kubernetes.io/os", operator = "In", values = ["linux"] },
            { key = "karpenter.sh/capacity-type", operator = "In", values = ["on-demand"] },
            { key = "node.kubernetes.io/instance-type", operator = "In", values = ["c7g.large", "m7g.large"] },
            { key = "topology.kubernetes.io/zone", operator = "In", values = ["${var.aws_region}a", "${var.aws_region}b"] },
          ]
          taints = [
            {
              key    = "optimization.techx.io/tier"
              value  = "arm64-canary"
              effect = "NoSchedule"
            }
          ]

          expireAfter = "720h"
        }
      }

      limits = {
        cpu = "6"
      }

      disruption = {
        consolidationPolicy = "WhenEmptyOrUnderutilized"
        consolidateAfter    = "5m"
        budgets = [
          { nodes = "1" }
        ]
      }
    }
  }

  depends_on = [kubernetes_manifest.karpenter_ec2nodeclass_general]
}

resource "kubernetes_manifest" "karpenter_nodepool_arm64_protected" {
  manifest = {
    apiVersion = "karpenter.sh/v1"
    kind       = "NodePool"
    metadata = {
      name = "techx-arm64-protected"
    }
    spec = {
      template = {
        metadata = {
          labels = {
            "optimization.techx.io/tier" = "arm64-protected"
          }
        }
        spec = {
          nodeClassRef = {
            group = "karpenter.k8s.aws"
            kind  = "EC2NodeClass"
            name  = "techx-general"
          }

          requirements = [
            { key = "kubernetes.io/arch", operator = "In", values = ["arm64"] },
            { key = "kubernetes.io/os", operator = "In", values = ["linux"] },
            { key = "karpenter.sh/capacity-type", operator = "In", values = ["on-demand"] },
            { key = "node.kubernetes.io/instance-type", operator = "In", values = ["t4g.large"] },
            { key = "topology.kubernetes.io/zone", operator = "In", values = ["${var.aws_region}b"] },
          ]
          taints = [
            {
              key    = "optimization.techx.io/tier"
              value  = "arm64-protected"
              effect = "NoSchedule"
            }
          ]

          expireAfter = "720h"
        }
      }

      limits = {
        cpu = "4"
      }

      disruption = {
        consolidationPolicy = "WhenEmptyOrUnderutilized"
        consolidateAfter    = "5m"
        budgets = [
          { nodes = "1" }
        ]
      }
    }
  }

  depends_on = [kubernetes_manifest.karpenter_ec2nodeclass_general]
}

resource "kubernetes_manifest" "karpenter_nodepool_arm64_spot" {
  manifest = {
    apiVersion = "karpenter.sh/v1"
    kind       = "NodePool"
    metadata = {
      name = "techx-arm64-spot"
    }
    spec = {
      template = {
        metadata = {
          labels = {
            "optimization.techx.io/tier" = "arm64-spot"
          }
        }
        spec = {
          nodeClassRef = {
            group = "karpenter.k8s.aws"
            kind  = "EC2NodeClass"
            name  = "techx-general"
          }

          requirements = [
            { key = "kubernetes.io/arch", operator = "In", values = ["arm64"] },
            { key = "kubernetes.io/os", operator = "In", values = ["linux"] },
            { key = "karpenter.sh/capacity-type", operator = "In", values = ["spot"] },
            { key = "node.kubernetes.io/instance-type", operator = "In", values = ["c7g.large", "m7g.large", "r7g.large", "c7g.xlarge", "m7g.xlarge"] },
            { key = "topology.kubernetes.io/zone", operator = "In", values = ["${var.aws_region}a", "${var.aws_region}b"] },
          ]
          taints = [
            {
              key    = "optimization.techx.io/tier"
              value  = "arm64-spot"
              effect = "NoSchedule"
            }
          ]

          expireAfter = "720h"
        }
      }

      limits = {
        cpu = "6"
      }

      disruption = {
        consolidationPolicy = "WhenEmptyOrUnderutilized"
        consolidateAfter    = "5m"
        budgets = [
          { nodes = "1" }
        ]
      }
    }
  }

  depends_on = [kubernetes_manifest.karpenter_ec2nodeclass_general]
}
