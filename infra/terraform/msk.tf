# Ref: CDO08-REL-14 - Amazon MSK managed baseline for the orders stream.
data "aws_iam_policy_document" "msk_kms" {
  statement {
    sid    = "EnableRootAccountAdministration"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }

    actions   = ["kms:*"]
    resources = ["*"]
  }
}

resource "aws_kms_key" "msk" {
  description             = "KMS key for TechX MSK storage encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.msk_kms.json

  tags = merge(var.tags, {
    Name = "techx-tf4-msk"
  })
}

resource "aws_kms_alias" "msk" {
  name          = "alias/techx-tf4-msk"
  target_key_id = aws_kms_key.msk.key_id
}

resource "aws_security_group" "msk" {
  name        = "techx-tf4-msk"
  description = "Private MSK access for TechX Kafka migration target"
  vpc_id      = module.vpc.vpc_id

  tags = merge(var.tags, {
    Name = "techx-tf4-msk"
  })
}

resource "aws_vpc_security_group_ingress_rule" "msk_sasl_ssl_from_eks_nodes" {
  security_group_id            = aws_security_group.msk.id
  referenced_security_group_id = module.eks.node_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 9096
  to_port                      = 9096
  description                  = "Allow EKS workloads and MirrorMaker2 to connect to MSK SASL/SCRAM"
}

resource "aws_vpc_security_group_egress_rule" "msk_all_egress" {
  security_group_id = aws_security_group.msk.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "Allow MSK broker egress for managed control-plane operations"
}

resource "aws_cloudwatch_log_group" "msk" {
  name              = "/aws/msk/techx-tf4-orders"
  retention_in_days = 7

  tags = merge(var.tags, {
    Name = "techx-tf4-msk-orders"
  })
}

resource "aws_msk_configuration" "orders" {
  name           = "techx-tf4-orders"
  kafka_versions = ["3.9.x"]

  server_properties = <<-PROPERTIES
    auto.create.topics.enable=true
    default.replication.factor=2
    min.insync.replicas=1
    num.partitions=3
    offsets.topic.replication.factor=2
    transaction.state.log.min.isr=1
    transaction.state.log.replication.factor=2
  PROPERTIES
}

resource "aws_msk_cluster" "orders" {
  cluster_name           = "techx-tf4-orders"
  kafka_version          = "3.9.x"
  number_of_broker_nodes = 2

  broker_node_group_info {
    instance_type   = "kafka.t3.small"
    client_subnets  = module.vpc.private_subnets
    security_groups = [aws_security_group.msk.id]

    storage_info {
      ebs_storage_info {
        volume_size = 10
      }
    }
  }

  client_authentication {
    sasl {
      scram = true
    }
  }

  configuration_info {
    arn      = aws_msk_configuration.orders.arn
    revision = aws_msk_configuration.orders.latest_revision
  }

  encryption_info {
    encryption_at_rest_kms_key_arn = aws_kms_key.msk.arn

    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }

  logging_info {
    broker_logs {
      cloudwatch_logs {
        enabled   = true
        log_group = aws_cloudwatch_log_group.msk.name
      }
    }
  }

  tags = merge(var.tags, {
    Name = "techx-tf4-orders"
  })
}

resource "aws_appautoscaling_target" "msk_broker_storage" {
  max_capacity       = 100
  min_capacity       = 10
  resource_id        = aws_msk_cluster.orders.arn
  scalable_dimension = "kafka:broker-storage:VolumeSize"
  service_namespace  = "kafka"
}

resource "aws_appautoscaling_policy" "msk_broker_storage" {
  name               = "techx-tf4-msk-broker-storage"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.msk_broker_storage.resource_id
  scalable_dimension = aws_appautoscaling_target.msk_broker_storage.scalable_dimension
  service_namespace  = aws_appautoscaling_target.msk_broker_storage.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "KafkaBrokerStorageUtilization"
    }

    target_value = 80
  }
}
