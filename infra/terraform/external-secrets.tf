# CDO08-SEC-01: External Secrets Operator + AWS Secrets Manager + IRSA.
# Terraform manages secret metadata and access plumbing only. Secret values are
# intentionally loaded out-of-band by an approved admin.

locals {
  app_namespace                   = "techx-tf4"
  external_secrets_namespace      = "external-secrets"
  external_secrets_serviceaccount = "external-secrets-sa"

  cdo08_app_secret_specs = {
    accounting_db_connection_string = {
      name        = "tf4/techx-tf4/accounting/db-connection-string"
      description = "Accounting service DB connection string for TF4"
      service     = "accounting"
      purpose     = "db-connection-string"
    }
    product_catalog_db_connection_string = {
      name        = "tf4/techx-tf4/product-catalog/db-connection-string"
      description = "Product Catalog service DB connection string for TF4"
      service     = "product-catalog"
      purpose     = "db-connection-string"
    }
    product_reviews_db_connection_string = {
      name        = "tf4/techx-tf4/product-reviews/db-connection-string"
      description = "Product Reviews service DB connection string for TF4"
      service     = "product-reviews"
      purpose     = "db-connection-string"
    }
    product_reviews_openai_api_key = {
      name        = "tf4/techx-tf4/product-reviews/openai-api-key"
      description = "Product Reviews OpenAI API key for TF4"
      service     = "product-reviews"
      purpose     = "openai-api-key"
    }
    postgresql_postgres_password = {
      name        = "tf4/techx-tf4/postgresql/postgres-password"
      description = "PostgreSQL admin password for TF4"
      service     = "postgresql"
      purpose     = "postgres-password"
    }
  }

  eks_oidc_provider_url = replace(module.eks.cluster_oidc_issuer_url, "https://", "")
}

resource "aws_secretsmanager_secret" "cdo08_app" {
  for_each = local.cdo08_app_secret_specs

  name                    = each.value.name
  description             = each.value.description
  recovery_window_in_days = 7

  tags = merge(var.tags, {
    Name            = each.value.name
    Team            = "CDO08"
    SecurityFinding = "CDO08-SEC-01"
    Namespace       = local.app_namespace
    Service         = each.value.service
    SecretPurpose   = each.value.purpose
  })
}

data "aws_iam_policy_document" "external_secrets_reader" {
  statement {
    sid    = "ReadCdo08AppSecrets"
    effect = "Allow"

    actions = [
      "secretsmanager:DescribeSecret",
      "secretsmanager:GetSecretValue",
    ]

    resources = [for secret in aws_secretsmanager_secret.cdo08_app : secret.arn]
  }
}

resource "aws_iam_policy" "external_secrets_reader" {
  name        = "tf4-cdo08-external-secrets-reader"
  description = "Least-privilege read access for CDO08 app secrets synced by External Secrets Operator"
  policy      = data.aws_iam_policy_document.external_secrets_reader.json

  tags = merge(var.tags, {
    Name            = "tf4-cdo08-external-secrets-reader"
    Team            = "CDO08"
    SecurityFinding = "CDO08-SEC-01"
  })
}

data "aws_iam_policy_document" "external_secrets_assume_role" {
  statement {
    sid     = "AllowEksServiceAccountAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [module.eks.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.eks_oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.eks_oidc_provider_url}:sub"
      values   = ["system:serviceaccount:${local.app_namespace}:${local.external_secrets_serviceaccount}"]
    }
  }
}

resource "aws_iam_role" "external_secrets_reader" {
  name               = "tf4-cdo08-external-secrets-reader"
  assume_role_policy = data.aws_iam_policy_document.external_secrets_assume_role.json

  tags = merge(var.tags, {
    Name            = "tf4-cdo08-external-secrets-reader"
    Team            = "CDO08"
    SecurityFinding = "CDO08-SEC-01"
  })
}

resource "aws_iam_role_policy_attachment" "external_secrets_reader" {
  role       = aws_iam_role.external_secrets_reader.name
  policy_arn = aws_iam_policy.external_secrets_reader.arn
}

resource "helm_release" "external_secrets" {
  name             = "external-secrets"
  repository       = "https://charts.external-secrets.io"
  chart            = "external-secrets"
  version          = "2.7.0"
  namespace        = local.external_secrets_namespace
  create_namespace = true

  set {
    name  = "installCRDs"
    value = "true"
  }
}

resource "kubernetes_service_account_v1" "external_secrets_app" {
  metadata {
    name      = local.external_secrets_serviceaccount
    namespace = local.app_namespace

    annotations = {
      "eks.amazonaws.com/role-arn" = aws_iam_role.external_secrets_reader.arn
    }

    labels = {
      "app.kubernetes.io/name"       = local.external_secrets_serviceaccount
      "app.kubernetes.io/part-of"    = "techx-corp"
      "app.kubernetes.io/managed-by" = "terraform"
      "cdo08.techx.io/finding"       = "CDO08-SEC-01"
    }
  }

  depends_on = [
    helm_release.external_secrets,
    aws_iam_role_policy_attachment.external_secrets_reader,
  ]
}
