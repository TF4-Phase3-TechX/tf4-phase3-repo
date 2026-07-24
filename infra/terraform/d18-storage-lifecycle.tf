resource "aws_iam_role" "ebs_snapshot_lifecycle" {
  name = "tf4-d18-ebs-snapshot-lifecycle"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "dlm.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ebs_snapshot_lifecycle" {
  role       = aws_iam_role.ebs_snapshot_lifecycle.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSDataLifecycleManagerServiceRole"
}

resource "aws_dlm_lifecycle_policy" "ebs_recovery" {
  description        = "D18 daily recovery snapshots for explicitly tagged EBS volumes"
  execution_role_arn = aws_iam_role.ebs_snapshot_lifecycle.arn
  state              = "ENABLED"

  policy_details {
    resource_types = ["VOLUME"]
    target_tags = {
      D18Snapshot = "true"
    }

    schedule {
      name = "Daily snapshots retained for seven days"

      create_rule {
        interval      = 24
        interval_unit = "HOURS"
        times         = ["23:15"]
      }

      retain_rule {
        count = 7
      }

      tags_to_add = {
        ManagedBy  = "DLM"
        Purpose    = "recovery"
        Workstream = "D18-WS2"
      }

      copy_tags = true
    }
  }

  depends_on = [aws_iam_role_policy_attachment.ebs_snapshot_lifecycle]
}

resource "aws_s3_bucket_lifecycle_configuration" "cloudtrail_logs" {
  bucket = aws_s3_bucket.cloudtrail_logs.id

  rule {
    id     = "archive-and-expire-after-compliance-floor"
    status = "Enabled"

    filter {}

    transition {
      days          = 91
      storage_class = "GLACIER_IR"
    }

    expiration {
      days = 365
    }

    noncurrent_version_transition {
      noncurrent_days = 91
      storage_class   = "GLACIER_IR"
    }

    noncurrent_version_expiration {
      noncurrent_days = 365
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [
    aws_s3_bucket_object_lock_configuration.cloudtrail_logs,
    aws_s3_bucket_versioning.cloudtrail_logs_versioning
  ]
}

resource "aws_s3_bucket_lifecycle_configuration" "eks_audit_logs" {
  bucket = aws_s3_bucket.eks_audit_logs.id

  rule {
    id     = "archive-and-expire-after-compliance-floor"
    status = "Enabled"

    filter {}

    transition {
      days          = 91
      storage_class = "GLACIER_IR"
    }

    expiration {
      days = 365
    }

    noncurrent_version_transition {
      noncurrent_days = 91
      storage_class   = "GLACIER_IR"
    }

    noncurrent_version_expiration {
      noncurrent_days = 365
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [
    aws_s3_bucket_object_lock_configuration.eks_audit_logs,
    aws_s3_bucket_versioning.eks_audit_logs_versioning
  ]
}
