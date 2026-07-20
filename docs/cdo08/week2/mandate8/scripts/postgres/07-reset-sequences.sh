#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-techx-tf4}"
DB_NAME="${DB_NAME:-otel}"
RDS_HOST="${RDS_HOST:-techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com}"
RDS_PORT="${RDS_PORT:-5432}"
TARGET_SECRET_NAME="${TARGET_SECRET_NAME:-rds-admin-temp}"
TARGET_SECRET_USER_KEY="${TARGET_SECRET_USER_KEY:-username}"
TARGET_SECRET_PASSWORD_KEY="${TARGET_SECRET_PASSWORD_KEY:-password}"
CONFIRM_RESET_SEQUENCES="${CONFIRM_RESET_SEQUENCES:-}"
POD_NAME="rds-sequence-reset-$$"

if [[ "$CONFIRM_RESET_SEQUENCES" != "YES" ]]; then
  echo "[ERROR] This updates RDS sequence values. Re-run with CONFIRM_RESET_SEQUENCES=YES." >&2
  exit 1
fi

cleanup() {
  kubectl -n "$NAMESPACE" delete pod "$POD_NAME" --ignore-not-found >/dev/null 2>&1 || true
}
trap cleanup EXIT

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

echo "[INFO] Sequence before reset:"
kubectl -n "$NAMESPACE" exec "pod/$POD_NAME" -- \
  psql -c "SELECT (SELECT MAX(id) FROM reviews.productreviews) AS max_productreview_id, last_value, is_called FROM reviews.productreviews_id_seq;"

echo "[INFO] Resetting reviews.productreviews_id_seq to MAX(id)..."
kubectl -n "$NAMESPACE" exec "pod/$POD_NAME" -- \
  psql -v ON_ERROR_STOP=1 -c \
  "SELECT setval(pg_get_serial_sequence('reviews.productreviews','id'), COALESCE((SELECT MAX(id) FROM reviews.productreviews), 1), true);"

echo "[INFO] Sequence after reset:"
kubectl -n "$NAMESPACE" exec "pod/$POD_NAME" -- \
  psql -c "SELECT (SELECT MAX(id) FROM reviews.productreviews) AS max_productreview_id, last_value, is_called FROM reviews.productreviews_id_seq;"

echo "[OK] Sequence reset completed."
