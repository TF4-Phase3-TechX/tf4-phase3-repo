# Terraform owns Kyverno's AWS IRSA identity only. Argo CD owns the Kyverno controller.
# Required by the require-signed-techx-images ImageValidatingPolicy (platform/admission/
# require-signed-techx-images.yaml in the gitops repo), which needs to call ECR to fetch
# image manifests/signatures during admission review.
resource "aws_iam_policy" "kyverno_ecr_read" {
  name = "kyverno-ecr-read-production"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchCheckLayerAvailability"
        ]
        Resource = [
          "arn:aws:ecr:${var.aws_region}:${data.aws_caller_identity.current.account_id}:repository/techx-corp"
        ]
      }
    ]
  })
}

module "kyverno_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name = "kyverno-${var.cluster_name}"
  role_policy_arns = {
    kyverno_ecr_read = aws_iam_policy.kyverno_ecr_read.arn
  }
  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kyverno:kyverno-admission-controller"]
    }
  }
}
