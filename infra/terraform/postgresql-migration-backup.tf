# REL-15 - PostgreSQL migration backup bucket.
# Stores pre-cutover dumps outside the PostgreSQL pod with a 7-day retention window.

locals {
  postgresql_migration_backup_bucket_name = "tf4-postgresql-migration-backups-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  postgresql_migration_backup_prefix      = "rel15/"
}

resource "aws_s3_bucket" "postgresql_migration_backups" {
  bucket        = local.postgresql_migration_backup_bucket_name
  force_destroy = false

  tags = merge(var.tags, {
    Name      = "tf4-postgresql-migration-backups"
    Component = "postgresql"
    DataClass = "MigrationBackup"
    Mandate   = "08"
    Service   = "s3"
    Task      = "CDO08-REL-15"
  })
}

resource "aws_s3_bucket_versioning" "postgresql_migration_backups" {
  bucket = aws_s3_bucket.postgresql_migration_backups.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "postgresql_migration_backups" {
  bucket = aws_s3_bucket.postgresql_migration_backups.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_ownership_controls" "postgresql_migration_backups" {
  bucket = aws_s3_bucket.postgresql_migration_backups.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "postgresql_migration_backups" {
  bucket = aws_s3_bucket.postgresql_migration_backups.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "postgresql_migration_backups" {
  bucket = aws_s3_bucket.postgresql_migration_backups.id

  rule {
    id     = "expire-rel15-postgresql-backups-after-7-days"
    status = "Enabled"

    filter {
      prefix = local.postgresql_migration_backup_prefix
    }

    expiration {
      days = 7
    }

    noncurrent_version_expiration {
      noncurrent_days = 1
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  depends_on = [aws_s3_bucket_versioning.postgresql_migration_backups]
}
