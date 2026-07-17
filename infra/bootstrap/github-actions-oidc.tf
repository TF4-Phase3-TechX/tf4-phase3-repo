# Owner: Huy Hoàng nhóm CDO_04
# GitHub Actions OIDC roles for CI-only deployment.
# Bootstrap owns these roles because workflows need account-level trust before app/infra deploys run.

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

data "aws_kms_alias" "cloudtrail" {
  name = "alias/tf4-cloudtrail-key"
}

locals {
  github_org  = "TF4-Phase3-TechX"
  github_repo = "tf4-phase3-repo"

  github_oidc_provider_url = "https://token.actions.githubusercontent.com"
  github_oidc_provider_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"

  github_sub_any  = "repo:${local.github_org}/${local.github_repo}:*"
  github_sub_main = "repo:${local.github_org}/${local.github_repo}:ref:refs/heads/main"

  ecr_repository_arn = "arn:aws:ecr:${var.aws_region}:${data.aws_caller_identity.current.account_id}:repository/techx-corp"
  eks_cluster_arn    = "arn:aws:eks:${var.aws_region}:${data.aws_caller_identity.current.account_id}:cluster/techx-tf4-cluster"
}

resource "aws_iam_openid_connect_provider" "github" {
  url = local.github_oidc_provider_url

  client_id_list = [
    "sts.amazonaws.com"
  ]

  # GitHub Actions OIDC root CA thumbprint.
  # If AWS/GitHub rotate CA, update from AWS docs.
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1"
  ]

  tags = var.tags
}

data "aws_iam_policy_document" "github_actions_pr_trust" {
  statement {
    effect = "Allow"

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    actions = ["sts:AssumeRoleWithWebIdentity"]

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [local.github_sub_any]
    }
  }
}

data "aws_iam_policy_document" "github_actions_main_trust" {
  statement {
    effect = "Allow"

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    actions = ["sts:AssumeRoleWithWebIdentity"]

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [local.github_sub_main]
    }
  }
}

resource "aws_iam_role" "github_actions_plan" {
  name               = "tf4-github-actions-plan"
  assume_role_policy = data.aws_iam_policy_document.github_actions_pr_trust.json
  tags               = var.tags
}

data "aws_iam_policy_document" "github_actions_plan" {
  statement {
    sid    = "ReadTerraformPlanInputs"
    effect = "Allow"

    actions = [
      "autoscaling:Describe*",
      "budgets:ViewBudget",
      "budgets:ListTagsForResource",
      "access-analyzer:GetAnalyzer",
      "cloudtrail:DescribeTrails",
      "cloudtrail:GetEventSelectors",
      "cloudtrail:GetTrail",
      "cloudtrail:GetTrailStatus",
      "cloudtrail:ListTags",
      "config:DescribeConfigurationRecorders",
      "config:DescribeConfigurationRecorderStatus",
      "config:DescribeDeliveryChannels",
      "config:DescribeRetentionConfigurations",
      "ec2:Describe*",
      "ecr:Describe*",
      "ecr:GetLifecyclePolicy",
      "ecr:List*",
      "eks:Describe*",
      "eks:List*",
      "elasticloadbalancing:Describe*",
      "firehose:DescribeDeliveryStream",
      "firehose:ListTagsForDeliveryStream",
      "iam:Get*",
      "iam:List*",
      "kms:DescribeKey",
      "kms:GetKeyPolicy",
      "kms:GetKeyRotationStatus",
      "kms:ListAliases",
      "kms:ListResourceTags",
      "logs:Describe*",
      "logs:ListTagsForResource",
      "s3:GetAccelerateConfiguration",
      "s3:GetBucket*",
      "s3:GetEncryptionConfiguration",
      "s3:GetLifecycleConfiguration",
      "s3:GetReplicationConfiguration",
      "s3:ListBucket"
    ]

    resources = ["*"]
  }

  statement {
    sid       = "ReadSecureSlackWebhookParameter"
    effect    = "Allow"
    actions   = ["ssm:GetParameter"]
    resources = ["arn:${data.aws_partition.current.partition}:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/security-alerts/slack-webhook-url"]
  }

  statement {
    sid       = "DecryptCloudTrailSecureString"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = [data.aws_kms_alias.cloudtrail.target_key_arn]
  }

  statement {
    sid    = "ReadKubernetesHelmReleaseState"
    effect = "Allow"

    actions = [
      "eks:AccessKubernetesApi",
      "eks:DescribeCluster"
    ]

    resources = [local.eks_cluster_arn]
  }

  statement {
    sid    = "ReadTerraformStateBackend"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:ListBucket",
      "dynamodb:DescribeTable",
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:Scan"
    ]

    resources = [
      aws_s3_bucket.terraform_state.arn,
      "${aws_s3_bucket.terraform_state.arn}/*",
      aws_dynamodb_table.terraform_locks.arn
    ]
  }
}

