# The Kubernetes provider must discover Karpenter CRDs during Terraform plan.
resource "kubernetes_cluster_role_v1" "terraform_plan_crd_reader" {
  metadata {
    name = "terraform-plan-crd-reader"
  }

  rule {
    api_groups = ["apiextensions.k8s.io"]
    resources  = ["customresourcedefinitions"]
    verbs      = ["get", "list", "watch"]
  }

  rule {
    api_groups = ["karpenter.k8s.aws"]
    resources  = ["ec2nodeclasses"]
    verbs      = ["get", "list", "watch"]
  }

  rule {
    api_groups = ["karpenter.sh"]
    resources  = ["nodepools"]
    verbs      = ["get", "list", "watch"]
  }
}

resource "kubernetes_cluster_role_binding_v1" "terraform_plan_crd_reader" {
  metadata {
    name = "terraform-plan-crd-reader"
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "ClusterRole"
    name      = kubernetes_cluster_role_v1.terraform_plan_crd_reader.metadata[0].name
  }

  subject {
    kind      = "Group"
    name      = "terraform-plan-readers"
    api_group = "rbac.authorization.k8s.io"
    namespace = ""
  }
}

import {
  to = kubernetes_cluster_role_v1.terraform_plan_crd_reader
  id = "terraform-plan-crd-reader"
}

import {
  to = kubernetes_cluster_role_binding_v1.terraform_plan_crd_reader
  id = "terraform-plan-crd-reader"
}

import {
  to = aws_eks_access_policy_association.secret_reader["github_actions_terraform_plan"]
  id = "techx-tf4-cluster#arn:aws:iam::511825856493:role/tf4-github-actions-plan#arn:aws:eks::aws:cluster-access-policy/AmazonEKSSecretReaderPolicy"
}
