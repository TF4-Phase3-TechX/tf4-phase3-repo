# REL-22 - MSK Connect custom plugin artifact storage.
# The S3 Sink connector ZIP is uploaded after this bucket exists, then PR 2
# references the uploaded object version when creating the MSK Connect plugin.

locals {
  msk_connect_plugin_bucket_name = "tf4-msk-connect-plugins-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  msk_connect_plugin_prefix      = "plugins/"
}

resource "aws_s3_bucket" "msk_connect_plugins" {
  bucket        = local.msk_connect_plugin_bucket_name
  force_destroy = false

  tags = merge(var.tags, {
    Name      = "tf4-msk-connect-plugins"
    Component = "msk-connect"
    DataClass = "RuntimePluginArtifact"
    Mandate   = "20"
    Service   = "s3"
    Task      = "CDO08-REL-22"
  })
}

resource "aws_s3_bucket_versioning" "msk_connect_plugins" {
  bucket = aws_s3_bucket.msk_connect_plugins.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "msk_connect_plugins" {
  bucket = aws_s3_bucket.msk_connect_plugins.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_ownership_controls" "msk_connect_plugins" {
  bucket = aws_s3_bucket.msk_connect_plugins.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "msk_connect_plugins" {
  bucket = aws_s3_bucket.msk_connect_plugins.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "msk_connect_plugins_bucket" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.msk_connect_plugins.arn,
      "${aws_s3_bucket.msk_connect_plugins.arn}/*",
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
}

resource "aws_s3_bucket_policy" "msk_connect_plugins" {
  bucket = aws_s3_bucket.msk_connect_plugins.id
  policy = data.aws_iam_policy_document.msk_connect_plugins_bucket.json

  depends_on = [aws_s3_bucket_public_access_block.msk_connect_plugins]
}
