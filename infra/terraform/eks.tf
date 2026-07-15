# Owner: Huy Hoàng nhóm CDO_04
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = var.cluster_version

  # Private endpoint for cluster-internal access, public with CIDR restriction for kubectl
  cluster_endpoint_private_access      = true
  cluster_endpoint_public_access       = true
  cluster_endpoint_public_access_cidrs = var.allowed_cluster_endpoint_cidrs

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  cluster_security_group_tags = {
    "karpenter.sh/discovery" = var.cluster_name
  }

  # Karpenter-provisioned nodes select their security group by this same
  # discovery tag. Without it here, Karpenter falls back to matching the
  # cluster security group (control-plane traffic only) instead of the node
  # security group that already allows node-to-node/pod-to-pod traffic,
  # so new nodes can schedule but can't reach CoreDNS or other pods.
  node_security_group_tags = {
    "karpenter.sh/discovery" = var.cluster_name
  }

  # Bật Control Plane Logging
  cluster_enabled_log_types = ["api", "audit", "authenticator"]

  # Bật OIDC provider cho Service Accounts (IRSA)
  enable_irsa = true

  # Khai báo các Addon cần cài đặt cho EKS
  cluster_addons = {
    coredns            = {}
    kube-proxy         = {}
    vpc-cni            = {}
    aws-ebs-csi-driver = {}
  }

  # EKS access entries are managed explicitly in eks-access-entries.tf.
  enable_cluster_creator_admin_permissions = false

  # Keep KMS key administration stable across local and CI Terraform runs.
  kms_key_administrators = [
    "arn:aws:iam::511825856493:role/tf4-github-actions-terraform-apply",
  ]

  # Định nghĩa Managed Node Group chạy trong Private Subnets
  eks_managed_node_groups = {
    general = {
      name         = "techx-general-ng"
      min_size     = 2
      max_size     = 4
      desired_size = 2

      instance_types = ["t3.large"]
      capacity_type  = "ON_DEMAND"

      block_device_mappings = {
        xvda = {
          device_name = "/dev/xvda"
          ebs = {
            volume_size           = 20
            volume_type           = "gp3"
            iops                  = 3000
            throughput            = 125
            delete_on_termination = true
          }
        }
      }

      # Gắn thêm các IAM policy phổ biến cho worker nodes
      iam_role_additional_policies = {
        AmazonEBSCSIDriverPolicy           = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
        AmazonEKS_CNI_Policy               = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
        CloudWatchAgentServerPolicy        = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
        AmazonEC2ContainerRegistryReadOnly = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
      }

      labels = {
        role = "worker"
      }

      tags = var.tags
    }
  }

  tags = var.tags
}
