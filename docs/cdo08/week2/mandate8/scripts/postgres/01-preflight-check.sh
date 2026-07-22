#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_PROFILE="${AWS_PROFILE:-tf4}"
export AWS_PAGER="${AWS_PAGER:-}"
NAMESPACE="${NAMESPACE:-techx-tf4}"
SOURCE_DEPLOY="${SOURCE_DEPLOY:-postgresql}"
SOURCE_DB_USER="${SOURCE_DB_USER:-root}"
DB_NAME="${DB_NAME:-otel}"
RDS_HOST="${RDS_HOST:-techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com}"
DMS_REPLICATION_INSTANCE_ARN="${DMS_REPLICATION_INSTANCE_ARN:-arn:aws:dms:us-east-1:511825856493:rep:JPOXJ6J6NVEEVK6IDAJGAE23HY}"
DMS_TASK_ID="${DMS_TASK_ID:-techx-tf4-postgresql-forward}"
ENABLE_SLOT_PROBE="${ENABLE_SLOT_PROBE:-false}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "[ERROR] Missing required command: $1" >&2
    exit 1
  }
}

psql_source() {
  kubectl -n "$NAMESPACE" exec "deploy/$SOURCE_DEPLOY" -- \
    psql -U "$SOURCE_DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -At -c "$1"
}

require_cmd aws
require_cmd kubectl

echo "[INFO] Checking source PostgreSQL rollout..."
kubectl -n "$NAMESPACE" rollout status "deploy/$SOURCE_DEPLOY" --timeout=180s

echo "[INFO] Checking source service/PVC/pod inventory..."
kubectl -n "$NAMESPACE" get deploy,svc,pvc,pod -l opentelemetry.io/name=postgresql -o wide

echo "[INFO] Checking migration bridge service..."
kubectl -n "$NAMESPACE" get svc postgresql-migration-bridge -o wide

echo "[INFO] Checking source PostgreSQL logical settings..."
wal_level="$(psql_source "SHOW wal_level;")"
max_slots="$(psql_source "SHOW max_replication_slots;")"
max_senders="$(psql_source "SHOW max_wal_senders;")"
echo "wal_level=$wal_level"
echo "max_replication_slots=$max_slots"
echo "max_wal_senders=$max_senders"

if [[ "$wal_level" != "logical" ]]; then
  echo "[ERROR] wal_level must be logical before DMS CDC." >&2
  exit 1
fi

echo "[INFO] Checking source roles metadata only..."
kubectl -n "$NAMESPACE" exec "deploy/$SOURCE_DEPLOY" -- \
  psql -U "$SOURCE_DB_USER" -d "$DB_NAME" -c \
  "SELECT rolname, rolreplication, rolcanlogin FROM pg_roles WHERE rolname IN ('root','dms_user','techx_app') ORDER BY rolname;"

if [[ "$ENABLE_SLOT_PROBE" == "true" ]]; then
  slot_name="dms_probe_test_decoding_$(date +%s)"
  echo "[INFO] Probing test_decoding logical replication slot: $slot_name"
  cleanup_slot() {
    kubectl -n "$NAMESPACE" exec "deploy/$SOURCE_DEPLOY" -- \
      psql -U "$SOURCE_DB_USER" -d "$DB_NAME" -c \
      "SELECT pg_drop_replication_slot('$slot_name') WHERE EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name = '$slot_name');" >/dev/null || true
  }
  trap cleanup_slot EXIT
  kubectl -n "$NAMESPACE" exec "deploy/$SOURCE_DEPLOY" -- \
    psql -U "$SOURCE_DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -c \
    "SELECT * FROM pg_create_logical_replication_slot('$slot_name','test_decoding');"
else
  echo "[INFO] Slot probe skipped. Set ENABLE_SLOT_PROBE=true to run the temporary test_decoding probe."
fi

echo "[INFO] Checking RDS private endpoint reachability from source pod..."
kubectl -n "$NAMESPACE" exec "deploy/$SOURCE_DEPLOY" -- \
  pg_isready -h "$RDS_HOST" -p 5432 -d "$DB_NAME"

echo "[INFO] Checking DMS task metadata..."
aws dms describe-replication-tasks \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --filters "Name=replication-task-id,Values=$DMS_TASK_ID" \
  --query 'ReplicationTasks[0].{Id:ReplicationTaskIdentifier,Status:Status,MigrationType:MigrationType,StopReason:StopReason}'

echo "[INFO] Checking DMS connection status..."
aws dms describe-connections \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --filters "Name=replication-instance-arn,Values=$DMS_REPLICATION_INSTANCE_ARN" \
  --query 'Connections[*].{Endpoint:EndpointIdentifier,Status:Status,LastFailureMessage:LastFailureMessage}'

echo "[OK] Preflight checks completed."
