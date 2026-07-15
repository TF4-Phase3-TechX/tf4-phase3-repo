# Owner: Bá Huân CDO07
# Cấu hình bộ ghi, kênh phân phối và thời gian lưu giữ AWS Config cho AUDIT-009 và Task 2.

data "aws_partition" "current" {}

locals {
  aws_config_s3_prefix        = "aws-config"
  aws_config_evidence_prefix  = "${local.aws_config_s3_prefix}/"
  aws_config_expected_account = "511825856493"
  aws_config_retention_days   = 30

  aws_config_resource_types = [
    "AWS::EKS::Cluster",
    "AWS::EKS::Nodegroup",
    "AWS::EKS::Addon",
    "AWS::IAM::Role",
    "AWS::IAM::InstanceProfile",
    "AWS::IAM::Policy",
    "AWS::IAM::OIDCProvider",
    "AWS::EC2::Instance",
    "AWS::EC2::NetworkInterface",
    "AWS::EC2::Volume",
    "AWS::EC2::LaunchTemplate",
    "AWS::EC2::VPC",
    "AWS::EC2::SecurityGroup",
    "AWS::EC2::Subnet",
    "AWS::EC2::RouteTable",
    "AWS::EC2::NetworkAcl",
    "AWS::EC2::NatGateway",
    "AWS::EC2::InternetGateway",
    "AWS::AutoScaling::AutoScalingGroup",
    "AWS::SSM::Document",
    "AWS::SSM::ManagedInstanceInventory",
    "AWS::S3::Bucket",
    "AWS::S3::BucketPolicy",
    "AWS::CloudTrail::Trail",
    "AWS::KMS::Key",
    "AWS::ECR::Repository",
    "AWS::DynamoDB::Table",
    "AWS::Logs::LogGroup",
    "AWS::AccessAnalyzer::Analyzer",
    "AWS::ElasticLoadBalancingV2::LoadBalancer",
    "AWS::ElasticLoadBalancingV2::Listener",
    "AWS::ElasticLoadBalancingV2::TargetGroup",
  ]

  # Người vận hành được phép xem evidence nhưng không được thay đổi dữ liệu trong đường dẫn evidence.
  # Role chạy Terraform không nằm trong danh sách này để mọi thay đổi vẫn phải qua quy trình review IaC.
  aws_config_operator_role_arns = [
    local.eks_admin_access_entries["sso_deploy_operator"],
    local.eks_admin_access_entries["github_actions_deploy"],
  ]

  aws_config_tags = var.tags
}

# AWS Config sử dụng service-linked role này để thu thập cấu hình tài nguyên.
# Quyền ghi dữ liệu vào S3 được cấp riêng qua bucket policy của staging bucket.
resource "aws_iam_service_linked_role" "config" {
  aws_service_name = "config.amazonaws.com"
  description      = "Service-linked role for the TF4 AWS Config change trail"
}

resource "aws_config_configuration_recorder" "main" {
  name     = "tf4-aws-config-recorder"
  role_arn = aws_iam_service_linked_role.config.arn

  recording_group {
    all_supported  = false
    resource_types = local.aws_config_resource_types

    recording_strategy {
      use_only = "INCLUSION_BY_RESOURCE_TYPES"
    }
  }

  recording_mode {
    recording_frequency = "CONTINUOUS"
  }

  lifecycle {
    precondition {
      condition     = data.aws_caller_identity.current.account_id == local.aws_config_expected_account
      error_message = "AUDIT-009 must be deployed only to AWS account 511825856493."
    }

    precondition {
      condition     = var.aws_region == "us-east-1"
      error_message = "AUDIT-009 records global IAM resource types only in us-east-1."
    }
  }
}

resource "aws_config_delivery_channel" "main" {
  name           = "tf4-aws-config-delivery"
  s3_bucket_name = aws_s3_bucket.config_staging.id
  s3_key_prefix  = local.aws_config_s3_prefix

  snapshot_delivery_properties {
    delivery_frequency = "TwentyFour_Hours"
  }

  depends_on = [
    aws_config_configuration_recorder.main,
    aws_s3_bucket_policy.config_staging,
    aws_s3_bucket_replication_configuration.config_archive,
  ]
}

resource "aws_config_retention_configuration" "main" {
  retention_period_in_days = local.aws_config_retention_days

  depends_on = [aws_config_configuration_recorder.main]
}

resource "aws_config_configuration_recorder_status" "main" {
  name       = aws_config_configuration_recorder.main.name
  is_enabled = true

  depends_on = [
    aws_config_delivery_channel.main,
    aws_config_retention_configuration.main,
  ]
}
