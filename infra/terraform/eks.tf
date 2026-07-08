# Owner: Huy Hoàng nhóm CDO_04
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = var.cluster_version

  cluster_endpoint_public_access = true

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # Bật OIDC provider cho Service Accounts (IRSA)
  enable_irsa = true

  # Cấp quyền admin EKS cho tài khoản/IAM Principal tạo cụm (để kubectl get nodes hoạt động)
  enable_cluster_creator_admin_permissions = true

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
        AmazonEBSCSIDriverPolicy          = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
        AmazonEKS_CNI_Policy              = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
        AutoScalingFullAccess             = "arn:aws:iam::aws:policy/AutoScalingFullAccess"
        CloudWatchAgentServerPolicy       = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
      }

      labels = {
        role = "worker"
      }

      tags = {
        Environment = "Phase3"
        Team        = "TF4"
      }
    }
  }

  tags = {
    Environment = "Phase3"
    Team        = "TF4"
  }
}
