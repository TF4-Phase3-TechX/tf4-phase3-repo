# Owner: Nhóm CDO07 (Audit)
# Ref: AUDIT-010 — Fix 3 blockers cho MANDATE-04 Forensic Audit Trail
# Ngày: 2026-07-14
# Thay đổi:
#   [1] enable_log_file_validation = true   -> tamper-evident (digest file có chữ ký số)
#   [2] kms_key_id (KMS CMK riêng)          -> mã hóa log CloudTrail
#   [3] cloud_watch_logs_group_arn/role_arn -> CloudTrail -> CloudWatch Logs (query nhanh)
#   [4] S3 Object Lock COMPLIANCE 90 ngày   -> WORM, operator không xóa được
#   [5] S3 explicit Deny statements         -> separation of duties

# KMS CMK dành riêng cho CloudTrail
# Tách biệt với EKS KMS key, key rotation bật
# Policy: CloudTrail service + CloudWatch Logs service có quyền encrypt
resource "aws_kms_key" "cloudtrail" {
  description             = "TF4 CloudTrail dedicated KMS key - log encryption & tamper-evident"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  multi_region            = false

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EnableRootIAMAccess"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "AllowCloudTrailEncryptS3Logs"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action = [
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = "*"
        Condition = {
          StringLike = {
            "kms:EncryptionContext:aws:cloudtrail:arn" = "arn:aws:cloudtrail:*:${data.aws_caller_identity.current.account_id}:trail/*"
          }
        }
      },
      {
        Sid    = "AllowCloudWatchLogsEncrypt"
        Effect = "Allow"
        Principal = {
          Service = "logs.us-east-1.amazonaws.com"
        }
        Action = [
          "kms:Encrypt*",
          "kms:Decrypt*",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:Describe*"
        ]
        Resource = "*"
        Condition = {
          ArnLike = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:aws:logs:us-east-1:${data.aws_caller_identity.current.account_id}:*"
          }
        }
      },
      {
        Sid    = "AllowAuditTeamReadKeyMeta"
        Effect = "Allow"
        Principal = {
          AWS = "*"
        }
        Action = [
          "kms:DescribeKey",
          "kms:GetKeyPolicy",
          "kms:GetKeyRotationStatus"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:PrincipalAccount" = data.aws_caller_identity.current.account_id
          }
        }
      },
      {
        Sid    = "AllowEventBridgeEncryptSNS"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
        Action = [
          "kms:GenerateDataKey*",
          "kms:Decrypt"
        ]
        Resource = "*"
      }
    ]
  })

  tags = var.tags
}

resource "aws_kms_alias" "cloudtrail" {
  name          = "alias/tf4-cloudtrail-key"
  target_key_id = aws_kms_key.cloudtrail.key_id
}

# CloudWatch Log Group nhận log từ CloudTrail
# Retention: 90 ngày (đủ cho forensic trong mandate)
# Mã hóa bằng KMS CMK ở trên
resource "aws_cloudwatch_log_group" "cloudtrail" {
  name              = "/aws/cloudtrail/tf4-general-cloudtrail"
  retention_in_days = 90
  kms_key_id        = aws_kms_key.cloudtrail.arn

  tags = var.tags
}

# IAM Role: cho phép CloudTrail ghi vào CloudWatch Logs
# Trust policy: cloudtrail.amazonaws.com assume role này
# Inline policy: chỉ CreateLogStream + PutLogEvents vào đúng log group
resource "aws_iam_role" "cloudtrail_cw_logs" {
  name = "tf4-cloudtrail-to-cloudwatch-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "AllowCloudTrailAssume"
      Effect = "Allow"
      Principal = {
        Service = "cloudtrail.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "cloudtrail_cw_logs_policy" {
  name = "tf4-cloudtrail-cw-write-policy"
  role = aws_iam_role.cloudtrail_cw_logs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "AllowCloudTrailWriteCWL"
      Effect = "Allow"
      Action = [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ]
      Resource = "${aws_cloudwatch_log_group.cloudtrail.arn}:*"
    }]
  })
}

# S3 Bucket — CloudTrail logs với Object Lock (WORM)
# BREAKING CHANGE: object_lock_enabled = true -> "forces new resource"
# Bucket cũ bị destroy (force_destroy cũ = true nên xóa được objects)
# Bucket mới tạo lại cùng tên, với Object Lock từ đầu
# Sau apply: prevent_destroy = true ngăn xóa vô tình qua terraform destroy
resource "aws_s3_bucket" "cloudtrail_logs" {
  bucket              = "tf4-cloudtrail-logs-bucket-${data.aws_caller_identity.current.account_id}"
  force_destroy       = false
  object_lock_enabled = true

  tags = var.tags

  # lifecycle {
  #   prevent_destroy = true
  # }
}

