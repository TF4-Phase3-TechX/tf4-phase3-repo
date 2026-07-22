#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-techx-tf4}"
SOURCE_DEPLOY="${SOURCE_DEPLOY:-postgresql}"
SOURCE_DB_USER="${SOURCE_DB_USER:-root}"
DB_NAME="${DB_NAME:-otel}"
OUT_DIR="${OUT_DIR:-.}"
TS="${TS:-$(date -u +%Y%m%d-%H%M%S)}"
SCHEMA_FILE="${SCHEMA_FILE:-$OUT_DIR/postgresql-schema-$TS.sql}"

command -v kubectl >/dev/null 2>&1 || { echo "[ERROR] Missing kubectl" >&2; exit 1; }

echo "[INFO] Exporting schema-only dump from $NAMESPACE/$SOURCE_DEPLOY database $DB_NAME..."
kubectl -n "$NAMESPACE" exec "deploy/$SOURCE_DEPLOY" -- \
  pg_dump -U "$SOURCE_DB_USER" -d "$DB_NAME" --schema-only --no-owner --no-privileges > "$SCHEMA_FILE"

echo "[INFO] Schema file: $SCHEMA_FILE"
if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$SCHEMA_FILE"
elif command -v shasum >/dev/null 2>&1; then
  shasum -a 256 "$SCHEMA_FILE"
else
  echo "[WARN] No sha256 tool found; calculate file hash manually for evidence."
fi

echo "[INFO] Runtime table list from source:"
kubectl -n "$NAMESPACE" exec "deploy/$SOURCE_DEPLOY" -- \
  psql -U "$SOURCE_DB_USER" -d "$DB_NAME" -c \
  "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema') ORDER BY table_schema, table_name;"

echo "[OK] Schema export completed."
