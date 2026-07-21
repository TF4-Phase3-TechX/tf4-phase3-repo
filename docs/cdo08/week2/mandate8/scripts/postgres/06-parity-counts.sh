#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-techx-tf4}"
SOURCE_DEPLOY="${SOURCE_DEPLOY:-postgresql}"
SOURCE_DB_USER="${SOURCE_DB_USER:-root}"
DB_NAME="${DB_NAME:-otel}"
RDS_HOST="${RDS_HOST:-techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com}"
RDS_PORT="${RDS_PORT:-5432}"
TARGET_SECRET_NAME="${TARGET_SECRET_NAME:-rds-admin-temp}"
TARGET_SECRET_USER_KEY="${TARGET_SECRET_USER_KEY:-username}"
TARGET_SECRET_PASSWORD_KEY="${TARGET_SECRET_PASSWORD_KEY:-password}"
SOURCE_FROZEN="${SOURCE_FROZEN:-false}"
POD_NAME="rds-parity-check-$$"

TABLES=(
  'accounting."order"'
  'accounting.orderitem'
  'accounting.shipping'
  'catalog.products'
  'reviews.productreviews'
)

cleanup() {
  kubectl -n "$NAMESPACE" delete pod "$POD_NAME" --ignore-not-found >/dev/null 2>&1 || true
}
trap cleanup EXIT

source_count() {
  kubectl -n "$NAMESPACE" exec "deploy/$SOURCE_DEPLOY" -- \
    psql -U "$SOURCE_DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -At -c "SELECT COUNT(*) FROM $1;"
}

echo "[INFO] Creating temporary target psql pod using secret metadata only: $TARGET_SECRET_NAME"
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

target_count() {
  kubectl -n "$NAMESPACE" exec "pod/$POD_NAME" -- \
    psql -v ON_ERROR_STOP=1 -At -c "SELECT COUNT(*) FROM $1;"
}

if [[ "$SOURCE_FROZEN" != "true" ]]; then
  echo "[WARN] SOURCE_FROZEN is not true. This is a live sanity check, not final cutover parity."
  echo "[WARN] Dynamic tables can differ while source writes and DMS CDC are still active."
fi

printf "%-30s %12s %12s %8s\n" "table" "source" "target" "status"
failed=0
for table in "${TABLES[@]}"; do
  src="$(source_count "$table" | tr -d '\r')"
  tgt="$(target_count "$table" | tr -d '\r')"
  status="PASS"
  if [[ "$src" != "$tgt" ]]; then
    if [[ "$SOURCE_FROZEN" == "true" ]]; then
      status="FAIL"
    else
      status="DIFF"
    fi
    failed=1
  fi
  printf "%-30s %12s %12s %8s\n" "$table" "$src" "$tgt" "$status"
done

echo "[INFO] reviews.productreviews sequence on target:"
kubectl -n "$NAMESPACE" exec "pod/$POD_NAME" -- \
  psql -c "SELECT (SELECT MAX(id) FROM reviews.productreviews) AS max_productreview_id, last_value, is_called FROM reviews.productreviews_id_seq;"

if [[ "$failed" -ne 0 && "$SOURCE_FROZEN" == "true" ]]; then
  echo "[ERROR] Row count parity failed." >&2
  exit 1
fi

if [[ "$failed" -ne 0 ]]; then
  echo "[WARN] Live sanity check found count differences. Re-run with SOURCE_FROZEN=true only after writer freeze and CDC catch-up."
else
  echo "[OK] Row count parity passed."
fi
