# REL-22 - MSK orders S3 archive bucket.
# Stores orders topic events outside MSK so REL-25 can replay after cluster/topic loss.

locals {
  msk_orders_archive_bucket_name = "tf4-msk-orders-archive-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  msk_orders_archive_prefix      = "orders/"

  # Expected MSK Connect S3 Sink path. Subtask 3 owns the connector config.
  msk_orders_archive_partition_convention = "orders/topic=orders/year=YYYY/month=MM/day=DD/hour=HH/"

  # Normal operators can inspect evidence through approved read paths, but archive
  # mutation/deletion should go through reviewed Terraform or a break-glass process.
  msk_orders_archive_operator_role_arns = [
    local.eks_admin_access_entries["github_actions_deploy"],
    local.eks_admin_access_entries["sso_deploy_operator"],
    local.eks_admin_access_entries["sso_security_iam_manager"],
  ]
}

resource "aws_s3_bucket" "msk_orders_archive" {
  bucket        = local.msk_orders_archive_bucket_name
  force_destroy = false

  tags = merge(var.tags, {
    Name      = "tf4-msk-orders-archive"
    Component = "msk-orders"
    DataClass = "OrderEventArchive"
    Mandate   = "20"
    Service   = "s3"
    Task      = "CDO08-REL-22"
    Retention = "35-days"
  })
}

resource "aws_s3_bucket_versioning" "msk_orders_archive" {
  bucket = aws_s3_bucket.msk_orders_archive.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "msk_orders_archive" {
  bucket = aws_s3_bucket.msk_orders_archive.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_ownership_controls" "msk_orders_archive" {
  bucket = aws_s3_bucket.msk_orders_archive.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "msk_orders_archive" {
  bucket = aws_s3_bucket.msk_orders_archive.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "msk_orders_archive" {
  bucket = aws_s3_bucket.msk_orders_archive.id

  rule {
    id     = "orders-archive-7-day-standard-35-day-retention"
    status = "Enabled"

    filter {
      prefix = local.msk_orders_archive_prefix
    }

    transition {
      days          = 7
      storage_class = "STANDARD_IA"
    }

    expiration {
      days = 35
    }

    noncurrent_version_expiration {
      noncurrent_days = 35
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  depends_on = [aws_s3_bucket_versioning.msk_orders_archive]
}

data "aws_iam_policy_document" "msk_orders_archive_bucket" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.msk_orders_archive.arn,
      "${aws_s3_bucket.msk_orders_archive.arn}/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  statement {
    sid    = "DenyOperatorArchiveControlDeletion"
    effect = "Deny"
    actions = [
      "s3:DeleteBucket",
      "s3:DeleteBucketPolicy",
      "s3:PutBucketPolicy",
      "s3:PutBucketPublicAccessBlock",
      "s3:PutBucketVersioning",
      "s3:PutEncryptionConfiguration",
      "s3:PutLifecycleConfiguration",
    ]
    resources = [aws_s3_bucket.msk_orders_archive.arn]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:PrincipalArn"
      values   = local.msk_orders_archive_operator_role_arns
    }
  }

  statement {
    sid    = "DenyOperatorArchiveObjectDeletion"
    effect = "Deny"
    actions = [
      "s3:DeleteObject",
      "s3:DeleteObjectTagging",
      "s3:DeleteObjectVersion",
    ]
    resources = ["${aws_s3_bucket.msk_orders_archive.arn}/${local.msk_orders_archive_prefix}*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:PrincipalArn"
      values   = local.msk_orders_archive_operator_role_arns
    }
  }
}

resource "aws_s3_bucket_policy" "msk_orders_archive" {
  bucket = aws_s3_bucket.msk_orders_archive.id
  policy = data.aws_iam_policy_document.msk_orders_archive_bucket.json

  depends_on = [aws_s3_bucket_public_access_block.msk_orders_archive]
}