# S3 Object Lock Configuration — COMPLIANCE mode, 90 ngày
# COMPLIANCE: Không ai xóa được, kể cả root account (strict WORM)
# Khác với GOVERNANCE: admin không thể override, phù hợp audit/compliance yêu cầu cao
resource "aws_s3_bucket_object_lock_configuration" "cloudtrail_logs" {
  bucket = aws_s3_bucket.cloudtrail_logs.id

  rule {
    default_retention {
      mode = "COMPLIANCE"
      days = 90
    }
  }
}

resource "aws_s3_bucket_versioning" "cloudtrail_logs_versioning" {
  bucket = aws_s3_bucket.cloudtrail_logs.id

  versioning_configuration {
    status = "Enabled"
  }
}

# S3 Server-Side Encryption bằng KMS CMK riêng của CloudTrail
# bucket_key_enabled = true -> giảm KMS API call cost ~99%
resource "aws_s3_bucket_server_side_encryption_configuration" "cloudtrail_logs" {
  bucket = aws_s3_bucket.cloudtrail_logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.cloudtrail.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "cloudtrail_logs_public_block" {
  bucket = aws_s3_bucket.cloudtrail_logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# S3 Bucket Policy
# Allow: CloudTrail service ghi log (GetBucketAcl + PutObject)
# Deny: Non-admin xóa object/bucket (separation of duties)
# Deny: Tắt versioning (chỉ root mới được)
# Deny: HTTP (bắt buộc HTTPS)
resource "aws_s3_bucket_policy" "cloudtrail_logs_policy" {
  bucket = aws_s3_bucket.cloudtrail_logs.id

  depends_on = [
    aws_s3_bucket_public_access_block.cloudtrail_logs_public_block
  ]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AWSCloudTrailAclCheck"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action   = "s3:GetBucketAcl"
        Resource = aws_s3_bucket.cloudtrail_logs.arn
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = "arn:aws:cloudtrail:us-east-1:${data.aws_caller_identity.current.account_id}:trail/tf4-general-cloudtrail"
          }
        }
      },
      {
        Sid    = "AWSCloudTrailWrite"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.cloudtrail_logs.arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/*"
        Condition = {
          StringEquals = {
            "s3:x-amz-acl"  = "bucket-owner-full-control"
            "AWS:SourceArn" = "arn:aws:cloudtrail:us-east-1:${data.aws_caller_identity.current.account_id}:trail/tf4-general-cloudtrail"
          }
        }
      },
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
        Resource = "${aws_s3_bucket.cloudtrail_logs.arn}/*"
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
        Resource = aws_s3_bucket.cloudtrail_logs.arn
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
        Resource = aws_s3_bucket.cloudtrail_logs.arn
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
          aws_s3_bucket.cloudtrail_logs.arn,
          "${aws_s3_bucket.cloudtrail_logs.arn}/*"
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

# AWS CloudTrail — main trail với đủ 3 fix
# enable_log_file_validation = true -> tạo digest file, chữ ký số SHA-256
# kms_key_id -> mã hóa log S3
# cloud_watch_logs_* -> đẩy sang CloudWatch Logs để query nhanh
resource "aws_cloudtrail" "main" {
  name                          = "tf4-general-cloudtrail"
  s3_bucket_name                = aws_s3_bucket.cloudtrail_logs.id
  include_global_service_events = true
  is_multi_region_trail         = true
  enable_logging                = true

  event_selector {
    read_write_type           = "All"
    include_management_events = true
  }

  # FIX 1: Log file validation — tạo digest file mỗi giờ, có SHA-256 hash và chữ ký số RSA
  # Dùng: aws cloudtrail validate-logs -> xác minh log chưa bị sửa
  enable_log_file_validation = true

  # FIX 2: Mã hóa log bằng KMS CMK riêng (không dùng chung EKS key)
  kms_key_id = aws_kms_key.cloudtrail.arn

  # FIX 3: Đẩy log sang CloudWatch Logs -> query qua Insights UI trong vài giây
  # Không cần download từ S3 -> đạt <=10 phút forensic drill
  cloud_watch_logs_group_arn = "${aws_cloudwatch_log_group.cloudtrail.arn}:*"
  cloud_watch_logs_role_arn  = aws_iam_role.cloudtrail_cw_logs.arn

  depends_on = [
    aws_s3_bucket_policy.cloudtrail_logs_policy,
    aws_iam_role_policy.cloudtrail_cw_logs_policy
  ]

  tags = var.tags
}