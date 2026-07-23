# Owner: CDO08 Security/Platform
# CDO08-REL-24 - Separate backup/restore/deletion duties for protected recovery assets.

locals {
  rel24_ci_apply_role_arn  = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:role/tf4-github-actions-terraform-apply"
  rel24_plan_role_arn      = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:role/tf4-github-actions-plan"
  rel24_deploy_role_arn    = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:role/tf4-github-actions-eks-deploy"
  rel24_account_root_arn   = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"
  rel24_msk_archive_bucket = "tf4-msk-orders-archive-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  rel24_msk_archive_prefix = "orders/"
  rel24_backup_admin_name  = "tf4-rel24-backup-admin"
  rel24_restore_role_name  = "tf4-rel24-restore-operator"
  rel24_break_glass_name   = "tf4-rel24-backup-delete-break-glass"

  rel24_normal_operator_role_arns = [
    local.rel24_ci_apply_role_arn,
    local.rel24_plan_role_arn,
    local.rel24_deploy_role_arn,
    local.eks_admin_access_entries["sso_deploy_operator"],
    local.eks_admin_access_entries["github_actions_deploy"],
  ]

  # Terraform apply is protected by its identity boundary/explicit deny in bootstrap.
  # Keep it out of S3 bucket-policy control-change denies so reviewed IaC can maintain the policy.
  rel24_bucket_policy_operator_role_arns = [
    local.rel24_plan_role_arn,
    local.rel24_deploy_role_arn,
    local.eks_admin_access_entries["sso_deploy_operator"],
    local.eks_admin_access_entries["github_actions_deploy"],
  ]

  rel24_protected_object_arns = [
    "${aws_s3_bucket.postgresql_migration_backups.arn}/${local.postgresql_migration_backup_prefix}*",
    "${aws_s3_bucket.config_archive.arn}/${local.aws_config_evidence_prefix}*",
    "${aws_s3_bucket.config_staging.arn}/${local.aws_config_evidence_prefix}*",
    "arn:${data.aws_partition.current.partition}:s3:::${local.rel24_msk_archive_bucket}/${local.rel24_msk_archive_prefix}*",
  ]

  rel24_rds_snapshot_arns = [
    "arn:${data.aws_partition.current.partition}:rds:${var.aws_region}:${data.aws_caller_identity.current.account_id}:snapshot:techx-tf4-postgresql*",
    "arn:${data.aws_partition.current.partition}:rds:${var.aws_region}:${data.aws_caller_identity.current.account_id}:snapshot:rds:techx-tf4-postgresql*",
  ]

  rel24_elasticache_snapshot_arns = [
    "arn:${data.aws_partition.current.partition}:elasticache:${var.aws_region}:${data.aws_caller_identity.current.account_id}:snapshot:techx-tf4-valkey-cart*",
  ]

  rel24_protected_delete_actions = [
    "backup:DeleteBackupVault",
    "backup:DeleteBackupVaultAccessPolicy",
    "backup:DeleteBackupVaultLockConfiguration",
    "backup:DeleteRecoveryPoint",
    "elasticache:DeleteCacheCluster",
    "elasticache:DeleteReplicationGroup",
    "elasticache:DeleteSnapshot",
    "kafka-cluster:DeleteTopic",
    "kafka:DeleteCluster",
    "kafka:DeleteClusterPolicy",
    "kafka:DeleteConfiguration",
    "kms:DisableKey",
    "kms:DisableKeyRotation",
    "kms:ScheduleKeyDeletion",
    "rds:DeleteDBCluster",
    "rds:DeleteDBClusterAutomatedBackup",
    "rds:DeleteDBClusterSnapshot",
    "rds:DeleteDBInstance",
    "rds:DeleteDBInstanceAutomatedBackup",
    "rds:DeleteDBSnapshot",
    "s3:BypassGovernanceRetention",
    "s3:DeleteBucket",
    "s3:DeleteBucketPolicy",
    "s3:DeleteObject",
    "s3:DeleteObjectTagging",
    "s3:DeleteObjectVersion",
    "s3:PutBucketObjectLockConfiguration",
    "s3:PutBucketVersioning",
    "s3:PutLifecycleConfiguration",
    "s3:PutObjectLegalHold",
    "s3:PutObjectRetention",
  ]

  rel24_tags = merge(var.tags, {
    Owner   = "CDO08"
    Pillar  = "SecurityReliability"
    Mandate = "20"
    Task    = "CDO08-REL-24"
  })
}

data "aws_iam_policy_document" "rel24_approved_operations_assume_role" {
  statement {
    sid     = "AllowApprovedInAccountAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole", "sts:TagSession"]

    principals {
      type        = "AWS"
      identifiers = [local.rel24_account_root_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:PrincipalAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/Rel24Approval"
      values   = ["approved"]
    }

    condition {
      test     = "Null"
      variable = "aws:RequestTag/ChangeId"
      values   = ["false"]
    }
  }
}

