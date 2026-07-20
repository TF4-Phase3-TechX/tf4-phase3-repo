#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-techx-tf4}"
DB_NAME="${DB_NAME:-otel}"
RDS_HOST="${RDS_HOST:-techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com}"
RDS_PORT="${RDS_PORT:-5432}"
TARGET_SECRET_NAME="${TARGET_SECRET_NAME:-rds-admin-temp}"
TARGET_SECRET_USER_KEY="${TARGET_SECRET_USER_KEY:-username}"
TARGET_SECRET_PASSWORD_KEY="${TARGET_SECRET_PASSWORD_KEY:-password}"
SCHEMA_FILE="${SCHEMA_FILE:-}"
CONFIRM_RESTORE_SCHEMA="${CONFIRM_RESTORE_SCHEMA:-}"
POD_NAME="rds-schema-restore-$$"

if [[ "$CONFIRM_RESTORE_SCHEMA" != "YES" ]]; then
  echo "[ERROR] This applies schema DDL to RDS. Re-run with CONFIRM_RESTORE_SCHEMA=YES." >&2
  exit 1
fi

if [[ -z "$SCHEMA_FILE" || ! -f "$SCHEMA_FILE" ]]; then
  echo "[ERROR] Set SCHEMA_FILE to an existing schema dump path." >&2
  exit 1
fi

cleanup() {
  kubectl -n "$NAMESPACE" delete pod "$POD_NAME" --ignore-not-found >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[INFO] Creating temporary psql pod. Credentials are read from Kubernetes Secret metadata only: $TARGET_SECRET_NAME"
cat <<YAML | kubectl -n "$NAMESPACE" apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: $POD_NAME
spec:
  restartPolicy: Never
  containers:
    - name: psql
      image: postgres:17.6
      command: ["sleep", "3600"]
      env:
        - name: PGHOST
          value: "$RDS_HOST"
        - name: PGPORT
          value: "$RDS_PORT"
        - name: PGDATABASE
          value: "$DB_NAME"
        - name: PGUSER
          valueFrom:
            secretKeyRef:
              name: $TARGET_SECRET_NAME
              key: $TARGET_SECRET_USER_KEY
        - name: PGPASSWORD
          valueFrom:
            secretKeyRef:
              name: $TARGET_SECRET_NAME
              key: $TARGET_SECRET_PASSWORD_KEY
      resources:
        requests:
          cpu: 50m
          memory: 128Mi
        limits:
          cpu: 250m
          memory: 256Mi
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
        runAsNonRoot: true
        runAsUser: 999
        runAsGroup: 999
        seccompProfile:
          type: RuntimeDefault
YAML

kubectl -n "$NAMESPACE" wait --for=condition=Ready "pod/$POD_NAME" --timeout=60s
kubectl -n "$NAMESPACE" cp "$SCHEMA_FILE" "$POD_NAME:/tmp/postgresql-schema.sql"

echo "[INFO] Applying schema to RDS..."
kubectl -n "$NAMESPACE" exec "pod/$POD_NAME" -- \
  psql -v ON_ERROR_STOP=1 -f /tmp/postgresql-schema.sql

echo "[INFO] RDS table list after schema restore:"
kubectl -n "$NAMESPACE" exec "pod/$POD_NAME" -- \
  psql -c "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema') ORDER BY table_schema, table_name;"

echo "[OK] Schema restore completed."
