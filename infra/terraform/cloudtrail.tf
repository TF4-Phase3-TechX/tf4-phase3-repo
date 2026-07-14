# Owner: Nhóm CDO07 (Audit)
# Ref: AUDIT-010 — Fix 3 blockers cho MANDATE-04 Forensic Audit Trail
# Ngày: 2026-07-14
# Thay đổi:
#   [1] enable_log_file_validation = true   -> tamper-evident (digest file co chu ky so)
#   [2] kms_key_id (KMS CMK rieng)          -> ma hoa log CloudTrail
#   [3] cloud_watch_logs_group_arn/role_arn -> CloudTrail -> CloudWatch Logs (query nhanh)
#   [4] S3 Object Lock GOVERNANCE 90 ngay   -> WORM, operator khong xoa duoc
#   [5] S3 explicit Deny statements         -> separation of duties

###############################################################################
# 1. KMS CMK danh rieng cho CloudTrail
#    - Tach biet voi EKS KMS key (9f8187f4...)
#    - Key rotation bat
#    - Policy: CloudTrail service + CloudWatch Logs service co quyen encrypt
###############################################################################
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
      }
    ]
  })

  tags = var.tags
}

resource "aws_kms_alias" "cloudtrail" {
  name          = "alias/tf4-cloudtrail-key"
  target_key_id = aws_kms_key.cloudtrail.key_id
}

###############################################################################
# 2. CloudWatch Log Group nhan log tu CloudTrail
#    - Retention: 90 ngay (du cho forensic trong mandate)
#    - Ma hoa bang KMS CMK o tren
###############################################################################
resource "aws_cloudwatch_log_group" "cloudtrail" {
  name              = "/aws/cloudtrail/tf4-general-cloudtrail"
  retention_in_days = 90
  kms_key_id        = aws_kms_key.cloudtrail.arn

  tags = var.tags
}

###############################################################################
# 3. IAM Role: cho phep CloudTrail ghi vao CloudWatch Logs
#    Trust policy: cloudtrail.amazonaws.com assume role nay
#    Inline policy: chi CreateLogStream + PutLogEvents vao dung log group
###############################################################################
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

###############################################################################
# 4. S3 Bucket — CloudTrail logs voi Object Lock (WORM)
#
# BREAKING CHANGE: object_lock_enabled = true -> "forces new resource"
#    Bucket cu bi destroy (force_destroy cu = true nen xoa duoc objects)
#    Bucket moi tao lai cung ten, voi Object Lock tu dau
#
# Sau apply: prevent_destroy = true ngan xoa vo tinh qua terraform destroy
#            (muon xoa phai remove lifecycle block truoc)
###############################################################################
resource "aws_s3_bucket" "cloudtrail_logs" {
  bucket              = "tf4-cloudtrail-logs-bucket-${data.aws_caller_identity.current.account_id}"
  force_destroy       = false
  object_lock_enabled = true

  tags = var.tags

  lifecycle {
    prevent_destroy = true
  }
}

###############################################################################
# 5. S3 Object Lock Configuration — GOVERNANCE mode, 90 ngay
#    GOVERNANCE: Operator khong xoa duoc (khong co s3:BypassGovernanceRetention)
#    Admin (root/terraform) van co the override neu can
###############################################################################
resource "aws_s3_bucket_object_lock_configuration" "cloudtrail_logs" {
  bucket = aws_s3_bucket.cloudtrail_logs.id

  rule {
    default_retention {
      mode = "GOVERNANCE"
      days = 90
    }
  }
}

###############################################################################
# 6. S3 Versioning
###############################################################################
resource "aws_s3_bucket_versioning" "cloudtrail_logs_versioning" {
  bucket = aws_s3_bucket.cloudtrail_logs.id

  versioning_configuration {
    status = "Enabled"
  }
}

###############################################################################
# 7. S3 Server-Side Encryption bang KMS CMK rieng cua CloudTrail
#    bucket_key_enabled = true -> giam KMS API call cost ~99%
###############################################################################
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

###############################################################################
# 8. Chan tat ca truy cap Public vao S3 Bucket
###############################################################################
resource "aws_s3_bucket_public_access_block" "cloudtrail_logs_public_block" {
  bucket = aws_s3_bucket.cloudtrail_logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

###############################################################################
# 9. S3 Bucket Policy
#    Allow: CloudTrail service ghi log (GetBucketAcl + PutObject)
#    Deny:  Non-admin xoa object/bucket (separation of duties)
#    Deny:  Tat versioning (chi root moi duoc)
#    Deny:  HTTP (bat buoc HTTPS)
###############################################################################
resource "aws_s3_bucket_policy" "cloudtrail_logs_policy" {
  bucket = aws_s3_bucket.cloudtrail_logs.id

  depends_on = [
    aws_s3_bucket_public_access_block.cloudtrail_logs_public_block
  ]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # ALLOW: CloudTrail kiem tra bucket ACL
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
      # ALLOW: CloudTrail ghi log vao bucket
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
      # DENY: Chan NON-ADMIN xoa object (separation of duties)
      #       Chi root va github-actions-terraform-apply moi duoc xoa
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
      # DENY: Chan xoa bucket
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
      # DENY: Chan tat versioning (chi root moi duoc)
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
      # DENY: Bat buoc HTTPS cho moi request
      {
        Sid    = "DenyHTTPInsecureTransport"
        Effect = "Deny"
        Principal = {
          AWS = "*"
        }
        Action   = "s3:*"
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

###############################################################################
# 10. AWS CloudTrail — main trail voi du 3 fix
#     enable_log_file_validation = true -> tao digest file, chu ky so SHA-256
#     kms_key_id                        -> ma hoa log S3
#     cloud_watch_logs_* -> day sang CloudWatch Logs de query nhanh
###############################################################################
resource "aws_cloudtrail" "main" {
  name                          = "tf4-general-cloudtrail"
  s3_bucket_name                = aws_s3_bucket.cloudtrail_logs.id
  include_global_service_events = true
  is_multi_region_trail         = true
  enable_logging                = true

  # FIX 1: Log file validation — tao digest file moi gio, co SHA-256 hash va chu ky so RSA
  #        -> Dung: aws cloudtrail validate-logs -> xac minh log chua bi sua
  enable_log_file_validation = true

  # FIX 2: Ma hoa log bang KMS CMK rieng (khong dung chung EKS key)
  kms_key_id = aws_kms_key.cloudtrail.arn

  # FIX 3: Day log sang CloudWatch Logs -> query qua Insights UI trong vai giay
  #        Khong can download tu S3 -> dat <=10 phut forensic drill
  cloud_watch_logs_group_arn = "${aws_cloudwatch_log_group.cloudtrail.arn}:*"
  cloud_watch_logs_role_arn  = aws_iam_role.cloudtrail_cw_logs.arn

  depends_on = [
    aws_s3_bucket_policy.cloudtrail_logs_policy,
    aws_iam_role_policy.cloudtrail_cw_logs_policy
  ]

  tags = var.tags
}