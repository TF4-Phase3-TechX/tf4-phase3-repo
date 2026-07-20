# Owner: CDO08 Reliability
# REL-15: AWS DMS baseline for PostgreSQL migration.
# This provisions the private DMS runtime only; endpoint/task creation waits for
# source/target Secrets Manager values so credentials do not enter Terraform state.

locals {
  postgresql_dms_source_host        = "k8s-techxtf4-postgres-981d5617bf-18dcaaac76555685.elb.us-east-1.amazonaws.com"
  postgresql_dms_source_secret_path = "techx/tf4/dms-postgres-source"
  postgresql_dms_target_secret_path = "techx/tf4/rds-postgres"

  postgresql_dms_table_mappings = {
    rules = [
      {
        "rule-type" = "selection"
        "rule-id"   = "1"
        "rule-name" = "include-accounting"
        "object-locator" = {
          "schema-name" = "accounting"
          "table-name"  = "%"
        }
        "rule-action" = "include"
      },
      {
        "rule-type" = "selection"
        "rule-id"   = "2"
        "rule-name" = "include-catalog"
        "object-locator" = {
          "schema-name" = "catalog"
          "table-name"  = "%"
        }
        "rule-action" = "include"
      },
      {
        "rule-type" = "selection"
        "rule-id"   = "3"
        "rule-name" = "include-reviews"
        "object-locator" = {
          "schema-name" = "reviews"
          "table-name"  = "%"
        }
        "rule-action" = "include"
      }
    ]
  }

  postgresql_dms_forward_task_settings = {
    TargetMetadata = {
      TargetSchema             = ""
      SupportLobs              = true
      FullLobMode              = false
      LobChunkSize             = 64
      LimitedSizeLobMode       = true
      LobMaxSize               = 32
      LoadMaxFileSize          = 0
      ParallelLoadThreads      = 0
      ParallelLoadBufferSize   = 0
      BatchApplyEnabled        = false
      TaskRecoveryTableEnabled = false
    }
    FullLoadSettings = {
      TargetTablePrepMode             = "DO_NOTHING"
      CreatePkAfterFullLoad           = false
      StopTaskCachedChangesApplied    = false
      StopTaskCachedChangesNotApplied = false
      MaxFullLoadSubTasks             = 4
      TransactionConsistencyTimeout   = 600
      CommitRate                      = 10000
    }
    Logging = {
      EnableLogging = true
    }
    ValidationSettings = {
      EnableValidation    = true
      ValidationMode      = "ROW_LEVEL"
      ThreadCount         = 5
      FailureMaxCount     = 10000
      HandleCollationDiff = false
    }
    ControlTablesSettings = {
      ControlSchema                 = "dms_control"
      HistoryTimeslotInMinutes      = 5
      HistoryTableEnabled           = true
      SuspendedTablesTableEnabled   = true
      StatusTableEnabled            = true
      FullLoadExceptionTableEnabled = true
    }
  }
}

data "aws_secretsmanager_secret" "postgresql_dms_source" {
  name = local.postgresql_dms_source_secret_path
}

data "aws_secretsmanager_secret" "postgresql_dms_target" {
  name = local.postgresql_dms_target_secret_path
}

resource "aws_iam_role" "dms_vpc_role" {
  name = "dms-vpc-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "dms.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(
    var.tags,
    {
      Name      = "dms-vpc-role"
      Component = "postgresql"
      Service   = "dms"
      ManagedBy = "terraform"
      Mandate   = "08"
      Task      = "CDO08-REL-15"
    }
  )
}

resource "aws_iam_role_policy_attachment" "dms_vpc_role" {
  role       = aws_iam_role.dms_vpc_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonDMSVPCManagementRole"
}

resource "aws_iam_role" "dms_cloudwatch_logs_role" {
  name = "dms-cloudwatch-logs-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "dms.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(
    var.tags,
    {
      Name      = "dms-cloudwatch-logs-role"
      Component = "postgresql"
      Service   = "dms"
      ManagedBy = "terraform"
      Mandate   = "08"
      Task      = "CDO08-REL-15"
    }
  )
}

resource "aws_iam_role_policy_attachment" "dms_cloudwatch_logs_role" {
  role       = aws_iam_role.dms_cloudwatch_logs_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonDMSCloudWatchLogsRole"
}

resource "aws_iam_role" "postgresql_dms_secrets_access" {
  name = "techx-tf4-postgresql-dms-secrets-access"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "dms.us-east-1.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(
    var.tags,
    {
      Name      = "techx-tf4-postgresql-dms-secrets-access"
      Component = "postgresql"
      Service   = "dms"
      ManagedBy = "terraform"
      Mandate   = "08"
      Task      = "CDO08-REL-15"
    }
  )
}

resource "aws_iam_role_policy" "postgresql_dms_secrets_access" {
  name = "techx-tf4-postgresql-dms-secrets-access"
  role = aws_iam_role.postgresql_dms_secrets_access.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadPostgresqlDmsSecrets"
        Effect = "Allow"
        Action = [
          "secretsmanager:DescribeSecret",
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${local.postgresql_dms_source_secret_path}-*",
          "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:techx/tf4/rds-postgres-*"
        ]
      }
    ]
  })
}

resource "aws_security_group" "dms_postgresql_migration" {
  name        = "techx-tf4-dms-postgresql-migration"
  description = "Private AWS DMS runtime for PostgreSQL migration"
  vpc_id      = module.vpc.vpc_id

  tags = merge(
    var.tags,
    {
      Name      = "techx-tf4-dms-postgresql-migration"
      Component = "postgresql"
      Service   = "dms"
      ManagedBy = "terraform"
      Mandate   = "08"
      Task      = "CDO08-REL-15"
    }
  )
}

