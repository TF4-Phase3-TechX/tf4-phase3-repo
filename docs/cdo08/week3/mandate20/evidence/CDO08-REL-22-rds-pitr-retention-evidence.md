# CDO08-REL-22 RDS PITR and Retention Evidence

**Owner:** Hoàng Nam
**Team:** CDO08
**Task:** CDO08-REL-22
**Subtask:** Verify RDS PITR and implement approved retention policy
**Ngày ghi nhận:** 2026-07-23

Tài liệu này ghi lại evidence cho RDS PostgreSQL/accounting trong Mandate 20. Evidence không chứa plaintext credential, secret value hoặc dữ liệu production.

---

## 1. Output Của Subtask

Subtask 1 cần tạo ra các output sau:

- RDS automated backup/PITR baseline: retention 7 ngày, backup window, latest restorable time.
- RDS safety baseline: private endpoint, encryption, deletion protection, Multi-AZ.
- Restore permission baseline: AWS Backup service role có policy backup và restore.
- Recovery point 35 ngày: recovery point thật trong AWS Backup vault, encrypted, có `RecoveryPointArn`, `CreationDate` và `DeleteAt`.
- Command evidence để REL-25 dùng lại khi chạy restore test.

Kết luận hiện tại:

| Hạng mục               | Trạng thái | Evidence chính                                                  |
| ---------------------- | ---------- | --------------------------------------------------------------- |
| Automated backup/PITR  | PASS       | `BackupRetentionPeriod=7`, `LatestRestorableTime` quan sát được |
| Backup window          | PASS       | `PreferredBackupWindow=18:00-19:00`                             |
| Encryption             | PASS       | RDS và recovery point đều có KMS key                            |
| Deletion protection    | PASS       | `DeletionProtection=true`                                       |
| Restore permissions    | PASS       | AWS Backup role có `AWSBackupServiceRolePolicyForRestores`      |
| Recovery point 35 ngày | PASS       | `DeleteAt=2026-08-27T15:19:58.948000+07:00`                     |
| Production data impact | PASS       | Không restore, không delete, không thay đổi dữ liệu production  |

---

## 2. RDS PITR Baseline

Lệnh kiểm tra:

```powershell
aws rds describe-db-instances `
  --db-instance-identifier techx-tf4-postgresql `
  --region us-east-1 `
  --profile tf4 `
  --query "DBInstances[0].{Id:DBInstanceIdentifier,Status:DBInstanceStatus,Engine:Engine,EngineVersion:EngineVersion,Public:PubliclyAccessible,StorageEncrypted:StorageEncrypted,KmsKeyId:KmsKeyId,BackupRetentionPeriod:BackupRetentionPeriod,PreferredBackupWindow:PreferredBackupWindow,LatestRestorableTime:LatestRestorableTime,DeletionProtection:DeletionProtection,MultiAZ:MultiAZ,Arn:DBInstanceArn}"
```

Output chính:

```json
{
    "Id": "techx-tf4-postgresql",
    "Status": "available",
    "Engine": "postgres",
    "EngineVersion": "17.9",
    "Public": false,
    "StorageEncrypted": true,
    "KmsKeyId": "arn:aws:kms:us-east-1:511825856493:key/8e5f51a9-8299-4c33-93d1-fdd85cd95d2a",
    "BackupRetentionPeriod": 7,
    "PreferredBackupWindow": "18:00-19:00",
    "LatestRestorableTime": "2026-07-23T08:37:38+00:00",
    "DeletionProtection": true,
    "MultiAZ": true,
    "Arn": "arn:aws:rds:us-east-1:511825856493:db:techx-tf4-postgresql"
}
```

Kết luận:

- RDS PostgreSQL đang `available`.
- Endpoint không public.
- Storage encryption đang bật.
- Automated backup retention là 7 ngày.
- PITR quan sát được qua `LatestRestorableTime`.
- Deletion protection và Multi-AZ đang bật.

---

## 3. AWS Backup Retention Control

Terraform apply đã tạo các output sau:

