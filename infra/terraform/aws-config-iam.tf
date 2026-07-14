# Owner: Bá Huân CDO07
# IAM đặc quyền tối thiểu cho replication và các rào chắn bảo vệ bucket evidence AWS Config.

data "aws_iam_policy_document" "config_replication_assume_role" {
  statement {
    sid     = "AllowS3ReplicationAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "config_replication" {
  name               = "tf4-aws-config-worm-replication"
  assume_role_policy = data.aws_iam_policy_document.config_replication_assume_role.json

  tags = local.aws_config_tags
}

data "aws_iam_policy_document" "config_replication" {
  statement {
    sid       = "ReadReplicationConfiguration"
    effect    = "Allow"
    actions   = ["s3:GetReplicationConfiguration"]
    resources = [aws_s3_bucket.config_staging.arn]
  }

  statement {
    sid       = "ListConfigEvidencePrefix"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.config_staging.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        local.aws_config_s3_prefix,
        local.aws_config_evidence_prefix,
        "${local.aws_config_evidence_prefix}*",
      ]
    }
  }

  statement {
    sid    = "ReadConfigEvidenceVersions"
    effect = "Allow"
    actions = [
      "s3:GetObjectLegalHold",
      "s3:GetObjectRetention",
      "s3:GetObjectVersionAcl",
      "s3:GetObjectVersionForReplication",
      "s3:GetObjectVersionTagging",
    ]
    resources = ["${aws_s3_bucket.config_staging.arn}/${local.aws_config_evidence_prefix}*"]
  }

  statement {
    sid    = "WriteImmutableConfigReplicas"
    effect = "Allow"
    actions = [
      "s3:ReplicateObject",
      "s3:ReplicateTags",
    ]
    resources = ["${aws_s3_bucket.config_archive.arn}/${local.aws_config_evidence_prefix}*"]
  }
}

resource "aws_iam_role_policy" "config_replication" {
  name   = "tf4-aws-config-worm-replication"
  role   = aws_iam_role.config_replication.id
  policy = data.aws_iam_policy_document.config_replication.json
}

data "aws_iam_policy_document" "config_staging_bucket" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.config_staging.arn,
      "${aws_s3_bucket.config_staging.arn}/*",
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
    sid    = "DenyOperatorBucketControlChanges"
    effect = "Deny"
    actions = [
      "s3:DeleteBucket",
      "s3:DeleteBucketPolicy",
      "s3:PutBucketNotification",
      "s3:PutBucketOwnershipControls",
      "s3:PutBucketPolicy",
      "s3:PutBucketPublicAccessBlock",
      "s3:PutBucketVersioning",
      "s3:PutEncryptionConfiguration",
      "s3:PutLifecycleConfiguration",
      "s3:PutReplicationConfiguration",
    ]
    resources = [aws_s3_bucket.config_staging.arn]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:PrincipalArn"
      values   = local.aws_config_operator_role_arns
    }
  }

  statement {
    sid    = "DenyOperatorEvidenceMutation"
    effect = "Deny"
    actions = [
      "s3:DeleteObject",
      "s3:DeleteObjectTagging",
      "s3:DeleteObjectVersion",
      "s3:PutObject",
      "s3:PutObjectAcl",
      "s3:PutObjectTagging",
    ]
    resources = ["${aws_s3_bucket.config_staging.arn}/${local.aws_config_evidence_prefix}*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:PrincipalArn"
      values   = local.aws_config_operator_role_arns
    }
  }

  statement {
    sid       = "AWSConfigBucketPermissionsCheck"
    effect    = "Allow"
    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.config_staging.arn]

    principals {
      type        = "Service"
      identifiers = ["config.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "AWS:SourceArn"
      values = [
        "arn:${data.aws_partition.current.partition}:config:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*",
      ]
    }
  }

  statement {
    sid       = "AWSConfigBucketExistenceCheck"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.config_staging.arn]

    principals {
      type        = "Service"
      identifiers = ["config.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "AWS:SourceArn"
      values = [
        "arn:${data.aws_partition.current.partition}:config:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*",
      ]
    }
  }

  statement {
    sid     = "AWSConfigBucketDelivery"
    effect  = "Allow"
    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.config_staging.arn}/${local.aws_config_s3_prefix}/AWSLogs/${data.aws_caller_identity.current.account_id}/Config/*",
    ]

    principals {
      type        = "Service"
      identifiers = ["config.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "AWS:SourceArn"
      values = [
        "arn:${data.aws_partition.current.partition}:config:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*",
      ]
    }
  }
}

resource "aws_s3_bucket_policy" "config_staging" {
  bucket = aws_s3_bucket.config_staging.id
  policy = data.aws_iam_policy_document.config_staging_bucket.json

  depends_on = [aws_s3_bucket_public_access_block.config_staging]
}

data "aws_iam_policy_document" "config_archive_bucket" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.config_archive.arn,
      "${aws_s3_bucket.config_archive.arn}/*",
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
    sid    = "DenyOperatorArchiveControlChanges"
    effect = "Deny"
    actions = [
      "s3:DeleteBucket",
      "s3:DeleteBucketPolicy",
      "s3:PutBucketObjectLockConfiguration",
      "s3:PutBucketOwnershipControls",
      "s3:PutBucketPolicy",
      "s3:PutBucketPublicAccessBlock",
      "s3:PutBucketVersioning",
      "s3:PutEncryptionConfiguration",
      "s3:PutLifecycleConfiguration",
    ]
    resources = [aws_s3_bucket.config_archive.arn]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:PrincipalArn"
      values   = local.aws_config_operator_role_arns
    }
  }

  statement {
    sid    = "DenyOperatorArchiveMutation"
    effect = "Deny"
    actions = [
      "s3:BypassGovernanceRetention",
      "s3:DeleteObject",
      "s3:DeleteObjectTagging",
      "s3:DeleteObjectVersion",
      "s3:PutObject",
      "s3:PutObjectAcl",
      "s3:PutObjectLegalHold",
      "s3:PutObjectRetention",
      "s3:PutObjectTagging",
    ]
    resources = ["${aws_s3_bucket.config_archive.arn}/${local.aws_config_evidence_prefix}*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:PrincipalArn"
      values   = local.aws_config_operator_role_arns
    }
  }
}

resource "aws_s3_bucket_policy" "config_archive" {
  bucket = aws_s3_bucket.config_archive.id
  policy = data.aws_iam_policy_document.config_archive_bucket.json

  depends_on = [
    aws_s3_bucket_object_lock_configuration.config_archive,
    aws_s3_bucket_public_access_block.config_archive,
  ]
}