data "aws_iam_policy_document" "rel24_break_glass_assume_role" {
  statement {
    sid     = "AllowDeletionApprovedInAccountAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole", "sts:TagSession"]

    principals {
      type        = "AWS"
      identifiers = [local.rel24_account_root_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:PrincipalAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/Rel24DeletionApproved"
      values   = ["true"]
    }

    condition {
      test     = "Null"
      variable = "aws:RequestTag/ChangeId"
      values   = ["false"]
    }
  }
}

resource "aws_iam_role" "rel24_backup_admin" {
  name               = local.rel24_backup_admin_name
  description        = "CDO08-REL-24 role for approved backup administration without source backup deletion."
  assume_role_policy = data.aws_iam_policy_document.rel24_approved_operations_assume_role.json

  max_session_duration = 3600
  tags                 = local.rel24_tags
}

resource "aws_iam_role" "rel24_restore_operator" {
  name               = local.rel24_restore_role_name
  description        = "CDO08-REL-24 role for approved restores without source backup deletion."
  assume_role_policy = data.aws_iam_policy_document.rel24_approved_operations_assume_role.json

  max_session_duration = 3600
  tags                 = local.rel24_tags
}

resource "aws_iam_role" "rel24_backup_delete_break_glass" {
  name               = local.rel24_break_glass_name
  description        = "CDO08-REL-24 time-boxed break-glass role for approved protected backup/archive deletion."
  assume_role_policy = data.aws_iam_policy_document.rel24_break_glass_assume_role.json

  max_session_duration = 3600
  tags                 = local.rel24_tags
}

data "aws_iam_policy_document" "rel24_deny_protected_deletes" {
  statement {
    sid       = "DenyProtectedRecoveryAssetDeletion"
    effect    = "Deny"
    actions   = local.rel24_protected_delete_actions
    resources = ["*"]
  }
}

