# REL-22 fallback foundation - self-managed Kafka Connect on EKS.
# This role is intentionally limited to writing archived orders objects only.

data "aws_iam_policy_document" "msk_orders_kafka_connect_archive_s3_write" {
  statement {
    sid       = "GetOrdersArchiveBucketLocation"
    effect    = "Allow"
    actions   = ["s3:GetBucketLocation"]
    resources = [aws_s3_bucket.msk_orders_archive.arn]
  }

  statement {
    sid    = "ListOrdersArchivePrefix"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:ListBucketMultipartUploads",
    ]
    resources = [aws_s3_bucket.msk_orders_archive.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        local.msk_orders_archive_prefix,
        "${local.msk_orders_archive_prefix}*",
      ]
    }
  }

  statement {
    sid    = "WriteOrdersArchiveObjects"
    effect = "Allow"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
      "s3:PutObject",
    ]
    resources = ["${aws_s3_bucket.msk_orders_archive.arn}/${local.msk_orders_archive_prefix}*"]
  }
}

resource "aws_iam_policy" "msk_orders_kafka_connect_archive_s3_write" {
  name        = "techx-tf4-orders-kafka-connect-archive-s3-write"
  description = "Least-privilege S3 write access for REL-22 self-managed Kafka Connect orders archive"
  policy      = data.aws_iam_policy_document.msk_orders_kafka_connect_archive_s3_write.json

  tags = merge(var.tags, {
    Name      = "techx-tf4-orders-kafka-connect-archive-s3-write"
    Component = "kafka-connect"
    Mandate   = "20"
    Task      = "CDO08-REL-22"
  })
}

module "msk_orders_kafka_connect_archive_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name = "techx-tf4-orders-kafka-connect-archive"
  role_policy_arns = {
    orders_archive_s3_write = aws_iam_policy.msk_orders_kafka_connect_archive_s3_write.arn
  }
  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["techx-tf4:kafka-connect-orders-archive"]
    }
  }

  tags = merge(var.tags, {
    Name      = "techx-tf4-orders-kafka-connect-archive"
    Component = "kafka-connect"
    Mandate   = "20"
    Task      = "CDO08-REL-22"
  })
}

