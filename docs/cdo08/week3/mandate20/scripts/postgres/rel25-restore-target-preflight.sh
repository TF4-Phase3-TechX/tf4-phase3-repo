#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_PROFILE="${AWS_PROFILE:-}"
export AWS_PAGER="${AWS_PAGER:-}"

RESTORE_DRILL_ID="${RESTORE_DRILL_ID:-}"
RESTORE_TARGET_IDENTIFIER="${RESTORE_TARGET_IDENTIFIER:-}"
RESTORE_TARGET_ENDPOINT="${RESTORE_TARGET_ENDPOINT:-}"
RESTORE_TARGET_DNS_NAME="${RESTORE_TARGET_DNS_NAME:-}"
RESTORE_TARGET_PREFIX="${RESTORE_TARGET_PREFIX:-techx-tf4-drill-}"
PRODUCTION_RDS_IDENTIFIER="techx-tf4-postgresql"
NAMESPACE="${NAMESPACE:-techx-tf4}"
VALIDATION_CLIENT_SELECTOR="${VALIDATION_CLIENT_SELECTOR:-restore-validation-client=true}"

fail() {
  echo "[ERROR] $1" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

require_non_empty() {
  [[ -n "${!1:-}" ]] || fail "Set $1 before running restore target preflight."
}

require_cmd aws
require_cmd kubectl

require_non_empty AWS_PROFILE
require_non_empty RESTORE_DRILL_ID
require_non_empty RESTORE_TARGET_IDENTIFIER
require_non_empty RESTORE_TARGET_ENDPOINT

[[ "$RESTORE_DRILL_ID" =~ ^[a-z0-9][a-z0-9-]{2,40}$ ]] || \
  fail "RESTORE_DRILL_ID must be 3-41 lowercase letters/numbers/hyphens."

[[ "$RESTORE_TARGET_IDENTIFIER" != "$PRODUCTION_RDS_IDENTIFIER" ]] || \
  fail "Restore target identifier matches production identifier: $PRODUCTION_RDS_IDENTIFIER"

[[ "$RESTORE_TARGET_IDENTIFIER" == "${RESTORE_TARGET_PREFIX}${RESTORE_DRILL_ID}"* ]] || \
  fail "Restore target identifier must start with ${RESTORE_TARGET_PREFIX}${RESTORE_DRILL_ID}"

[[ "$RESTORE_TARGET_IDENTIFIER" == *"drill"* && "$RESTORE_TARGET_IDENTIFIER" == *"restore"* ]] || \
  fail "Restore target identifier must contain both drill and restore markers."

if [[ -n "$RESTORE_TARGET_DNS_NAME" ]]; then
  [[ "$RESTORE_TARGET_DNS_NAME" != *"prod"* && "$RESTORE_TARGET_DNS_NAME" != *"production"* ]] || \
    fail "Restore DNS name must not contain prod/production."
fi

echo "[INFO] Resolving production endpoint from AWS RDS..."
production_endpoint="$(aws rds describe-db-instances \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --db-instance-identifier "$PRODUCTION_RDS_IDENTIFIER" \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text)"

[[ -n "$production_endpoint" && "$production_endpoint" != "None" ]] || \
  fail "Could not resolve production RDS endpoint for $PRODUCTION_RDS_IDENTIFIER."

[[ "$RESTORE_TARGET_ENDPOINT" != "$production_endpoint" ]] || \
  fail "Restore target endpoint matches production endpoint: $production_endpoint"

echo "[INFO] Resolving restore target from AWS RDS..."
resolved_json="$(aws rds describe-db-instances \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" \
  --query 'DBInstances[0].{Identifier:DBInstanceIdentifier,Endpoint:Endpoint.Address,Public:PubliclyAccessible,DeletionProtection:DeletionProtection}' \
  --output json)"

resolved_endpoint="$(aws rds describe-db-instances \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text)"

publicly_accessible="$(aws rds describe-db-instances \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" \
  --query 'DBInstances[0].PubliclyAccessible' \
  --output text)"

[[ "$resolved_endpoint" == "$RESTORE_TARGET_ENDPOINT" ]] || \
  fail "RESTORE_TARGET_ENDPOINT ($RESTORE_TARGET_ENDPOINT) does not match AWS RDS endpoint ($resolved_endpoint)."

[[ "$resolved_endpoint" != "$production_endpoint" ]] || \
  fail "Resolved RDS endpoint is production endpoint."

[[ "$publicly_accessible" == "False" ]] || \
  fail "Restore target must be private. PubliclyAccessible=$publicly_accessible"

echo "[INFO] Restore RDS target metadata:"
echo "$resolved_json"

echo "[INFO] Checking validation client access path..."
kubectl -n "$NAMESPACE" get pod -l "$VALIDATION_CLIENT_SELECTOR" -o name | grep -q . || \
  fail "No validation client pod found with selector $VALIDATION_CLIENT_SELECTOR in namespace $NAMESPACE."

echo "[OK] Restore target preflight passed. Target is isolated from production identifiers/endpoints."