```text
rds_postgresql_backup_plan_id = "aa4e9e58-dd96-4fd8-b3c5-22fd3529ebca"
rds_postgresql_backup_role_arn = "arn:aws:iam::511825856493:role/techx-tf4-rel22-rds-backup"
rds_postgresql_backup_vault_arn = "arn:aws:backup:us-east-1:511825856493:backup-vault:techx-tf4-rel22-rds-postgresql"
rds_postgresql_backup_vault_name = "techx-tf4-rel22-rds-postgresql"
rds_postgresql_instance_arn = "arn:aws:rds:us-east-1:511825856493:db:techx-tf4-postgresql"
```

Lệnh kiểm tra vault:

```powershell
aws backup describe-backup-vault `
  --backup-vault-name techx-tf4-rel22-rds-postgresql `
  --region us-east-1 `
  --profile tf4 `
  --query "{Name:BackupVaultName,Arn:BackupVaultArn,RecoveryPoints:NumberOfRecoveryPoints,EncryptionKeyArn:EncryptionKeyArn,CreationDate:CreationDate}"
```

Output chính:

```json
{
    "Name": "techx-tf4-rel22-rds-postgresql",
    "Arn": "arn:aws:backup:us-east-1:511825856493:backup-vault:techx-tf4-rel22-rds-postgresql",
    "RecoveryPoints": 1,
    "EncryptionKeyArn": "arn:aws:kms:us-east-1:511825856493:key/bffa0a1c-e484-40d1-b87e-43c7162e09be",
    "CreationDate": "2026-07-23T15:06:13.933000+07:00"
}
```

Kết luận:

- AWS Backup vault đã tồn tại.
- Vault có encryption key.
- Vault hiện có 1 recovery point.

---

## 4. Restore Permission Baseline

Lệnh kiểm tra:

```powershell
aws iam list-attached-role-policies `
  --role-name techx-tf4-rel22-rds-backup `
  --region us-east-1 `
  --profile tf4 `
  --query "AttachedPolicies[*].{PolicyName:PolicyName,PolicyArn:PolicyArn}"
```

Output chính:

```json
[
    {
        "PolicyName": "AWSBackupServiceRolePolicyForRestores",
        "PolicyArn": "arn:aws:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForRestores"
    },
    {
        "PolicyName": "AWSBackupServiceRolePolicyForBackup",
        "PolicyArn": "arn:aws:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForBackup"
    }
]
```

Kết luận:

- AWS Backup service role có quyền backup.
- AWS Backup service role có quyền restore để REL-25 dùng trong restore test.

---

## 5. On-Demand Recovery Point 35 Ngày

Do AWS Backup plan mới được apply trong ngày 2026-07-23, chưa có recovery point từ lịch daily tại thời điểm kiểm tra. Để tạo evidence thật ngay cho REL-22, đã chạy on-demand backup job với lifecycle 35 ngày.

Lệnh chạy:

```powershell
aws backup start-backup-job `
  --backup-vault-name techx-tf4-rel22-rds-postgresql `
  --resource-arn arn:aws:rds:us-east-1:511825856493:db:techx-tf4-postgresql `
  --iam-role-arn arn:aws:iam::511825856493:role/techx-tf4-rel22-rds-backup `
  --lifecycle DeleteAfterDays=35 `
  --region us-east-1 `
  --profile tf4 `
  --query "{BackupJobId:BackupJobId,RecoveryPointArn:RecoveryPointArn,CreationDate:CreationDate}" `
  --output table
```

Output submit job:

```text
BackupJobId      193efb00-b004-4b95-96e2-194b6e3c6885
CreationDate     2026-07-23T15:19:58.948000+07:00
RecoveryPointArn None
```

Lệnh monitor:

```powershell
aws backup describe-backup-job `
  --backup-job-id 193efb00-b004-4b95-96e2-194b6e3c6885 `
  --region us-east-1 `
  --profile tf4 `
  --query "{State:State,StatusMessage:StatusMessage,PercentDone:PercentDone,CreationDate:CreationDate,CompletionDate:CompletionDate,RecoveryPointArn:RecoveryPointArn,BackupSizeInBytes:BackupSizeInBytes}" `
  --output table
