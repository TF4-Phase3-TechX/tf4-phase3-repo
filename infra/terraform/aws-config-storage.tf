# Owner: Bá Huân CDO07
# Lưu evidence AWS Config qua staging bucket có versioning và archive bucket WORM bất biến.

resource "aws_s3_bucket" "config_staging" {
  bucket        = "tf4-aws-config-staging-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  force_destroy = false

  tags = merge(local.aws_config_tags, {
    Name         = "tf4-aws-config-staging"
    DataClass    = "AuditEvidenceStaging"
    Immutability = "Versioned"
  })
}

resource "aws_s3_bucket_versioning" "config_staging" {
  bucket = aws_s3_bucket.config_staging.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "config_staging" {
  bucket = aws_s3_bucket.config_staging.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_ownership_controls" "config_staging" {
  bucket = aws_s3_bucket.config_staging.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "config_staging" {
  bucket = aws_s3_bucket.config_staging.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Giữ evidence tại staging đủ 30 ngày để kiểm tra replication và xử lý sự cố.
# S3 không chạy expiration khi object vẫn ở trạng thái replication PENDING hoặc FAILED.
resource "aws_s3_bucket_lifecycle_configuration" "config_staging" {
  bucket = aws_s3_bucket.config_staging.id

  rule {
    id     = "expire-config-evidence-after-retention"
    status = "Enabled"

    filter {
      prefix = local.aws_config_evidence_prefix
    }

    expiration {
      days = local.aws_config_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 1
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "remove-expired-config-delete-markers"
    status = "Enabled"

    filter {
      prefix = local.aws_config_evidence_prefix
    }

    expiration {
      expired_object_delete_marker = true
    }
  }

  depends_on = [aws_s3_bucket_versioning.config_staging]
}

resource "aws_s3_bucket" "config_archive" {
  bucket              = "tf4-aws-config-worm-archive-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  force_destroy       = false
  object_lock_enabled = true

  tags = merge(local.aws_config_tags, {
    Name         = "tf4-aws-config-worm-archive"
    DataClass    = "ImmutableAuditEvidence"
    Immutability = "WORM-COMPLIANCE"
  })
}

resource "aws_s3_bucket_versioning" "config_archive" {
  bucket = aws_s3_bucket.config_archive.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "config_archive" {
  bucket = aws_s3_bucket.config_archive.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_ownership_controls" "config_archive" {
  bucket = aws_s3_bucket.config_archive.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "config_archive" {
  bucket = aws_s3_bucket.config_archive.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_object_lock_configuration" "config_archive" {
  bucket              = aws_s3_bucket.config_archive.id
  object_lock_enabled = "Enabled"

  rule {
    default_retention {
      mode = "COMPLIANCE"
      days = local.aws_config_retention_days
    }
  }

  depends_on = [aws_s3_bucket_versioning.config_archive]
}

# Lifecycle chỉ dọn phiên bản archive sau khi thời hạn COMPLIANCE kết thúc.
# Expiration tạo delete marker; noncurrent expiration mới xóa vật lý phiên bản đã hết khóa.
resource "aws_s3_bucket_lifecycle_configuration" "config_archive" {
  bucket = aws_s3_bucket.config_archive.id

  rule {
    id     = "expire-worm-evidence-after-retention"
    status = "Enabled"

    filter {
      prefix = local.aws_config_evidence_prefix
    }

    expiration {
      days = local.aws_config_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 1
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "remove-expired-worm-delete-markers"
    status = "Enabled"

    filter {
      prefix = local.aws_config_evidence_prefix
    }

    expiration {
      expired_object_delete_marker = true
    }
  }

  depends_on = [
    aws_s3_bucket_object_lock_configuration.config_archive,
    aws_s3_bucket_versioning.config_archive,
  ]
}

resource "aws_s3_bucket_replication_configuration" "config_archive" {
  bucket = aws_s3_bucket.config_staging.id
  role   = aws_iam_role.config_replication.arn

  rule {
    id       = "replicate-aws-config-to-worm-archive"
    priority = 1
    status   = "Enabled"

    delete_marker_replication {
      status = "Disabled"
    }

    filter {
      prefix = local.aws_config_evidence_prefix
    }

    destination {
      bucket        = aws_s3_bucket.config_archive.arn
      storage_class = "STANDARD"

      metrics {
        status = "Enabled"

        event_threshold {
          minutes = 15
        }
      }
    }
  }

  depends_on = [
    aws_iam_role_policy.config_replication,
    aws_s3_bucket_policy.config_archive,
    aws_s3_bucket_policy.config_staging,
    aws_s3_bucket_ownership_controls.config_archive,
    aws_s3_bucket_ownership_controls.config_staging,
    aws_s3_bucket_server_side_encryption_configuration.config_archive,
    aws_s3_bucket_server_side_encryption_configuration.config_staging,
    aws_s3_bucket_versioning.config_archive,
    aws_s3_bucket_versioning.config_staging,
  ]
}
