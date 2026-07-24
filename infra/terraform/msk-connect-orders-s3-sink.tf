# REL-22 - MSK Connect S3 Sink connector for orders archive.
# Archives the orders topic to S3 without changing the application request path.

locals {
  msk_connect_orders_s3_sink_name = "techx-tf4-orders-s3-sink"

  msk_connect_plugin_key        = "plugins/confluent-s3-sink/12.1.0/confluent-s3-sink-msk-config-provider-0.4.0.zip"
  msk_connect_plugin_version_id = "hXtZCmoZg6tFgybk57jR400Kdf2CYHHh"
  msk_connect_plugin_sha256     = "112225c1dff0620e4f4050551cc5a22191a8f231348350cf44dbf603e7c497ee"

  msk_connect_orders_dlq_topic = "orders-archive-dlq"
}

data "aws_secretsmanager_secret" "msk_kafka" {
  name = "techx/tf4/msk-kafka"
}

resource "aws_security_group" "msk_connect_orders_s3_sink" {
  name        = "techx-tf4-msk-connect-orders-s3-sink"
  description = "MSK Connect S3 Sink access for REL-22 orders archival"
  vpc_id      = module.vpc.vpc_id

  tags = merge(var.tags, {
    Name      = "techx-tf4-msk-connect-orders-s3-sink"
    Component = "msk-connect"
    Mandate   = "20"
    Task      = "CDO08-REL-22"
  })
}

resource "aws_vpc_security_group_ingress_rule" "msk_sasl_ssl_from_msk_connect_orders_s3_sink" {
  security_group_id            = aws_security_group.msk.id
  referenced_security_group_id = aws_security_group.msk_connect_orders_s3_sink.id
  ip_protocol                  = "tcp"
  from_port                    = 9096
  to_port                      = 9096
  description                  = "Allow REL-22 MSK Connect S3 Sink to consume orders over SASL/SCRAM TLS"
}

resource "aws_vpc_security_group_egress_rule" "msk_connect_orders_s3_sink_to_msk" {
  security_group_id            = aws_security_group.msk_connect_orders_s3_sink.id
  referenced_security_group_id = aws_security_group.msk.id
  ip_protocol                  = "tcp"
  from_port                    = 9096
  to_port                      = 9096
  description                  = "Allow MSK Connect S3 Sink egress to MSK SASL/SCRAM brokers"
}

resource "aws_vpc_security_group_egress_rule" "msk_connect_orders_s3_sink_https" {
  security_group_id = aws_security_group.msk_connect_orders_s3_sink.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "Allow MSK Connect S3 Sink to call AWS APIs over HTTPS"
}

resource "aws_vpc_security_group_egress_rule" "msk_connect_orders_s3_sink_dns_tcp" {
  security_group_id = aws_security_group.msk_connect_orders_s3_sink.id
  cidr_ipv4         = var.vpc_cidr
  ip_protocol       = "tcp"
  from_port         = 53
  to_port           = 53
  description       = "Allow DNS TCP resolution through the VPC resolver path"
}

resource "aws_vpc_security_group_egress_rule" "msk_connect_orders_s3_sink_dns_udp" {
  security_group_id = aws_security_group.msk_connect_orders_s3_sink.id
  cidr_ipv4         = var.vpc_cidr
  ip_protocol       = "udp"
  from_port         = 53
  to_port           = 53
  description       = "Allow DNS UDP resolution through the VPC resolver path"
}

resource "aws_cloudwatch_log_group" "msk_connect_orders_s3_sink" {
  name              = "/aws/mskconnect/techx-tf4-orders-s3-sink"
  retention_in_days = 14

  tags = merge(var.tags, {
    Name      = "techx-tf4-orders-s3-sink"
    Component = "msk-connect"
    Mandate   = "20"
    Task      = "CDO08-REL-22"
  })
}

