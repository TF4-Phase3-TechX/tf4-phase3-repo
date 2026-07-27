# Task 62 / Mandate 14
# Dedicated AI/tool audit path:
# OTel Collector -> CloudWatch Logs -> Amazon Data Firehose -> S3 Object Lock.

locals {
  ai_audit_log_group_name               = "/aws/eks/techx-tf4/ai-audit"
  ai_audit_log_group_arn                = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:${local.ai_audit_log_group_name}:*"
  ai_audit_firehose_name                = "tf4-ai-audit-logs"
  ai_audit_firehose_arn                 = "arn:aws:firehose:${var.aws_region}:${data.aws_caller_identity.current.account_id}:deliverystream/${local.ai_audit_firehose_name}"
  ai_audit_s3_root_prefix               = "mandate-14/"
  ai_audit_s3_prefix                    = "mandate-14/ai-tool-audit/"
  ai_audit_firehose_error_prefix        = "mandate-14/errors/"
  otel_collector_namespace              = "techx-observability"
  otel_collector_service_account        = "otel-collector"
  ai_audit_firehose_error_log_group     = "/aws/firehose/tf4-ai-audit-errors"
  ai_audit_firehose_error_log_group_arn = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:${local.ai_audit_firehose_error_log_group}:*"

  ai_audit_tags = merge(var.tags, {
    Control            = "Mandate-14"
    DataClassification = "InternalAuditMetadata"
    Pipeline           = "ai-tool-audit"
  })
}

# CloudWatch is the operational audit copy and the source for Firehose.
resource "aws_cloudwatch_log_group" "ai_audit" {
  name              = local.ai_audit_log_group_name
  retention_in_days = 7
  tags              = local.ai_audit_tags
}

resource "aws_cloudwatch_log_group" "ai_audit_firehose_errors" {
  name              = local.ai_audit_firehose_error_log_group
  retention_in_days = 7
  tags              = local.ai_audit_tags
}

resource "aws_cloudwatch_log_stream" "ai_audit_firehose_s3_delivery" {
  name           = "S3Delivery"
  log_group_name = aws_cloudwatch_log_group.ai_audit_firehose_errors.name
}

# S3 is the long-lived audit archive. Object Lock retention can be enabled manually out-of-band via Break-Glass role.
resource "aws_s3_bucket" "ai_audit" {
  bucket        = "tf4-ai-audit-logs-${data.aws_caller_identity.current.account_id}"
  force_destroy = false

  tags = local.ai_audit_tags
}