```

Output completed:

```text
BackupSizeInBytes 0
CompletionDate    2026-07-23T15:24:03.962000+07:00
CreationDate      2026-07-23T15:19:58.948000+07:00
PercentDone       100.0
RecoveryPointArn  arn:aws:rds:us-east-1:511825856493:snapshot:awsbackup:job-193efb00-b004-4b95-96e2-194b6e3c6885
State             COMPLETED
StatusMessage     None
```

---

## 6. Recovery Point Retention Evidence

Lệnh kiểm tra recovery point trong vault:

```powershell
aws backup list-recovery-points-by-backup-vault `
  --backup-vault-name techx-tf4-rel22-rds-postgresql `
  --region us-east-1 `
  --profile tf4 `
  --query "RecoveryPoints[*].{Status:Status,ResourceType:ResourceType,ResourceArn:ResourceArn,RecoveryPointArn:RecoveryPointArn,CreationDate:CreationDate,DeleteAt:CalculatedLifecycle.DeleteAt,EncryptionKeyArn:EncryptionKeyArn}" `
  --output table
```

Output chính:

```text
CreationDate     2026-07-23T15:19:58.948000+07:00
DeleteAt         2026-08-27T15:19:58.948000+07:00
EncryptionKeyArn arn:aws:kms:us-east-1:511825856493:key/8e5f51a9-8299-4c33-93d1-fdd85cd95d2a
RecoveryPointArn arn:aws:rds:us-east-1:511825856493:snapshot:awsbackup:job-193efb00-b004-4b95-96e2-194b6e3c6885
ResourceArn      arn:aws:rds:us-east-1:511825856493:db:techx-tf4-postgresql
ResourceType     RDS
Status           COMPLETED
```

Kết luận:

- Recovery point đã `COMPLETED`.
- Recovery point thuộc resource type `RDS`.
- Recovery point trỏ đúng DB `techx-tf4-postgresql`.
- Recovery point được mã hóa.
- Retention 35 ngày: từ `2026-07-23T15:19:58.948000+07:00` đến `2026-08-27T15:19:58.948000+07:00`.

---

## 7. Production Safety

Các thao tác đã thực hiện:

- Read-only verification với RDS, IAM và AWS Backup.
- Tạo AWS Backup recovery point cho RDS.

Các thao tác không thực hiện:

- Không restore database.
- Không overwrite hoặc truncate dữ liệu.
- Không delete snapshot/recovery point.
- Không thay đổi application connection string.
- Không thay đổi workload runtime.

Kết luận: subtask này không thay đổi production data.

---

## 8. Identifier Cho Restore Test

REL-25 có thể dùng các identifier sau để làm restore test trong môi trường isolated:

| Field                    | Value                                                                                            |
| ------------------------ | ------------------------------------------------------------------------------------------------ |
| Source RDS ARN           | `arn:aws:rds:us-east-1:511825856493:db:techx-tf4-postgresql`                                     |
| Backup vault             | `techx-tf4-rel22-rds-postgresql`                                                                 |
| Backup plan ID           | `aa4e9e58-dd96-4fd8-b3c5-22fd3529ebca`                                                           |
| Backup role ARN          | `arn:aws:iam::511825856493:role/techx-tf4-rel22-rds-backup`                                      |
| Backup job ID            | `193efb00-b004-4b95-96e2-194b6e3c6885`                                                           |
| Recovery point ARN       | `arn:aws:rds:us-east-1:511825856493:snapshot:awsbackup:job-193efb00-b004-4b95-96e2-194b6e3c6885` |
| Recovery point created   | `2026-07-23T15:19:58.948000+07:00`                                                               |
| Recovery point delete at | `2026-08-27T15:19:58.948000+07:00`                                                               |

---

## 9. Kết Luận

Subtask `Verify RDS PITR and implement approved retention policy` đã đạt acceptance criteria:

- PITR window quan sát được qua `LatestRestorableTime`.
- Automated backup retention 7 ngày và backup window đã được verify.
- RDS encryption, deletion protection và Multi-AZ đã được verify.
- AWS Backup recovery point 35 ngày đã tồn tại và mã hóa.
- Restore service role đã có policy restore.
- Không thay đổi production data.
