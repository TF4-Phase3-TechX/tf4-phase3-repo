# Owner: Nhóm CDO07 (Audit)
# Ref: AUDIT-015 — Amazon Athena Forensic Security Analytics
# Mục đích: Triển khai Athena + Glue Data Catalog để truy vấn SQL tương tác
# trên 3 nguồn audit logs (CloudTrail, AWS Config, EKS) trực tiếp trên S3.
# Chi phí incremental: ~$0.13/tháng (serverless, pay-per-query)

# ─────────────────────────────────────────────────────────────
# 1. Glue Database — chứa metadata cho tất cả audit tables
# ─────────────────────────────────────────────────────────────
resource "aws_glue_catalog_database" "audit_forensics" {
  name        = "tf4_audit_forensics"
  description = "Glue Data Catalog database cho forensic security analytics - MANDATE-04"

  tags = var.tags
}

# ─────────────────────────────────────────────────────────────
# 2. S3 Bucket — lưu trữ kết quả truy vấn Athena
# ─────────────────────────────────────────────────────────────
resource "aws_s3_bucket" "athena_results" {
  bucket        = "tf4-athena-query-results-${data.aws_caller_identity.current.account_id}"
  force_destroy = false

  tags = merge(var.tags, {
    Name      = "tf4-athena-query-results"
    DataClass = "AthenaQueryOutput"
  })
}

resource "aws_s3_bucket_server_side_encryption_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle: tự động xóa kết quả truy vấn sau 7 ngày để tiết kiệm chi phí
resource "aws_s3_bucket_lifecycle_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id

  rule {
    id     = "expire-athena-results"
    status = "Enabled"

    expiration {
      days = 7
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

# ─────────────────────────────────────────────────────────────
# 3. Athena Workgroup — cấu hình môi trường truy vấn
# ─────────────────────────────────────────────────────────────
resource "aws_athena_workgroup" "audit_forensics" {
  name        = "tf4-audit-forensics"
  description = "Workgroup cho forensic security analytics queries - MANDATE-04"
  state       = "ENABLED"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${aws_s3_bucket.athena_results.id}/results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }

    # Giới hạn scan tối đa 1 GB mỗi query để tránh chi phí bất thường
    bytes_scanned_cutoff_per_query = 1073741824 # 1 GB
  }

  tags = var.tags
}

# ─────────────────────────────────────────────────────────────
# 4. Glue Table — CloudTrail Events
# ─────────────────────────────────────────────────────────────
resource "aws_glue_catalog_table" "cloudtrail_events" {
  database_name = aws_glue_catalog_database.audit_forensics.name
  name          = "cloudtrail_events"
  description   = "CloudTrail API call events - WHO did WHAT on AWS infrastructure"
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    classification                = "cloudtrail"
    "projection.enabled"          = "true"
    "projection.year.type"        = "integer"
    "projection.year.range"       = "2026,2030"
    "projection.month.type"       = "integer"
    "projection.month.range"      = "1,12"
    "projection.month.digits"     = "2"
    "projection.day.type"         = "integer"
    "projection.day.range"        = "1,31"
    "projection.day.digits"       = "2"
    "storage.location.template"   = "s3://${aws_s3_bucket.cloudtrail_logs.id}/AWSLogs/${data.aws_caller_identity.current.account_id}/CloudTrail/${var.aws_region}/$${year}/$${month}/$${day}"
  }

  partition_keys {
    name = "year"
    type = "string"
  }
  partition_keys {
    name = "month"
    type = "string"
  }
  partition_keys {
    name = "day"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.cloudtrail_logs.id}/AWSLogs/${data.aws_caller_identity.current.account_id}/CloudTrail/${var.aws_region}/"
    input_format  = "com.amazon.emr.cloudtrail.CloudTrailInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hive.hcatalog.data.JsonSerDe"
    }

    columns {
      name = "eventversion"
      type = "string"
    }
    columns {
      name = "useridentity"
      type = "struct<type:string,arn:string,userid:string,principalid:string,accountid:string,username:string,invokedby:string,accesskeyid:string,sessioncontext:struct<attributes:struct<creationdate:string,mfaauthenticated:string>,sessionissuer:struct<type:string,principalid:string,arn:string,accountid:string,username:string>>>"
    }
    columns {
      name = "eventtime"
      type = "string"
    }
    columns {
      name = "eventsource"
      type = "string"
    }
    columns {
      name = "eventname"
      type = "string"
    }
    columns {
      name = "awsregion"
      type = "string"
    }
    columns {
      name = "sourceipaddress"
      type = "string"
    }
    columns {
      name = "useragent"
      type = "string"
    }
    columns {
      name = "requestparameters"
      type = "string"
    }
    columns {
      name = "responseelements"
      type = "string"
    }
    columns {
      name = "requestid"
      type = "string"
    }
    columns {
      name = "eventid"
      type = "string"
    }
    columns {
      name = "eventtype"
      type = "string"
    }
    columns {
      name = "apiversion"
      type = "string"
    }
    columns {
      name = "readonly"
      type = "string"
    }
    columns {
      name = "recipientaccountid"
      type = "string"
    }
    columns {
      name = "errorcode"
      type = "string"
    }
    columns {
      name = "errormessage"
      type = "string"
    }
    columns {
      name = "serviceeventdetails"
      type = "string"
    }
    columns {
      name = "addendum"
      type = "string"
    }
    columns {
      name = "sessioncredentialfromconsole"
      type = "string"
    }
    columns {
      name = "edgedevicedetails"
      type = "string"
    }
    columns {
      name = "resources"
      type = "array<struct<arn:string,accountid:string,type:string>>"
    }
    columns {
      name = "sharedeventid"
      type = "string"
    }
    columns {
      name = "vpcendpointid"
      type = "string"
    }
    columns {
      name = "tlsdetails"
      type = "struct<tlsversion:string,ciphersuite:string,clientprovidedhostheader:string>"
    }
  }
}

