# Owner: CDO08 Reliability
# REL-22: AWS Backup retention control for Mandate 20 RDS restore readiness.

data "aws_iam_policy_document" "rds_backup_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["backup.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "rds_backup" {
  name               = "techx-tf4-rel22-rds-backup"
  assume_role_policy = data.aws_iam_policy_document.rds_backup_assume_role.json
  description        = "AWS Backup service role for REL-22 RDS PostgreSQL recovery points"

  tags = merge(
    var.tags,
    {
      Name      = "techx-tf4-rel22-rds-backup"
      Component = "postgresql"
      Service   = "aws-backup"
      ManagedBy = "terraform"
      Mandate   = "20"
      Task      = "CDO08-REL-22"
    }
  )
}

resource "aws_iam_role_policy_attachment" "rds_backup_backup" {
  role       = aws_iam_role.rds_backup.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForBackup"
}

resource "aws_iam_role_policy_attachment" "rds_backup_restore" {
  role       = aws_iam_role.rds_backup.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForRestores"
}

resource "aws_backup_vault" "rds_postgresql" {
  name = "techx-tf4-rel22-rds-postgresql"

  tags = merge(
    var.tags,
    {
      Name      = "techx-tf4-rel22-rds-postgresql"
      Component = "postgresql"
      Service   = "aws-backup"
      ManagedBy = "terraform"
      Mandate   = "20"
      Task      = "CDO08-REL-22"
      Retention = "35-days"
    }
  )
}

resource "aws_backup_plan" "rds_postgresql" {
  name = "techx-tf4-rel22-rds-postgresql-35d"

  rule {
    rule_name         = "daily-rds-postgresql-35d"
    target_vault_name = aws_backup_vault.rds_postgresql.name
    schedule          = "cron(0 17 ? * * *)"
    start_window      = 60
    completion_window = 180

    lifecycle {
      delete_after = 35
    }
  }

  tags = merge(
    var.tags,
    {
      Name      = "techx-tf4-rel22-rds-postgresql-35d"
      Component = "postgresql"
      Service   = "aws-backup"
      ManagedBy = "terraform"
      Mandate   = "20"
      Task      = "CDO08-REL-22"
      Retention = "35-days"
    }
  )
}

resource "aws_backup_selection" "rds_postgresql" {
  iam_role_arn = aws_iam_role.rds_backup.arn
  name         = "techx-tf4-rel22-rds-postgresql"
  plan_id      = aws_backup_plan.rds_postgresql.id
  resources    = [aws_db_instance.postgresql.arn]
}