resource "aws_iam_policy" "github_actions_plan" {
  name   = "tf4-github-actions-plan"
  policy = data.aws_iam_policy_document.github_actions_plan.json
  tags   = var.tags
}

resource "aws_iam_role_policy_attachment" "github_actions_plan" {
  role       = aws_iam_role.github_actions_plan.name
  policy_arn = aws_iam_policy.github_actions_plan.arn
}


resource "aws_iam_role" "github_actions_build" {
  name               = "tf4-github-actions-ecr-build"
  assume_role_policy = data.aws_iam_policy_document.github_actions_main_trust.json
  tags               = var.tags
}

data "aws_iam_policy_document" "github_actions_build" {
  statement {
    sid       = "EcrAuth"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "PushPullTechxImages"
    effect = "Allow"

    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeImages",
      "ecr:DescribeRepositories",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:ListImages",
      "ecr:PutImage",
      "ecr:UploadLayerPart"
    ]

    resources = [local.ecr_repository_arn]
  }
}

resource "aws_iam_policy" "github_actions_build" {
  name   = "tf4-github-actions-ecr-build"
  policy = data.aws_iam_policy_document.github_actions_build.json
  tags   = var.tags
}

resource "aws_iam_role_policy_attachment" "github_actions_build" {
  role       = aws_iam_role.github_actions_build.name
  policy_arn = aws_iam_policy.github_actions_build.arn
}

resource "aws_iam_role" "github_actions_deploy" {
  name               = "tf4-github-actions-eks-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_actions_main_trust.json
  tags               = var.tags
}

data "aws_iam_policy_document" "github_actions_deploy" {
  statement {
    sid       = "DescribeEksCluster"
    effect    = "Allow"
    actions   = ["eks:DescribeCluster"]
    resources = [local.eks_cluster_arn]
  }
}

resource "aws_iam_policy" "github_actions_deploy" {
  name   = "tf4-github-actions-eks-deploy"
  policy = data.aws_iam_policy_document.github_actions_deploy.json
  tags   = var.tags
}

resource "aws_iam_role_policy_attachment" "github_actions_deploy" {
  role       = aws_iam_role.github_actions_deploy.name
  policy_arn = aws_iam_policy.github_actions_deploy.arn
}

resource "aws_iam_role" "github_actions_terraform_apply" {
  name               = "tf4-github-actions-terraform-apply"
  assume_role_policy = data.aws_iam_policy_document.github_actions_main_trust.json
  tags               = var.tags
}

# Bootstrap role can mutate bootstrap state backend and GitHub OIDC IAM.
# Infra apply role can mutate broad infra. Scope down later after first stable apply evidence.
resource "aws_iam_role_policy_attachment" "github_actions_terraform_apply_poweruser" {
  role       = aws_iam_role.github_actions_terraform_apply.name
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}

resource "aws_iam_role_policy_attachment" "github_actions_terraform_apply_iam" {
  role       = aws_iam_role.github_actions_terraform_apply.name
  policy_arn = "arn:aws:iam::aws:policy/IAMFullAccess"
}
