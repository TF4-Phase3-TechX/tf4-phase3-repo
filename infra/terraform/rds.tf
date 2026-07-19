# Owner: CDO08 Reliability
# REL-14: Managed PostgreSQL baseline for Mandate 8.
# This provisions the private RDS target only; migration/cutover remains in REL-15.

resource "aws_security_group" "rds_postgresql" {
  name        = "techx-tf4-rds-postgresql"
  description = "Private RDS PostgreSQL access for TechX workloads"
  vpc_id      = module.vpc.vpc_id

  tags = merge(
    var.tags,
    {
      Name      = "techx-tf4-rds-postgresql"
      Component = "postgresql"
      Service   = "rds"
      ManagedBy = "terraform"
      Mandate   = "08"
      Task      = "CDO08-REL-14"
    }
  )
}

resource "aws_vpc_security_group_ingress_rule" "rds_postgresql_from_eks_nodes" {
  security_group_id            = aws_security_group.rds_postgresql.id
  referenced_security_group_id = module.eks.node_security_group_id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "Allow EKS worker nodes to reach RDS PostgreSQL"
}

resource "aws_vpc_security_group_egress_rule" "rds_postgresql_all_egress" {
  security_group_id = aws_security_group.rds_postgresql.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "Allow outbound responses and AWS-managed maintenance traffic"
}

resource "aws_db_subnet_group" "postgresql" {
  name        = "techx-tf4-postgresql-private"
  description = "Private subnet group for TechX RDS PostgreSQL"
  subnet_ids  = module.vpc.private_subnets

  tags = merge(
    var.tags,
    {
      Name      = "techx-tf4-postgresql-private"
      Component = "postgresql"
      Service   = "rds"
      ManagedBy = "terraform"
      Mandate   = "08"
      Task      = "CDO08-REL-14"
    }
  )
}

resource "aws_db_parameter_group" "postgresql" {
  name        = "techx-tf4-postgresql17-dms"
  family      = "postgres17"
  description = "PostgreSQL 17 parameters for TechX RDS migration target"

  parameter {
    name         = "rds.logical_replication"
    value        = "1"
    apply_method = "pending-reboot"
  }

  tags = merge(
    var.tags,
    {
      Name      = "techx-tf4-postgresql17-dms"
      Component = "postgresql"
      Service   = "rds"
      ManagedBy = "terraform"
      Mandate   = "08"
      Task      = "CDO08-REL-14"
    }
  )
}

resource "aws_db_instance" "postgresql" {
  identifier = "techx-tf4-postgresql"

  engine         = "postgres"
  engine_version = "17.6"
  instance_class = "db.t4g.micro"

  db_name  = "otel"
  username = "postgres"

  manage_master_user_password = true

  allocated_storage     = 20
  max_allocated_storage = 100
  storage_type          = "gp3"
  storage_encrypted     = true

  multi_az               = true
  db_subnet_group_name   = aws_db_subnet_group.postgresql.name
  vpc_security_group_ids = [aws_security_group.rds_postgresql.id]
  publicly_accessible    = false

  parameter_group_name = aws_db_parameter_group.postgresql.name

  backup_retention_period = 7
  backup_window           = "18:00-19:00"
  maintenance_window      = "sun:19:00-sun:20:00"

  auto_minor_version_upgrade = true
  copy_tags_to_snapshot      = true
  deletion_protection        = true
  delete_automated_backups   = false
  skip_final_snapshot        = false
  final_snapshot_identifier  = "techx-tf4-postgresql-final"

  performance_insights_enabled = false
  monitoring_interval          = 0

  tags = merge(
    var.tags,
    {
      Name      = "techx-tf4-postgresql"
      Component = "postgresql"
      Service   = "rds"
      ManagedBy = "terraform"
      Mandate   = "08"
      Task      = "CDO08-REL-14"
    }
  )
}
