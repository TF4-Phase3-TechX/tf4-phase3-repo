#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-techx-tf4}"
DEPLOYMENT="${DEPLOYMENT:-postgresql}"
SOURCE_DB="${SOURCE_DB:-otel}"
DB_USER="${DB_USER:-root}"
RESTORE_DB="${RESTORE_DB:-rel03_restore_verify}"
BACKUP_DIR="${BACKUP_DIR:-artifacts/rel-03a-postgresql}"
TIMESTAMP="${TIMESTAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
BACKUP_FILE="${BACKUP_FILE:-${BACKUP_DIR}/${SOURCE_DB}-${TIMESTAMP}.sql}"
EXPECTED_CONTEXT_PATTERN="${EXPECTED_CONTEXT_PATTERN:-techx-tf4-cluster}"

usage() {
  cat <<'EOF'
Usage:
  postgresql-backup-restore-proof.sh backup
  BACKUP_FILE=<path> postgresql-backup-restore-proof.sh verify
  postgresql-backup-restore-proof.sh recreate-proof

The verify command restores into the temporary database rel03_restore_verify.
It never restores over the source database. The temporary database is removed
on success or failure.
EOF
}

require_tools() {
  command -v kubectl >/dev/null 2>&1 || { echo "kubectl is required" >&2; exit 1; }
  local current_context
  current_context="$(kubectl config current-context)"
  if [[ "$current_context" != *"$EXPECTED_CONTEXT_PATTERN"* ]]; then
    echo "Refusing to run: context '$current_context' does not match '$EXPECTED_CONTEXT_PATTERN'." >&2
    exit 1
  fi
  echo "Kubernetes context: $current_context"
  kubectl -n "$NAMESPACE" get deployment "$DEPLOYMENT" >/dev/null
  kubectl -n "$NAMESPACE" rollout status "deployment/$DEPLOYMENT" --timeout=120s
}

query() {
  local database="$1"
  local sql="$2"
  kubectl -n "$NAMESPACE" exec "deployment/$DEPLOYMENT" -- \
    psql -X -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$database" -Atc "$sql"
}

schema_signature() {
  local database="$1"
  query "$database" "
    SELECT n.nspname || ':' || count(c.oid)
    FROM pg_namespace n
    LEFT JOIN pg_class c
      ON c.relnamespace = n.oid AND c.relkind IN ('r','p')
    WHERE n.nspname IN ('accounting','catalog','reviews')
    GROUP BY n.nspname
    ORDER BY n.nspname;"
}

cleanup_restore_db() {
  query postgres "DROP DATABASE IF EXISTS \"${RESTORE_DB}\" WITH (FORCE);" >/dev/null || true
}

backup() {
  mkdir -p "$BACKUP_DIR"
  echo "Creating a plain-SQL backup from ${NAMESPACE}/${DEPLOYMENT}:${SOURCE_DB}"
  kubectl -n "$NAMESPACE" exec "deployment/$DEPLOYMENT" -- \
    pg_dump -U "$DB_USER" -d "$SOURCE_DB" --format=plain --no-owner --no-acl > "$BACKUP_FILE"
  test -s "$BACKUP_FILE"
  grep -q -- "-- PostgreSQL database dump" "$BACKUP_FILE"
  grep -q -- "-- PostgreSQL database dump complete" "$BACKUP_FILE"

  echo "Backup validated: $BACKUP_FILE"
  echo "Keep this artifact outside Git; database dumps may contain sensitive data."
}

verify_restore() {
  test -f "$BACKUP_FILE" || { echo "Backup not found: $BACKUP_FILE" >&2; exit 1; }
  trap cleanup_restore_db EXIT
  cleanup_restore_db

  query postgres "CREATE DATABASE \"${RESTORE_DB}\";" >/dev/null
  kubectl -n "$NAMESPACE" exec -i "deployment/$DEPLOYMENT" -- \
    psql -X -v ON_ERROR_STOP=1 --single-transaction -U "$DB_USER" -d "$RESTORE_DB" < "$BACKUP_FILE"

  local source_signature restore_signature
  source_signature="$(schema_signature "$SOURCE_DB")"
  restore_signature="$(schema_signature "$RESTORE_DB")"

  echo "Source schema signature:"
  printf '%s\n' "$source_signature"
  echo "Restored schema signature:"
  printf '%s\n' "$restore_signature"
  test -n "$source_signature"
  test "$source_signature" = "$restore_signature"

  echo "Restore proof passed in temporary database: $RESTORE_DB"
}

recreate_proof() {
  local before_uid after_uid source_signature restore_signature
  if [[ "${CONFIRM_RECREATE:-}" != "${NAMESPACE}/${DEPLOYMENT}" ]]; then
    echo "Pod recreation causes downtime." >&2
    echo "Rerun with CONFIRM_RECREATE=${NAMESPACE}/${DEPLOYMENT}" >&2
    exit 1
  fi
  before_uid="$(kubectl -n "$NAMESPACE" get pod -l app.kubernetes.io/component=postgresql -o jsonpath='{.items[0].metadata.uid}')"
  source_signature="$(schema_signature "$SOURCE_DB")"

  kubectl -n "$NAMESPACE" delete pod -l app.kubernetes.io/component=postgresql --wait=true
  kubectl -n "$NAMESPACE" rollout status "deployment/$DEPLOYMENT" --timeout=300s

  after_uid="$(kubectl -n "$NAMESPACE" get pod -l app.kubernetes.io/component=postgresql -o jsonpath='{.items[0].metadata.uid}')"
  restore_signature="$(schema_signature "$SOURCE_DB")"

  test "$before_uid" != "$after_uid"
  test "$source_signature" = "$restore_signature"
  echo "Old pod UID: $before_uid"
  echo "New pod UID: $after_uid"
  echo "Persisted schema signature:"
  printf '%s\n' "$restore_signature"
  echo "Pod recreation proof passed: UID changed and schema signature persisted."
}

require_tools
case "${1:-}" in
  backup) backup ;;
  verify) verify_restore ;;
  recreate-proof) recreate_proof ;;
  *) usage; exit 2 ;;
esac
