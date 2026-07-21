#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_PROFILE="${AWS_PROFILE:-tf4}"
export AWS_PAGER="${AWS_PAGER:-}"
NAMESPACE="${NAMESPACE:-techx-tf4}"
SOURCE_DEPLOY="${SOURCE_DEPLOY:-postgresql}"
SOURCE_DB_USER="${SOURCE_DB_USER:-root}"
DB_NAME="${DB_NAME:-otel}"
BACKUP_BUCKET="${BACKUP_BUCKET:-tf4-postgresql-migration-backups-511825856493-us-east-1}"
TS="${TS:-$(date -u +%Y%m%d-%H%M%S)}"
S3_PREFIX="${S3_PREFIX:-rel15/precutover/$TS}"
OUT_DIR="${OUT_DIR:-.}"
BACKUP_FILE="$OUT_DIR/postgresql-data-$TS.dump"
LIST_FILE="$OUT_DIR/postgresql-data-$TS.list"
CONFIRM_BACKUP_TO_S3="${CONFIRM_BACKUP_TO_S3:-}"

if [[ "${1:-}" == "--yes" ]]; then
  CONFIRM_BACKUP_TO_S3="YES"
fi

if [[ "$CONFIRM_BACKUP_TO_S3" != "YES" ]]; then
  echo "[ERROR] This creates a source dump and uploads it to S3. Re-run with CONFIRM_BACKUP_TO_S3=YES or pass --yes." >&2
  exit 1
fi

command -v aws >/dev/null 2>&1 || { echo "[ERROR] Missing aws CLI" >&2; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo "[ERROR] Missing kubectl" >&2; exit 1; }

remote_dump="/tmp/postgresql-data-$TS.dump"
remote_list="/tmp/postgresql-data-$TS.list"

cleanup_remote() {
  kubectl -n "$NAMESPACE" exec "deploy/$SOURCE_DEPLOY" -- rm -f "$remote_dump" "$remote_list" >/dev/null 2>&1 || true
}
trap cleanup_remote EXIT

echo "[INFO] Creating custom-format dump inside source pod..."
kubectl -n "$NAMESPACE" exec "deploy/$SOURCE_DEPLOY" -- \
  sh -c "pg_dump -U '$SOURCE_DB_USER' -d '$DB_NAME' --format=custom --no-owner --no-privileges -f '$remote_dump' && pg_restore --list '$remote_dump' > '$remote_list' && sha256sum '$remote_dump' '$remote_list'"

echo "[INFO] Copying dump and list files to local workspace..."
kubectl -n "$NAMESPACE" exec "deploy/$SOURCE_DEPLOY" -- cat "$remote_dump" > "$BACKUP_FILE"
kubectl -n "$NAMESPACE" exec "deploy/$SOURCE_DEPLOY" -- cat "$remote_list" > "$LIST_FILE"

echo "[INFO] Local file hashes:"
if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$BACKUP_FILE" "$LIST_FILE"
fi

echo "[INFO] Uploading to s3://$BACKUP_BUCKET/$S3_PREFIX/"
aws s3 cp "$BACKUP_FILE" "s3://$BACKUP_BUCKET/$S3_PREFIX/$(basename "$BACKUP_FILE")" --region "$AWS_REGION" --profile "$AWS_PROFILE"
aws s3 cp "$LIST_FILE" "s3://$BACKUP_BUCKET/$S3_PREFIX/$(basename "$LIST_FILE")" --region "$AWS_REGION" --profile "$AWS_PROFILE"

echo "[INFO] Uploaded objects:"
aws s3 ls "s3://$BACKUP_BUCKET/$S3_PREFIX/" --region "$AWS_REGION" --profile "$AWS_PROFILE"

echo "[OK] Backup uploaded to S3."