# ─────────────────────────────────────────────────────────────
# 5. Glue Table — AWS Config History
# ─────────────────────────────────────────────────────────────
resource "aws_glue_catalog_table" "aws_config_history" {
  database_name = aws_glue_catalog_database.audit_forensics.name
  name          = "aws_config_history"
  description   = "AWS Config configuration change history - infrastructure timeline"
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    classification                = "json"
    compressionType               = "gzip"
    "projection.enabled"          = "true"
    "projection.year.type"        = "integer"
    "projection.year.range"       = "2026,2030"
    "projection.month.type"       = "integer"
    "projection.month.range"      = "1,12"
    "projection.month.digits"     = "2"
    "projection.day.type"         = "integer"
    "projection.day.range"        = "1,31"
    "projection.day.digits"       = "2"
    "storage.location.template"   = "s3://${aws_s3_bucket.config_staging.id}/aws-config/AWSLogs/${data.aws_caller_identity.current.account_id}/Config/${var.aws_region}/$${year}/$${month}/$${day}/ConfigHistory"
  }

  partition_keys {
    name = "year"
    type = "string"
  }
  partition_keys {
    name = "month"
    type = "string"
  }
  partition_keys {
    name = "day"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.config_staging.id}/aws-config/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
    }

    columns {
      name = "version"
      type = "string"
    }
    columns {
      name = "accountid"
      type = "string"
    }
    columns {
      name = "configurationitemcapturetime"
      type = "string"
    }
    columns {
      name = "configurationitemstatus"
      type = "string"
    }
    columns {
      name = "configurationstateid"
      type = "string"
    }
    columns {
      name = "resourcecreationtime"
      type = "string"
    }
    columns {
      name = "resourcetype"
      type = "string"
    }
    columns {
      name = "resourceid"
      type = "string"
    }
    columns {
      name = "resourcename"
      type = "string"
    }
    columns {
      name = "awsregion"
      type = "string"
    }
    columns {
      name = "supplementaryconfiguration"
      type = "map<string,string>"
    }
    columns {
      name = "relationships"
      type = "array<struct<resourcetype:string,resourceid:string,resourcename:string,relationshipname:string>>"
    }
  }
}

# ─────────────────────────────────────────────────────────────
# 6. Glue Table — EKS Audit Events
# ─────────────────────────────────────────────────────────────
resource "aws_glue_catalog_table" "eks_audit_events" {
  database_name = aws_glue_catalog_database.audit_forensics.name
  name          = "eks_audit_events"
  description   = "EKS Control Plane audit events - K8s API server activity"
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    classification    = "json"
    compressionType   = "gzip"
    # Partition projection tự động tạo partition theo cấu trúc Firehose output
    "projection.enabled"          = "true"
    "projection.year.type"        = "integer"
    "projection.year.range"       = "2026,2030"
    "projection.month.type"       = "integer"
    "projection.month.range"      = "1,12"
    "projection.month.digits"     = "2"
    "projection.day.type"         = "integer"
    "projection.day.range"        = "1,31"
    "projection.day.digits"       = "2"
    "projection.hour.type"        = "integer"
    "projection.hour.range"       = "0,23"
    "projection.hour.digits"      = "2"
    "storage.location.template"   = "s3://${aws_s3_bucket.eks_audit_logs.id}/$${year}/$${month}/$${day}/$${hour}"
  }

  partition_keys {
    name = "year"
    type = "string"
  }
  partition_keys {
    name = "month"
    type = "string"
  }
  partition_keys {
    name = "day"
    type = "string"
  }
  partition_keys {
    name = "hour"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.eks_audit_logs.id}/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
      parameters = {
        "ignore.malformed.json" = "true"
      }
    }

    columns {
      name = "kind"
      type = "string"
    }
    columns {
      name = "apiversion"
      type = "string"
    }
    columns {
      name = "level"
      type = "string"
    }
    columns {
      name = "auditid"
      type = "string"
    }
    columns {
      name = "stage"
      type = "string"
    }
    columns {
      name = "requesturi"
      type = "string"
    }
    columns {
      name = "verb"
      type = "string"
    }
    columns {
      name = "user"
      type = "struct<username:string,uid:string,groups:array<string>,extra:map<string,array<string>>>"
    }
    columns {
      name = "sourceips"
      type = "array<string>"
    }
    columns {
      name = "useragent"
      type = "string"
    }
    columns {
      name = "objectref"
      type = "struct<resource:string,namespace:string,name:string,uid:string,apigroup:string,apiversion:string,resourceversion:string>"
    }
    columns {
      name = "responsestatus"
      type = "struct<status:string,message:string,reason:string,details:struct<name:string,group:string,kind:string,uid:string>,code:int>"
    }
    columns {
      name = "requestobject"
      type = "map<string,string>"
    }
    columns {
      name = "responseobject"
      type = "map<string,string>"
    }
    columns {
      name = "requestreceivedtimestamp"
      type = "string"
    }
    columns {
      name = "stagetimestamp"
      type = "string"
    }
    columns {
      name = "annotations"
      type = "map<string,string>"
    }
  }
}

