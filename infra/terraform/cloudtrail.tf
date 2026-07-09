# Owner: Nhóm CDO07 (Audit)
# 1. S3 Bucket lưu trữ log của AWS CloudTrail
resource "aws_s3_bucket" "cloudtrail_logs" {
  bucket        = "tf4-cloudtrail-logs-bucket-${data.aws_caller_identity.current.account_id}"
  force_destroy = true

  tags = var.tags
}

# 2. Bật S3 Versioning để đảm bảo tính bất biến (Immutability/Non-repudiation)
resource "aws_s3_bucket_versioning" "cloudtrail_logs_versioning" {
  bucket = aws_s3_bucket.cloudtrail_logs.id
  versioning_configuration {
    status = "Enabled"
  }
}

# 3. Chặn tất cả truy cập Public vào S3 Bucket
resource "aws_s3_bucket_public_access_block" "cloudtrail_logs_public_block" {
  bucket = aws_s3_bucket.cloudtrail_logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# 4. S3 Bucket Policy cho phép AWS CloudTrail ghi log vào bucket
resource "aws_s3_bucket_policy" "cloudtrail_logs_policy" {
  bucket = aws_s3_bucket.cloudtrail_logs.id
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
            "s3:x-amz-acl" = "bucket-owner-full-control"
          }
        }
      }
    ]
  })
}

# 5. Cấu hình AWS CloudTrail ghi nhận log tất cả region
resource "aws_cloudtrail" "main" {
  name                          = "tf4-general-cloudtrail"
  s3_bucket_name                = aws_s3_bucket.cloudtrail_logs.id
  include_global_service_events = true
  is_multi_region_trail         = true
  enable_logging                = true

  depends_on = [
    aws_s3_bucket_policy.cloudtrail_logs_policy
  ]

  tags = var.tags
}
