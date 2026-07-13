# Bastion Host configuration for secure private access to operational portals (SSM Session Manager)
# Project: techx-tf4 (CDO08-SEC-05)

# 1. Security Group for Portal Bastion Host (Block all public Ingress)
resource "aws_security_group" "portal_bastion" {
  name        = "tf4-portal-bastion-sg"
  description = "Security Group for SSM Portal Bastion Host (No Ingress)"
  vpc_id      = module.vpc.vpc_id

  # Ingress: Empty (No public inbound ports open)

  # Egress: Allow outbound HTTPS (SSM/EKS API) and basic infrastructure services
  egress {
    description = "Allow HTTPS egress to AWS SSM and EKS API"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Allow DNS egress to VPC Resolver"
    from_port   = 53
    to_port     = 53
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Allow HTTP egress for downloading kubectl/packages"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name            = "tf4-portal-bastion-sg"
    SecurityFinding = "CDO08-SEC-05"
  })
}

# 2. IAM Role for Portal Bastion Host
resource "aws_iam_role" "portal_bastion" {
  name = "tf4-portal-bastion-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })

  tags = merge(var.tags, {
    Name            = "tf4-portal-bastion-role"
    SecurityFinding = "CDO08-SEC-05"
  })
}

# Attach managed SSM core policy to enable Session Manager features
resource "aws_iam_role_policy_attachment" "portal_bastion_ssm" {
  role       = aws_iam_role.portal_bastion.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Inline policy to allow describing EKS cluster (restricted to cluster ARN)
resource "aws_iam_role_policy" "portal_bastion_eks_describe" {
  name = "tf4-portal-bastion-eks-describe"
  role = aws_iam_role.portal_bastion.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["eks:DescribeCluster"]
      Resource = module.eks.cluster_arn
    }]
  })
}

resource "aws_iam_instance_profile" "portal_bastion" {
  name = "tf4-portal-bastion-instance-profile"
  role = aws_iam_role.portal_bastion.name

  tags = merge(var.tags, {
    Name            = "tf4-portal-bastion-instance-profile"
    SecurityFinding = "CDO08-SEC-05"
  })
}

# 3. Fetch latest Amazon Linux 2023 Minimal AMI
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["al2023-ami-minimal-kernel-*-x86_64"]
  }
}

# 4. Provision private Portal Bastion Host instance (no public IP, runs in private subnet)
resource "aws_instance" "portal_bastion" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = "t3.nano"
  iam_instance_profile        = aws_iam_instance_profile.portal_bastion.name
  subnet_id                   = module.vpc.private_subnets[0]
  associate_public_ip_address = false

  vpc_security_group_ids = [aws_security_group.portal_bastion.id]

  user_data = templatefile("${path.module}/portal-bastion-user-data.sh.tftpl", {
    aws_region   = "us-east-1"
    cluster_name = module.eks.cluster_name
  })

  root_block_device {
    volume_size           = 8
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  # Enforce IMDSv2 for enhanced instance metadata security
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  tags = merge(var.tags, {
    Name            = "tf4-portal-bastion"
    SecurityFinding = "CDO08-SEC-05"
    AccessPurpose   = "OperationalPortals"
  })
}

# 5. EKS Access Entry to map Portal Bastion IAM Role to Kubernetes groups
resource "aws_eks_access_entry" "portal_bastion" {
  cluster_name      = module.eks.cluster_name
  principal_arn     = aws_iam_role.portal_bastion.arn
  type              = "STANDARD"
  kubernetes_groups = ["portal-bastion-group"]
  tags              = var.tags
}

# 6. Allow EKS API server to accept HTTPS traffic from Portal Bastion Security Group
resource "aws_vpc_security_group_ingress_rule" "eks_api_from_portal_bastion" {
  security_group_id            = module.eks.cluster_security_group_id
  referenced_security_group_id = aws_security_group.portal_bastion.id
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
  description                  = "Allow EKS API access from SSM Portal Bastion Host"
}