data "aws_iam_policy_document" "rel24_backup_admin" {
  source_policy_documents = [data.aws_iam_policy_document.rel24_deny_protected_deletes.json]

  statement {
    sid    = "ReadBackupAndRecoveryInventory"
    effect = "Allow"
    actions = [
      "backup:Describe*",
      "backup:Get*",
      "backup:List*",
      "elasticache:Describe*",
      "elasticache:ListTagsForResource",
      "kafka:Describe*",
      "kafka:GetBootstrapBrokers",
      "kafka:List*",
      "rds:Describe*",
      "rds:ListTagsForResource",
      "s3:GetBucketLocation",
      "s3:GetBucketVersioning",
      "s3:GetEncryptionConfiguration",
      "s3:GetLifecycleConfiguration",
      "s3:ListBucket",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "CreateRdsRecoveryPoints"
    effect = "Allow"
    actions = [
      "rds:AddTagsToResource",
      "rds:CopyDBSnapshot",
      "rds:CreateDBSnapshot",
    ]
    resources = concat(
      [aws_db_instance.postgresql.arn],
      local.rel24_rds_snapshot_arns
    )
  }

  statement {
    sid    = "CreateValkeyRecoveryPoints"
    effect = "Allow"
    actions = [
      "elasticache:AddTagsToResource",
      "elasticache:CopySnapshot",
      "elasticache:CreateSnapshot",
    ]
    resources = concat(
      [aws_elasticache_replication_group.valkey_cart.arn],
      local.rel24_elasticache_snapshot_arns
    )
  }

  statement {
    sid    = "WriteArchiveObjects"
    effect = "Allow"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:PutObject",
      "s3:PutObjectTagging",
    ]
    resources = local.rel24_protected_object_arns
  }

  statement {
    sid    = "StartAwsBackupJobs"
    effect = "Allow"
    actions = [
      "backup:StartBackupJob",
      "backup:TagResource",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "UseEncryptionKeysForBackupServices"
    effect = "Allow"
    actions = [
      "kms:CreateGrant",
      "kms:Decrypt",
      "kms:DescribeKey",
      "kms:Encrypt",
      "kms:GenerateDataKey*",
      "kms:ReEncrypt*",
    ]
    resources = ["*"]

    condition {
      test     = "StringLike"
      variable = "kms:ViaService"
      values = [
        "backup.${var.aws_region}.amazonaws.com",
        "elasticache.${var.aws_region}.amazonaws.com",
        "kafka.${var.aws_region}.amazonaws.com",
        "rds.${var.aws_region}.amazonaws.com",
        "s3.${var.aws_region}.amazonaws.com",
      ]
    }
  }
}

resource "aws_iam_role_policy" "rel24_backup_admin" {
  name   = "tf4-rel24-backup-admin"
  role   = aws_iam_role.rel24_backup_admin.id
  policy = data.aws_iam_policy_document.rel24_backup_admin.json
}

data "aws_iam_policy_document" "rel24_restore_operator" {
  source_policy_documents = [data.aws_iam_policy_document.rel24_deny_protected_deletes.json]

  statement {
    sid    = "ReadRecoverySources"
    effect = "Allow"
    actions = [
      "elasticache:Describe*",
      "elasticache:ListTagsForResource",
      "kafka:Describe*",
      "kafka:GetBootstrapBrokers",
      "kafka:List*",
      "rds:Describe*",
      "rds:ListTagsForResource",
      "s3:GetBucketLocation",
      "s3:GetObject",
      "s3:GetObjectTagging",
      "s3:GetObjectVersion",
      "s3:ListBucket",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "RestoreRdsFromSnapshots"
    effect = "Allow"
    actions = [
      "rds:AddTagsToResource",
      "rds:CreateDBInstance",
      "rds:RestoreDBClusterFromSnapshot",
      "rds:RestoreDBInstanceFromDBSnapshot",
      "rds:RestoreDBInstanceToPointInTime",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "RestoreValkeyFromSnapshots"
    effect = "Allow"
    actions = [
      "elasticache:AddTagsToResource",
      "elasticache:CreateCacheCluster",
      "elasticache:CreateReplicationGroup",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "CreateReplayMskResources"
    effect = "Allow"
    actions = [
      "kafka:CreateCluster",
      "kafka:CreateConfiguration",
      "kafka:TagResource",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "UseEncryptionKeysForRestoreServices"
    effect = "Allow"
    actions = [
      "kms:CreateGrant",
      "kms:Decrypt",
      "kms:DescribeKey",
      "kms:Encrypt",
      "kms:GenerateDataKey*",
      "kms:ReEncrypt*",
    ]
    resources = ["*"]

    condition {
      test     = "StringLike"
      variable = "kms:ViaService"
      values = [
        "elasticache.${var.aws_region}.amazonaws.com",
        "kafka.${var.aws_region}.amazonaws.com",
        "rds.${var.aws_region}.amazonaws.com",
        "s3.${var.aws_region}.amazonaws.com",
      ]
    }
  }
}

resource "aws_iam_role_policy" "rel24_restore_operator" {
  name   = "tf4-rel24-restore-operator"
  role   = aws_iam_role.rel24_restore_operator.id
  policy = data.aws_iam_policy_document.rel24_restore_operator.json
}

data "aws_iam_policy_document" "rel24_backup_delete_break_glass" {
  statement {
    sid    = "ReadRecoveryAssetsBeforeApprovedDeletion"
    effect = "Allow"
    actions = [
      "backup:Describe*",
      "backup:Get*",
      "backup:List*",
      "elasticache:Describe*",
      "kafka:Describe*",
      "kafka:List*",
      "rds:Describe*",
      "s3:GetBucketLocation",
      "s3:GetObjectRetention",
      "s3:GetObjectVersion",
      "s3:ListBucket",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "AllowApprovedProtectedDeletionOnlyWithSessionTag"
    effect    = "Allow"
    actions   = local.rel24_protected_delete_actions
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:PrincipalTag/Rel24DeletionApproved"
      values   = ["true"]
    }
  }
}

resource "aws_iam_role_policy" "rel24_backup_delete_break_glass" {
  name   = "tf4-rel24-backup-delete-break-glass"
  role   = aws_iam_role.rel24_backup_delete_break_glass.id
  policy = data.aws_iam_policy_document.rel24_backup_delete_break_glass.json
}

data "aws_iam_policy_document" "rel24_postgresql_migration_backups_bucket" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.postgresql_migration_backups.arn,
      "${aws_s3_bucket.postgresql_migration_backups.arn}/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  statement {
    sid    = "DenyNormalOperatorBackupControlChanges"
    effect = "Deny"
    actions = [
      "s3:DeleteBucket",
      "s3:DeleteBucketPolicy",
      "s3:PutBucketOwnershipControls",
      "s3:PutBucketPolicy",
      "s3:PutBucketPublicAccessBlock",
      "s3:PutBucketVersioning",
      "s3:PutEncryptionConfiguration",
      "s3:PutLifecycleConfiguration",
    ]
    resources = [aws_s3_bucket.postgresql_migration_backups.arn]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:PrincipalArn"
      values   = local.rel24_bucket_policy_operator_role_arns
    }
  }

  statement {
    sid    = "DenyNormalOperatorBackupObjectDeletion"
    effect = "Deny"
    actions = [
      "s3:BypassGovernanceRetention",
      "s3:DeleteObject",
      "s3:DeleteObjectTagging",
      "s3:DeleteObjectVersion",
      "s3:PutObjectLegalHold",
      "s3:PutObjectRetention",
    ]
    resources = ["${aws_s3_bucket.postgresql_migration_backups.arn}/${local.postgresql_migration_backup_prefix}*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:PrincipalArn"
      values   = local.rel24_bucket_policy_operator_role_arns
    }
  }
}

resource "aws_s3_bucket_policy" "rel24_postgresql_migration_backups" {
  bucket = aws_s3_bucket.postgresql_migration_backups.id
  policy = data.aws_iam_policy_document.rel24_postgresql_migration_backups_bucket.json

  depends_on = [aws_s3_bucket_public_access_block.postgresql_migration_backups]
}