resource "aws_vpc_security_group_egress_rule" "dms_postgresql_to_source_bridge" {
  security_group_id = aws_security_group.dms_postgresql_migration.id
  cidr_ipv4         = var.vpc_cidr
  from_port         = 5432
  to_port           = 5432
  ip_protocol       = "tcp"
  description       = "Allow DMS to reach the temporary internal PostgreSQL NLB bridge"
}

resource "aws_vpc_security_group_egress_rule" "dms_postgresql_to_rds" {
  security_group_id            = aws_security_group.dms_postgresql_migration.id
  referenced_security_group_id = aws_security_group.rds_postgresql.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "Allow DMS to reach target RDS PostgreSQL"
}

resource "aws_vpc_security_group_egress_rule" "dms_postgresql_to_aws_services_https" {
  security_group_id = aws_security_group.dms_postgresql_migration.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  description       = "Allow DMS to retrieve PostgreSQL migration credentials from AWS services via NAT"
}

resource "aws_vpc_security_group_ingress_rule" "rds_postgresql_from_dms" {
  security_group_id            = aws_security_group.rds_postgresql.id
  referenced_security_group_id = aws_security_group.dms_postgresql_migration.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "Allow DMS replication instance to load/CDC into RDS PostgreSQL"
}

resource "aws_dms_replication_subnet_group" "postgresql" {
  replication_subnet_group_id          = "techx-tf4-postgresql-dms-private"
  replication_subnet_group_description = "Private subnet group for PostgreSQL DMS migration"
  subnet_ids                           = module.vpc.private_subnets

  tags = merge(
    var.tags,
    {
      Name      = "techx-tf4-postgresql-dms-private"
      Component = "postgresql"
      Service   = "dms"
      ManagedBy = "terraform"
      Mandate   = "08"
      Task      = "CDO08-REL-15"
    }
  )
}

resource "aws_dms_replication_instance" "postgresql" {
  replication_instance_id     = "techx-tf4-postgresql-dms"
  replication_instance_class  = "dms.t3.medium"
  allocated_storage           = 50
  apply_immediately           = true
  auto_minor_version_upgrade  = true
  publicly_accessible         = false
  multi_az                    = true
  replication_subnet_group_id = aws_dms_replication_subnet_group.postgresql.id
  vpc_security_group_ids      = [aws_security_group.dms_postgresql_migration.id]

  depends_on = [
    aws_iam_role_policy_attachment.dms_vpc_role,
    aws_iam_role_policy_attachment.dms_cloudwatch_logs_role
  ]

  tags = merge(
    var.tags,
    {
      Name      = "techx-tf4-postgresql-dms"
      Component = "postgresql"
      Service   = "dms"
      ManagedBy = "terraform"
      Mandate   = "08"
      Task      = "CDO08-REL-15"
    }
  )
}

resource "aws_dms_endpoint" "postgresql_source" {
  endpoint_id   = "techx-tf4-postgresql-source"
  endpoint_type = "source"
  engine_name   = "postgres"
  ssl_mode      = "none"
  database_name = "otel"

  extra_connection_attributes = "PluginName=test_decoding;CaptureDdls=false"

  secrets_manager_access_role_arn = aws_iam_role.postgresql_dms_secrets_access.arn
  secrets_manager_arn             = data.aws_secretsmanager_secret.postgresql_dms_source.arn

  depends_on = [aws_iam_role_policy.postgresql_dms_secrets_access]

  tags = merge(
    var.tags,
    {
      Name      = "techx-tf4-postgresql-source"
      Component = "postgresql"
      Service   = "dms"
      ManagedBy = "terraform"
      Mandate   = "08"
      Task      = "CDO08-REL-15"
    }
  )
}

resource "aws_dms_endpoint" "postgresql_target" {
  endpoint_id   = "techx-tf4-postgresql-rds-target"
  endpoint_type = "target"
  engine_name   = "postgres"
  ssl_mode      = "require"
  database_name = "otel"

  secrets_manager_access_role_arn = aws_iam_role.postgresql_dms_secrets_access.arn
  secrets_manager_arn             = data.aws_secretsmanager_secret.postgresql_dms_target.arn

  depends_on = [aws_iam_role_policy.postgresql_dms_secrets_access]

  tags = merge(
    var.tags,
    {
      Name      = "techx-tf4-postgresql-rds-target"
      Component = "postgresql"
      Service   = "dms"
      ManagedBy = "terraform"
      Mandate   = "08"
      Task      = "CDO08-REL-15"
    }
  )
}

resource "aws_dms_replication_task" "postgresql_forward" {
  replication_task_id      = "techx-tf4-postgresql-forward"
  migration_type           = "full-load-and-cdc"
  replication_instance_arn = aws_dms_replication_instance.postgresql.replication_instance_arn
  source_endpoint_arn      = aws_dms_endpoint.postgresql_source.endpoint_arn
  target_endpoint_arn      = aws_dms_endpoint.postgresql_target.endpoint_arn

  table_mappings            = jsonencode(local.postgresql_dms_table_mappings)
  replication_task_settings = jsonencode(local.postgresql_dms_forward_task_settings)

  tags = merge(
    var.tags,
    {
      Name      = "techx-tf4-postgresql-forward"
      Component = "postgresql"
      Service   = "dms"
      ManagedBy = "terraform"
      Mandate   = "08"
      Task      = "CDO08-REL-15"
    }
  )
}