# ─────────────────────────────────────────────────────────────
# 7. IAM Policy — Quyền truy vấn Athena cho Audit Analysts
# Nguyên tắc Least Privilege: chỉ cho phép đọc dữ liệu audit,
# không cho phép sửa/xóa source data trên S3 WORM buckets
# ─────────────────────────────────────────────────────────────
resource "aws_iam_policy" "athena_audit_analyst" {
  name        = "tf4-athena-audit-analyst-policy"
  description = "Least-privilege policy cho CDO07 audit analysts sử dụng Athena forensics"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowAthenaQueryExecution"
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution",
          "athena:StopQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
          "athena:GetWorkGroup",
          "athena:ListQueryExecutions"
        ]
        Resource = aws_athena_workgroup.audit_forensics.arn
      },
      {
        Sid    = "AllowGlueCatalogRead"
        Effect = "Allow"
        Action = [
          "glue:GetDatabase",
          "glue:GetTable",
          "glue:GetTables",
          "glue:GetPartition",
          "glue:GetPartitions",
          "glue:BatchGetPartition"
        ]
        Resource = [
          "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
          "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:database/${aws_glue_catalog_database.audit_forensics.name}",
          "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${aws_glue_catalog_database.audit_forensics.name}/*"
        ]
      },
      {
        Sid    = "AllowReadAuditSourceBuckets"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = [
          aws_s3_bucket.cloudtrail_logs.arn,
          "${aws_s3_bucket.cloudtrail_logs.arn}/*",
          aws_s3_bucket.config_staging.arn,
          "${aws_s3_bucket.config_staging.arn}/*",
          aws_s3_bucket.eks_audit_logs.arn,
          "${aws_s3_bucket.eks_audit_logs.arn}/*"
        ]
      },
      {
        Sid    = "AllowWriteAthenaResults"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:GetBucketLocation",
          "s3:AbortMultipartUpload",
          "s3:DeleteObject"
        ]
        Resource = [
          aws_s3_bucket.athena_results.arn,
          "${aws_s3_bucket.athena_results.arn}/*"
        ]
      },
      {
        Sid    = "AllowDecryptCloudTrailLogs"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey"
        ]
        Resource = aws_kms_key.cloudtrail.arn
      }
    ]
  })

  tags = var.tags
}

# ─────────────────────────────────────────────────────────────
# 8. IAM Policy — CloudWatch Logs Insights cho Real-time Forensics
# Hybrid approach: CW Insights (real-time, <1h) + Athena (historical, S3 WORM)
# Scoped chỉ đến 2 log groups chứa audit data
# ─────────────────────────────────────────────────────────────
resource "aws_iam_policy" "cloudwatch_insights_forensics" {
  name        = "tf4-cloudwatch-insights-forensics-policy"
  description = "CloudWatch Logs Insights permissions cho real-time forensic queries - MANDATE-04 hybrid approach"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudWatchLogsInsightsQuery"
        Effect = "Allow"
        Action = [
          "logs:StartQuery",
          "logs:StopQuery",
          "logs:GetQueryResults",
          "logs:GetLogEvents",
          "logs:FilterLogEvents",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams"
        ]
        Resource = [
          "${aws_cloudwatch_log_group.cloudtrail.arn}:*",
          "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/eks/${var.cluster_name}/cluster:*"
        ]
      }
    ]
  })

  tags = var.tags
}
