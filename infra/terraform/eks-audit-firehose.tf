# Owner: Nhóm CDO07 (Audit)
# Mục đích: Stream EKS Control Plane logs (audit, authenticator) từ CloudWatch Logs 
# sang S3 bucket bảo vệ bởi S3 Object Lock COMPLIANCE 90 ngày (WORM),
# đảm bảo logs không thể bị sửa/xóa kể cả bởi root account.

# 1. S3 Bucket nhận logs với Object Lock enabled từ đầu
resource "aws_s3_bucket" "eks_audit_logs" {
  bucket              = "tf4-eks-audit-logs-${data.aws_caller_identity.current.account_id}"
  force_destroy       = false
  object_lock_enabled = true

  tags = var.tags
}

# Object Lock Configuration: COMPLIANCE mode, 90 ngày retention
resource "aws_s3_bucket_object_lock_configuration" "eks_audit_logs" {
  bucket = aws_s3_bucket.eks_audit_logs.id

  rule {
    default_retention {
      mode = "COMPLIANCE"
      days = 90
    }
  }
}

# Versioning bắt buộc phải bật khi dùng Object Lock
resource "aws_s3_bucket_versioning" "eks_audit_logs_versioning" {
  bucket = aws_s3_bucket.eks_audit_logs.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Mã hóa mặc định SSE-S3 (AES256) tránh phát sinh chi phí KMS API call
resource "aws_s3_bucket_server_side_encryption_configuration" "eks_audit_logs_encryption" {
  bucket = aws_s3_bucket.eks_audit_logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# Chặn public access hoàn toàn
resource "aws_s3_bucket_public_access_block" "eks_audit_logs_public_block" {
  bucket = aws_s3_bucket.eks_audit_logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Bucket Policy bảo vệ logs
resource "aws_s3_bucket_policy" "eks_audit_logs_policy" {
  bucket = aws_s3_bucket.eks_audit_logs.id

  depends_on = [
    aws_s3_bucket_public_access_block.eks_audit_logs_public_block
  ]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DenyNonAdminDeleteObject"
        Effect = "Deny"
        Principal = {
          AWS = "*"
        }
        Action = [
          "s3:DeleteObject",
          "s3:DeleteObjectVersion"
        ]
        Resource = "${aws_s3_bucket.eks_audit_logs.arn}/*"
        Condition = {
          StringNotEquals = {
            "aws:PrincipalArn" = [
              "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root",
              "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/tf4-github-actions-terraform-apply"
            ]
          }
        }
      },
      {
        Sid    = "DenyDeleteBucket"
        Effect = "Deny"
        Principal = {
          AWS = "*"
        }
        Action   = "s3:DeleteBucket"
        Resource = aws_s3_bucket.eks_audit_logs.arn
        Condition = {
          StringNotEquals = {
            "aws:PrincipalArn" = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
          }
        }
      },
      {
        Sid    = "DenyDisableVersioning"
        Effect = "Deny"
        Principal = {
          AWS = "*"
        }
        Action   = "s3:PutBucketVersioning"
        Resource = aws_s3_bucket.eks_audit_logs.arn
        Condition = {
          StringNotEquals = {
            "aws:PrincipalArn" = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
          }
        }
      },
      {
        Sid    = "DenyHTTPInsecureTransport"
        Effect = "Deny"
        Principal = {
          AWS = "*"
        }
        Action = "s3:*"
        Resource = [
          aws_s3_bucket.eks_audit_logs.arn,
          "${aws_s3_bucket.eks_audit_logs.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}

# 2. CloudWatch Log Group & Log Stream cho Firehose error logging
resource "aws_cloudwatch_log_group" "firehose_delivery_errors" {
  name              = "/aws/firehose/tf4-eks-audit-logs-errors"
  retention_in_days = 14
  tags              = var.tags
}

resource "aws_cloudwatch_log_stream" "firehose_s3_delivery" {
  name           = "S3Delivery"
  log_group_name = aws_cloudwatch_log_group.firehose_delivery_errors.name
}

# 3. IAM Role cho Firehose ghi logs vào S3 và CWL
resource "aws_iam_role" "firehose_to_s3" {
  name = "tf4-firehose-to-s3-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "firehose.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "firehose_to_s3_policy" {
  name = "tf4-firehose-to-s3-policy"
  role = aws_iam_role.firehose_to_s3.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowS3Actions"
        Effect = "Allow"
        Action = [
          "s3:AbortMultipartUpload",
          "s3:GetBucketLocation",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:ListBucketMultipartUploads",
          "s3:PutObject"
        ]
        Resource = [
          aws_s3_bucket.eks_audit_logs.arn,
          "${aws_s3_bucket.eks_audit_logs.arn}/*"
        ]
      },
      {
        Sid    = "AllowCloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.firehose_delivery_errors.arn}:*"
      }
    ]
  })
}

# 4. Amazon Data Firehose Delivery Stream
resource "aws_kinesis_firehose_delivery_stream" "eks_audit_logs" {
  name        = "tf4-eks-audit-logs-firehose"
  destination = "extended_s3"

  extended_s3_configuration {
    role_arn   = aws_iam_role.firehose_to_s3.arn
    bucket_arn = aws_s3_bucket.eks_audit_logs.arn

    buffering_size     = 5  # MB (1-128)
    buffering_interval = 60 # Seconds (60-900)
    compression_format = "GZIP"

    cloudwatch_logging_options {
      enabled         = true
      log_group_name  = aws_cloudwatch_log_group.firehose_delivery_errors.name
      log_stream_name = aws_cloudwatch_log_stream.firehose_s3_delivery.name
    }
  }

  tags = var.tags
}

# 5. IAM Role cho CloudWatch Logs ghi log vào Firehose
resource "aws_iam_role" "cwl_to_firehose" {
  name = "tf4-cwl-to-firehose-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "logs.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "cwl_to_firehose_policy" {
  name = "tf4-cwl-to-firehose-policy"
  role = aws_iam_role.cwl_to_firehose.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowPutRecordFirehose"
        Effect = "Allow"
        Action = [
          "firehose:PutRecord",
          "firehose:PutRecordBatch"
        ]
        Resource = aws_kinesis_firehose_delivery_stream.eks_audit_logs.arn
      }
    ]
  })
}

# 6. CloudWatch Subscription Filter để stream logs từ EKS log group sang Firehose
resource "aws_cloudwatch_log_subscription_filter" "eks_audit_logs" {
  name            = "tf4-eks-audit-logs-subscription"
  log_group_name  = "/aws/eks/${var.cluster_name}/cluster"
  filter_pattern  = "{ ($.requestURI != \"/healthz*\") && ($.requestURI != \"/livez*\") && ($.user.username != \"system:node:*\") }" # Lọc bỏ healthcheck & node heartbeat, giữ 100% vết thao tác người dùng
  destination_arn = aws_kinesis_firehose_delivery_stream.eks_audit_logs.arn
  role_arn        = aws_iam_role.cwl_to_firehose.arn

  # Log group do EKS module tạo ra, nên cần depends_on để tránh lỗi
  depends_on = [
    module.eks,
    aws_iam_role_policy.cwl_to_firehose_policy
  ]
}