resource "aws_s3_bucket_versioning" "ai_audit" {
  bucket = aws_s3_bucket.ai_audit.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "ai_audit" {
  bucket = aws_s3_bucket.ai_audit.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "ai_audit" {
  bucket = aws_s3_bucket.ai_audit.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "ai_audit" {
  bucket = aws_s3_bucket.ai_audit.id

  rule {
    id     = "expire-ai-audit-after-object-lock"
    status = "Enabled"

    filter {
      prefix = local.ai_audit_s3_root_prefix
    }

    expiration {
      days = 90
    }

    # Versioned expiration first creates a delete marker. Remove the resulting
    # noncurrent version as soon as the 90-day retention permits.
    noncurrent_version_expiration {
      noncurrent_days = 1
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [
    aws_s3_bucket_versioning.ai_audit,
  ]
}

resource "aws_s3_bucket_policy" "ai_audit" {
  bucket = aws_s3_bucket.ai_audit.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.ai_audit.arn,
          "${aws_s3_bucket.ai_audit.arn}/*",
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      },
      {
        Sid       = "DenyWrongEncryptionHeader"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.ai_audit.arn}/*"
        Condition = {
          StringNotEquals = {
            "s3:x-amz-server-side-encryption" = "AES256"
          }
          Null = {
            "s3:x-amz-server-side-encryption" = "false"
          }
        }
      },
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.ai_audit]
}

# Firehose can read/write only the AI audit and delivery-error prefixes. It
# cannot delete audit objects and receives no KMS permissions.
resource "aws_iam_role" "ai_audit_firehose_to_s3" {
  name = "tf4-ai-audit-firehose-to-s3-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "AllowFirehoseAssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "firehose.amazonaws.com"
      }
      Action = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          "aws:SourceAccount" = data.aws_caller_identity.current.account_id
        }
      }
    }]
  })

  tags = local.ai_audit_tags
}

resource "aws_iam_role_policy" "ai_audit_firehose_to_s3" {
  name = "tf4-ai-audit-firehose-to-s3-policy"
  role = aws_iam_role.ai_audit_firehose_to_s3.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InspectDestinationBucket"
        Effect = "Allow"
        Action = [
          "s3:GetBucketLocation",
          "s3:ListBucket",
          "s3:ListBucketMultipartUploads",
        ]
        Resource = aws_s3_bucket.ai_audit.arn
      },
      {
        Sid    = "WriteAuditObjects"
        Effect = "Allow"
        Action = [
          "s3:AbortMultipartUpload",
          "s3:GetObject",
          "s3:ListMultipartUploadParts",
          "s3:PutObject",
        ]
        Resource = [
          "${aws_s3_bucket.ai_audit.arn}/${local.ai_audit_s3_prefix}*",
          "${aws_s3_bucket.ai_audit.arn}/${local.ai_audit_firehose_error_prefix}*",
        ]
      },
      {
        Sid      = "WriteDeliveryErrors"
        Effect   = "Allow"
        Action   = "logs:PutLogEvents"
        Resource = local.ai_audit_firehose_error_log_group_arn
      },
    ]
  })
}

resource "aws_kinesis_firehose_delivery_stream" "ai_audit" {
  name        = local.ai_audit_firehose_name
  destination = "extended_s3"

  extended_s3_configuration {
    role_arn   = aws_iam_role.ai_audit_firehose_to_s3.arn
    bucket_arn = aws_s3_bucket.ai_audit.arn

    buffering_size      = 5
    buffering_interval  = 60
    compression_format  = "GZIP"
    prefix              = "${local.ai_audit_s3_prefix}year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/"
    error_output_prefix = "${local.ai_audit_firehose_error_prefix}year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/type=!{firehose:error-output-type}/"

    processing_configuration {
      enabled = true

      processors {
        type = "Decompression"

        parameters {
          parameter_name  = "CompressionFormat"
          parameter_value = "GZIP"
        }
      }

      processors {
        type = "CloudWatchLogProcessing"

        parameters {
          parameter_name  = "DataMessageExtraction"
          parameter_value = "true"
        }
      }
    }

    cloudwatch_logging_options {
      enabled         = true
      log_group_name  = aws_cloudwatch_log_group.ai_audit_firehose_errors.name
      log_stream_name = aws_cloudwatch_log_stream.ai_audit_firehose_s3_delivery.name
    }
  }

  tags = local.ai_audit_tags

  depends_on = [
    aws_iam_role_policy.ai_audit_firehose_to_s3,
    aws_s3_bucket_lifecycle_configuration.ai_audit,
    aws_s3_bucket_policy.ai_audit,
  ]
}

# CloudWatch Logs can put records only into the dedicated AI audit stream.
resource "aws_iam_role" "ai_audit_cwl_to_firehose" {
  name = "tf4-ai-audit-cwl-to-firehose-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "AllowCloudWatchLogsAssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "logs.amazonaws.com"
      }
      Action = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          "aws:SourceAccount" = data.aws_caller_identity.current.account_id
        }
        ArnLike = {
          "aws:SourceArn" = local.ai_audit_log_group_arn
        }
      }
    }]
  })

  tags = local.ai_audit_tags
}

resource "aws_iam_role_policy" "ai_audit_cwl_to_firehose" {
  name = "tf4-ai-audit-cwl-to-firehose-policy"
  role = aws_iam_role.ai_audit_cwl_to_firehose.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "WriteDedicatedAuditStream"
      Effect = "Allow"
      Action = [
        "firehose:PutRecord",
        "firehose:PutRecordBatch",
      ]
      Resource = local.ai_audit_firehose_arn
    }]
  })
}

resource "aws_cloudwatch_log_subscription_filter" "ai_audit" {
  name            = "tf4-ai-audit-to-firehose"
  log_group_name  = aws_cloudwatch_log_group.ai_audit.name
  filter_pattern  = ""
  destination_arn = aws_kinesis_firehose_delivery_stream.ai_audit.arn
  role_arn        = aws_iam_role.ai_audit_cwl_to_firehose.arn

  depends_on = [aws_iam_role_policy.ai_audit_cwl_to_firehose]
}

# The collector receives AWS credentials through EKS Pod Identity. The trust
# policy and association are constrained to the exact cluster/namespace/SA.
resource "aws_iam_role" "otel_collector_ai_audit" {
  name = "tf4-otel-ai-audit-cloudwatch-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "AllowEksPodIdentity"
      Effect = "Allow"
      Principal = {
        Service = "pods.eks.amazonaws.com"
      }
      Action = [
        "sts:AssumeRole",
        "sts:TagSession",
      ]
      Condition = {
        StringEquals = {
          "aws:RequestTag/eks-cluster-name"           = var.cluster_name
          "aws:RequestTag/kubernetes-namespace"       = local.otel_collector_namespace
          "aws:RequestTag/kubernetes-service-account" = local.otel_collector_service_account
        }
      }
    }]
  })

  tags = local.ai_audit_tags
}

resource "aws_iam_role_policy" "otel_collector_ai_audit" {
  name = "tf4-otel-ai-audit-cloudwatch-policy"
  role = aws_iam_role.otel_collector_ai_audit.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "WriteDedicatedAuditLogGroup"
      Effect = "Allow"
      Action = [
        "logs:CreateLogStream",
        "logs:DescribeLogStreams",
        "logs:PutLogEvents",
      ]
      Resource = local.ai_audit_log_group_arn
    }]
  })
}

resource "aws_eks_pod_identity_association" "otel_collector_ai_audit" {
  cluster_name    = module.eks.cluster_name
  namespace       = local.otel_collector_namespace
  service_account = local.otel_collector_service_account
  role_arn        = aws_iam_role.otel_collector_ai_audit.arn
}