data "aws_iam_policy_document" "msk_connect_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["kafkaconnect.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${data.aws_partition.current.partition}:kafkaconnect:${var.aws_region}:${data.aws_caller_identity.current.account_id}:connector/*"]
    }
  }
}

resource "aws_iam_role" "msk_connect_orders_s3_sink" {
  name               = "techx-tf4-orders-s3-sink-msk-connect"
  assume_role_policy = data.aws_iam_policy_document.msk_connect_assume_role.json

  tags = merge(var.tags, {
    Name      = "techx-tf4-orders-s3-sink-msk-connect"
    Component = "msk-connect"
    Mandate   = "20"
    Task      = "CDO08-REL-22"
  })
}

data "aws_iam_policy_document" "msk_connect_orders_s3_sink" {
  statement {
    sid    = "ReadCustomPluginArtifact"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
    ]
    resources = ["${aws_s3_bucket.msk_connect_plugins.arn}/${local.msk_connect_plugin_key}"]
  }

  statement {
    sid       = "ListCustomPluginArtifactBucket"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.msk_connect_plugins.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = [local.msk_connect_plugin_prefix, "${local.msk_connect_plugin_prefix}*"]
    }
  }

  statement {
    sid    = "WriteOrdersArchiveObjects"
    effect = "Allow"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:GetBucketLocation",
      "s3:ListBucketMultipartUploads",
      "s3:ListMultipartUploadParts",
      "s3:PutObject",
    ]
    resources = [
      aws_s3_bucket.msk_orders_archive.arn,
      "${aws_s3_bucket.msk_orders_archive.arn}/${local.msk_orders_archive_prefix}*",
    ]
  }

  statement {
    sid       = "ListOrdersArchivePrefix"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.msk_orders_archive.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = [local.msk_orders_archive_prefix, "${local.msk_orders_archive_prefix}*"]
    }
  }

  statement {
    sid       = "ReadMskScramCredential"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [data.aws_secretsmanager_secret.msk_kafka.arn]
  }

  statement {
    sid       = "DecryptSecretsManagerCredentialIfCustomerManagedKeyIsUsed"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "kms:CallerAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["secretsmanager.${var.aws_region}.amazonaws.com"]
    }
  }

  statement {
    sid    = "WriteConnectorLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams",
    ]
    resources = ["${aws_cloudwatch_log_group.msk_connect_orders_s3_sink.arn}:*"]
  }

  statement {
    sid    = "ManageConnectorLogDelivery"
    effect = "Allow"
    actions = [
      "logs:CreateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:DescribeLogGroups",
      "logs:DescribeResourcePolicies",
      "logs:GetLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:UpdateLogDelivery",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "msk_connect_orders_s3_sink" {
  name   = "techx-tf4-orders-s3-sink-msk-connect"
  role   = aws_iam_role.msk_connect_orders_s3_sink.id
  policy = data.aws_iam_policy_document.msk_connect_orders_s3_sink.json
}

resource "aws_mskconnect_custom_plugin" "orders_s3_sink" {
  name         = "techx-tf4-orders-s3-sink"
  content_type = "ZIP"

  location {
    s3 {
      bucket_arn     = aws_s3_bucket.msk_connect_plugins.arn
      file_key       = local.msk_connect_plugin_key
      object_version = local.msk_connect_plugin_version_id
    }
  }

  tags = merge(var.tags, {
    Name             = "techx-tf4-orders-s3-sink"
    Component        = "msk-connect"
    ConnectorVersion = "12.1.0"
    ConfigProvider   = "0.4.0"
    PluginSha256     = local.msk_connect_plugin_sha256
    Mandate          = "20"
    Task             = "CDO08-REL-22"
  })
}

resource "aws_mskconnect_worker_configuration" "orders_s3_sink" {
  name                    = "techx-tf4-orders-s3-sink-worker"
  description             = "Worker configuration for REL-22 orders S3 archive connector"
  properties_file_content = <<-PROPERTIES
    key.converter=org.apache.kafka.connect.storage.StringConverter
    value.converter=org.apache.kafka.connect.json.JsonConverter
    value.converter.schemas.enable=false
    connector.client.config.override.policy=All
    offset.flush.interval.ms=60000
    config.providers=secretsmanager
    config.providers.secretsmanager.class=com.amazonaws.kafka.config.providers.SecretsManagerConfigProvider
    config.providers.secretsmanager.param.region=${var.aws_region}
  PROPERTIES
}

resource "aws_mskconnect_connector" "orders_s3_sink" {
  name                       = local.msk_connect_orders_s3_sink_name
  kafkaconnect_version       = "2.7.1"
  service_execution_role_arn = aws_iam_role.msk_connect_orders_s3_sink.arn

  capacity {
    provisioned_capacity {
      mcu_count    = 1
      worker_count = 1
    }
  }

  connector_configuration = {
    "connector.class"                               = "io.confluent.connect.s3.S3SinkConnector"
    "tasks.max"                                     = "1"
    "topics"                                        = "orders"
    "s3.region"                                     = var.aws_region
    "s3.bucket.name"                                = aws_s3_bucket.msk_orders_archive.id
    "topics.dir"                                    = trimsuffix(local.msk_orders_archive_prefix, "/")
    "storage.class"                                 = "io.confluent.connect.s3.storage.S3Storage"
    "format.class"                                  = "io.confluent.connect.s3.format.json.JsonFormat"
    "schema.compatibility"                          = "NONE"
    "key.converter"                                 = "org.apache.kafka.connect.storage.StringConverter"
    "value.converter"                               = "org.apache.kafka.connect.json.JsonConverter"
    "value.converter.schemas.enable"                = "false"
    "partitioner.class"                             = "io.confluent.connect.storage.partitioner.TimeBasedPartitioner"
    "path.format"                                   = "'topic'=orders/'year'=YYYY/'month'=MM/'day'=dd/'hour'=HH"
    "partition.duration.ms"                         = "3600000"
    "locale"                                        = "en"
    "timezone"                                      = "UTC"
    "timestamp.extractor"                           = "Record"
    "rotate.schedule.interval.ms"                   = "600000"
    "flush.size"                                    = "100"
    "s3.part.size"                                  = "5242880"
    "consumer.override.security.protocol"           = "SASL_SSL"
    "consumer.override.sasl.mechanism"              = "SCRAM-SHA-512"
    "consumer.override.sasl.jaas.config"            = "org.apache.kafka.common.security.scram.ScramLoginModule required username=\"$${secretsmanager:techx/tf4/msk-kafka:username}\" password=\"$${secretsmanager:techx/tf4/msk-kafka:password}\";"
    "producer.override.security.protocol"           = "SASL_SSL"
    "producer.override.sasl.mechanism"              = "SCRAM-SHA-512"
    "producer.override.sasl.jaas.config"            = "org.apache.kafka.common.security.scram.ScramLoginModule required username=\"$${secretsmanager:techx/tf4/msk-kafka:username}\" password=\"$${secretsmanager:techx/tf4/msk-kafka:password}\";"
    "errors.tolerance"                              = "all"
    "errors.deadletterqueue.topic.name"             = local.msk_connect_orders_dlq_topic
    "errors.deadletterqueue.context.headers.enable" = "true"
    "errors.log.enable"                             = "true"
    "errors.log.include.messages"                   = "false"
    "config.action.reload"                          = "none"
  }

  kafka_cluster {
    apache_kafka_cluster {
      bootstrap_servers = aws_msk_cluster.orders.bootstrap_brokers_sasl_scram

      vpc {
        security_groups = [aws_security_group.msk_connect_orders_s3_sink.id]
        subnets         = module.vpc.private_subnets
      }
    }
  }

  kafka_cluster_client_authentication {
    authentication_type = "SASL_SCRAM"
  }

  kafka_cluster_encryption_in_transit {
    encryption_type = "TLS"
  }

  log_delivery {
    worker_log_delivery {
      cloudwatch_logs {
        enabled   = true
        log_group = aws_cloudwatch_log_group.msk_connect_orders_s3_sink.name
      }
    }
  }

  plugin {
    custom_plugin {
      arn      = aws_mskconnect_custom_plugin.orders_s3_sink.arn
      revision = aws_mskconnect_custom_plugin.orders_s3_sink.latest_revision
    }
  }

  worker_configuration {
    arn      = aws_mskconnect_worker_configuration.orders_s3_sink.arn
    revision = aws_mskconnect_worker_configuration.orders_s3_sink.latest_revision
  }

  tags = merge(var.tags, {
    Name      = local.msk_connect_orders_s3_sink_name
    Component = "msk-connect"
    Mandate   = "20"
    Task      = "CDO08-REL-22"
  })

  depends_on = [
    aws_iam_role_policy.msk_connect_orders_s3_sink,
    aws_vpc_security_group_ingress_rule.msk_sasl_ssl_from_msk_connect_orders_s3_sink,
  ]
}
