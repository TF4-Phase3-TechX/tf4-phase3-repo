# REL-15 PostgreSQL Migration Scripts

Người phụ trách: Hoàng Nam / CDO08

Bộ script này ghi lại flow runtime đang dùng cho migration PostgreSQL self-hosted trong EKS sang Amazon RDS PostgreSQL.

## Mục tiêu

1. Verify các điều kiện trước migration: source PostgreSQL, RDS, DMS và migration bridge.
2. Export schema từ PostgreSQL source.
3. Restore schema lên RDS trước khi chạy DMS vì DMS task đang dùng `TargetTablePrepMode = DO_NOTHING`.
4. Start và monitor DMS task `full-load-and-cdc`.
5. Verify row parity và reset sequence trên RDS trước cutover gate.

## Lưu ý an toàn

- Script không in secret value.
- Các script có tác động live đều yêu cầu biến xác nhận `CONFIRM_*`.
- Không tự động cutover traffic app sang RDS trong bộ script này. Cutover là bước vận hành riêng, cần approval gate và evidence parity trước khi thực hiện.
- DMS source endpoint hiện dùng `PluginName=test_decoding;CaptureDdls=false`.

## Runtime mặc định

```text
AWS_REGION=us-east-1
AWS_PROFILE=tf4
NAMESPACE=techx-tf4
SOURCE_DEPLOY=postgresql
SOURCE_DB_USER=root
DB_NAME=otel
RDS_HOST=techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com
DMS_REPLICATION_INSTANCE_ARN=arn:aws:dms:us-east-1:511825856493:rep:JPOXJ6J6NVEEVK6IDAJGAE23HY
DMS_TASK_ARN=arn:aws:dms:us-east-1:511825856493:task:7SDVOIB6RVGXJP3M5WK72BNYKY
DMS_TASK_ID=techx-tf4-postgresql-forward
```

## Script hiện có

```text
01-preflight-check.sh
02-export-schema.sh
03-restore-schema-to-rds.sh
04-start-dms-forward.sh
05-monitor-dms-forward.sh
06-parity-counts.sh
07-reset-sequences.sh
09-backup-to-s3.sh
```

Các script liên quan trực tiếp đến cutover như khóa ghi source, promote Argo Rollout và rollback traffic sẽ được bổ sung trong bước cutover riêng.
