#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_PROFILE="${AWS_PROFILE:-}"
EXPECTED_AWS_ACCOUNT_ID="${EXPECTED_AWS_ACCOUNT_ID:-}"
EXPECTED_KUBE_CONTEXT="${EXPECTED_KUBE_CONTEXT:-}"
SOURCE_DB_IDENTIFIER="${SOURCE_DB_IDENTIFIER:-techx-tf4-postgresql}"
DB_SUBNET_GROUP_NAME="${DB_SUBNET_GROUP_NAME:-techx-tf4-postgresql-private}"
RESTORE_DRILL_ID="${RESTORE_DRILL_ID:-}"
RESTORE_TIMESTAMP="${RESTORE_TIMESTAMP:-}"
RESTORE_TARGET_IDENTIFIER="${RESTORE_TARGET_IDENTIFIER:-}"
RESTORE_SECURITY_GROUP_ID="${RESTORE_SECURITY_GROUP_ID:-}"
VALIDATION_CLIENT_SECURITY_GROUP_ID="${VALIDATION_CLIENT_SECURITY_GROUP_ID:-}"
ACCOUNTING_TARGET_HOST="${ACCOUNTING_TARGET_HOST:-}"
ACCOUNTING_TARGET_DB="${ACCOUNTING_TARGET_DB:-otel}"
ACCOUNTING_TARGET_USER="${ACCOUNTING_TARGET_USER:-otelu}"
SOURCE_DB_NAME="${SOURCE_DB_NAME:-otel}"
SOURCE_DB_USER="${SOURCE_DB_USER:-otelu}"
PGSSLMODE="${PGSSLMODE:-require}"
NAMESPACE="${NAMESPACE:-techx-tf4}"
VALIDATION_CLIENT_SELECTOR="${VALIDATION_CLIENT_SELECTOR:-restore-validation-client=true}"
PREFLIGHT_ONLY="${PREFLIGHT_ONLY:-false}"
CONFIRM_PITR_RESTORE="${CONFIRM_PITR_RESTORE:-}"
CONFIRM_ACCOUNTING_IMPORT="${CONFIRM_ACCOUNTING_IMPORT:-}"
WAIT_TIMEOUT_SECONDS="${WAIT_TIMEOUT_SECONDS:-3600}"
NETWORK_WAIT_TIMEOUT_SECONDS="${NETWORK_WAIT_TIMEOUT_SECONDS:-300}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-30}"
TTL_HOURS="${TTL_HOURS:-24}"
export AWS_PAGER="${AWS_PAGER:-}"

PHASE="initialization"
RTO_START=0
RESTORE_ENDPOINT=""
REMOTE_DUMP="/tmp/rel25-accounting-${RESTORE_DRILL_ID:-unset}.dump"

now() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { printf '%s level=%s phase=%s message=%s\n' "$(now)" "$1" "$PHASE" "$2"; }
fail() { log ERROR "$1" >&2; exit 1; }
need() { [[ -n "${!1:-}" ]] || fail "Set $1 before running."; }
phase() { PHASE="$1"; PHASE_START="$(date +%s)"; log INFO phase_start; }
phase_done() { log INFO "phase_end duration_seconds=$(( $(date +%s) - PHASE_START ))"; }

# Invoked indirectly by the EXIT trap.
# shellcheck disable=SC2329
on_exit() {
  local code=$?
  if [[ -n "${VALIDATION_POD:-}" ]]; then
    kubectl -n "$NAMESPACE" exec "pod/$VALIDATION_POD" -- \
      rm -f "$REMOTE_DUMP" >/dev/null 2>&1 || true
  fi
  if ((code != 0)); then
    local elapsed=0
    ((RTO_START > 0)) && elapsed=$(( $(date +%s) - RTO_START ))
    log ERROR "restore_failed exit_code=$code rto_elapsed_seconds=$elapsed"
  fi
}
trap on_exit EXIT

aws_cli() { aws --region "$AWS_REGION" --profile "$AWS_PROFILE" "$@"; }

wait_for_rds() {
  local deadline=$(( $(date +%s) + WAIT_TIMEOUT_SECONDS ))
  local status
  while (( $(date +%s) < deadline )); do
    status="$(aws_cli rds describe-db-instances \
      --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" \
      --query 'DBInstances[0].DBInstanceStatus' --output text)"
    log INFO "target_status=$status"
    [[ "$status" == available ]] && return
    [[ "$status" == failed || "$status" == incompatible-restore ]] && \
      fail "Restore target entered terminal status $status."
    sleep "$POLL_INTERVAL_SECONDS"
  done
  fail "Timed out waiting for restore target."
}

wait_for_network() {
  local endpoint="$1"
  local target_name="$2"
  local deadline=$(( $(date +%s) + NETWORK_WAIT_TIMEOUT_SECONDS ))
  while (( $(date +%s) < deadline )); do
    if kubectl -n "$NAMESPACE" exec "pod/$VALIDATION_POD" -- \
      pg_isready -h "$endpoint" -p 5432 -t 10 >/dev/null 2>&1; then
      log INFO "network_probe_passed target=$target_name"
      return
    fi
    log INFO "network_probe_pending target=$target_name"
    sleep "$POLL_INTERVAL_SECONDS"
  done
  fail "Validation client could not reach $target_name."
}

for command in aws date kubectl; do
  command -v "$command" >/dev/null 2>&1 || fail "Missing command $command."
done
for variable in AWS_PROFILE EXPECTED_AWS_ACCOUNT_ID EXPECTED_KUBE_CONTEXT \
  RESTORE_DRILL_ID RESTORE_TIMESTAMP \
  RESTORE_TARGET_IDENTIFIER RESTORE_SECURITY_GROUP_ID \
  VALIDATION_CLIENT_SECURITY_GROUP_ID ACCOUNTING_TARGET_HOST; do
  need "$variable"
done

for number in WAIT_TIMEOUT_SECONDS NETWORK_WAIT_TIMEOUT_SECONDS \
  POLL_INTERVAL_SECONDS TTL_HOURS; do
  [[ "${!number}" =~ ^[1-9][0-9]*$ ]] || fail "$number must be a positive integer."
done
[[ "$PREFLIGHT_ONLY" == true || "$PREFLIGHT_ONLY" == false ]] || \
  fail "PREFLIGHT_ONLY must be true or false."
[[ "$RESTORE_DRILL_ID" =~ ^[a-z0-9][a-z0-9-]{2,40}$ ]] || \
  fail "Invalid RESTORE_DRILL_ID."
[[ "$RESTORE_TARGET_IDENTIFIER" =~ ^[a-z][a-z0-9-]{0,62}$ ]] || \
  fail "Target identifier violates RDS naming rules."
[[ "$RESTORE_TARGET_IDENTIFIER" != *"--"* ]] || fail "Target identifier contains consecutive hyphens."
[[ "$RESTORE_TARGET_IDENTIFIER" == "techx-tf4-drill-${RESTORE_DRILL_ID}-"*accounting*restore* ]] || \
  fail "Target identifier must use the drill prefix and contain accounting and restore."
[[ "$RESTORE_TARGET_IDENTIFIER" != "$SOURCE_DB_IDENTIFIER" ]] || fail "Target equals source."
[[ "$ACCOUNTING_TARGET_HOST" != *"prod"* && "$ACCOUNTING_TARGET_HOST" != *"production"* ]] || \
  fail "ACCOUNTING_TARGET_HOST must not contain prod/production."
for sg in "$RESTORE_SECURITY_GROUP_ID" "$VALIDATION_CLIENT_SECURITY_GROUP_ID"; do
  [[ "$sg" =~ ^sg-([0-9a-f]{8}|[0-9a-f]{17})$ ]] || fail "Invalid security group ID $sg."
done
[[ "$RESTORE_SECURITY_GROUP_ID" != "$VALIDATION_CLIENT_SECURITY_GROUP_ID" ]] || \
  fail "Restore and validation client must use different security groups."

restore_epoch="$(date -u -d "$RESTORE_TIMESTAMP" +%s 2>/dev/null)" || fail "Invalid RESTORE_TIMESTAMP."
restore_time="$(date -u -d "@$restore_epoch" +"%Y-%m-%dT%H:%M:%SZ")"

phase environment_preflight
account_id="$(aws --profile "$AWS_PROFILE" sts get-caller-identity --query Account --output text)"
[[ "$account_id" == "$EXPECTED_AWS_ACCOUNT_ID" ]] || fail "AWS account does not match EXPECTED_AWS_ACCOUNT_ID."
context="$(kubectl config current-context)"
[[ "$context" == "$EXPECTED_KUBE_CONTEXT" ]] || fail "Kubernetes context does not match EXPECTED_KUBE_CONTEXT."

mapfile -t pods < <(kubectl -n "$NAMESPACE" get pods -l "$VALIDATION_CLIENT_SELECTOR" \
  --field-selector=status.phase=Running -o name)
[[ "${#pods[@]}" -eq 1 ]] || fail "Expected one running validation pod; found ${#pods[@]}."
VALIDATION_POD="${pods[0]#pod/}"
pod_ip="$(kubectl -n "$NAMESPACE" get "pod/$VALIDATION_POD" -o jsonpath='{.status.podIP}')"
[[ -n "$pod_ip" ]] || fail "Validation pod has no IP."
kubectl -n "$NAMESPACE" exec "pod/$VALIDATION_POD" -- \
  sh -c 'command -v pg_isready >/dev/null' || fail "Validation pod lacks pg_isready."
kubectl -n "$NAMESPACE" exec "pod/$VALIDATION_POD" -- \
  sh -c 'command -v pg_dump >/dev/null && command -v pg_restore >/dev/null && command -v psql >/dev/null' || \
  fail "Validation pod must contain pg_dump, pg_restore, and psql."

read -r source_status instance_class source_vpc source_endpoint <<<"$(aws_cli rds describe-db-instances \
  --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --query 'DBInstances[0].[DBInstanceStatus,DBInstanceClass,DBSubnetGroup.VpcId,Endpoint.Address]' \
  --output text)"
[[ "$source_status" == available ]] || fail "Source status is $source_status."
[[ "$ACCOUNTING_TARGET_HOST" != "$source_endpoint" ]] || fail "Accounting target equals production source endpoint."
production_sgs="$(aws_cli rds describe-db-instances \
  --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --query 'DBInstances[0].VpcSecurityGroups[*].VpcSecurityGroupId' --output text)"
[[ " $production_sgs " != *" $RESTORE_SECURITY_GROUP_ID "* ]] || fail "Restore SG equals a production SG."

subnet_vpc="$(aws_cli rds describe-db-subnet-groups \
  --db-subnet-group-name "$DB_SUBNET_GROUP_NAME" \
  --query 'DBSubnetGroups[0].VpcId' --output text)"
[[ "$subnet_vpc" == "$source_vpc" ]] || fail "Subnet group is in the wrong VPC."

read -r validation_vpc validation_environment validation_production \
  validation_drill validation_purpose <<<"$(aws_cli ec2 describe-security-groups \
  --group-ids "$VALIDATION_CLIENT_SECURITY_GROUP_ID" \
  --query "SecurityGroups[0].[VpcId,Tags[?Key=='Environment'].Value|[0],Tags[?Key=='Production'].Value|[0],Tags[?Key=='RestoreDrillId'].Value|[0],Tags[?Key=='Purpose'].Value|[0]]" \
  --output text)"
[[ "$validation_vpc" == "$source_vpc" &&
   "$validation_environment" == RestoreDrill &&
   "$validation_production" == false &&
   "$validation_drill" == "$RESTORE_DRILL_ID" &&
   "$validation_purpose" == RestoreValidationClient ]] || \
  fail "Validation client SG metadata does not match the drill contract."

pod_sgs="$(aws_cli ec2 describe-network-interfaces \
  --filters "Name=addresses.private-ip-address,Values=$pod_ip" \
  --query 'NetworkInterfaces[0].Groups[*].GroupId' --output text)"
[[ " $pod_sgs " == *" $VALIDATION_CLIENT_SECURITY_GROUP_ID "* ]] || \
  fail "Validation pod ENI does not use the validation client SG."
phase_done

phase accounting_target_preflight
wait_for_network "$ACCOUNTING_TARGET_HOST" accounting_drill_target
kubectl -n "$NAMESPACE" exec "pod/$VALIDATION_POD" -- \
  psql "host=$ACCOUNTING_TARGET_HOST port=5432 dbname=$ACCOUNTING_TARGET_DB user=$ACCOUNTING_TARGET_USER sslmode=$PGSSLMODE" \
    -v ON_ERROR_STOP=1 -At -c 'select 1' >/dev/null || \
  fail "Validation client cannot authenticate to the accounting drill target."
log INFO "accounting_drill_target_authentication_passed"
phase_done

phase restore_preflight
# JMESPath literals require backticks, so this query must stay single-quoted.
# shellcheck disable=SC2016
read -r restore_vpc restore_environment restore_production restore_drill \
  restore_purpose unsafe_rules invalid_ports validation_rules unexpected_sources \
  <<<"$(aws_cli ec2 describe-security-groups --group-ids "$RESTORE_SECURITY_GROUP_ID" \
  --query 'SecurityGroups[0].[VpcId,Tags[?Key==`Environment`].Value|[0],Tags[?Key==`Production`].Value|[0],Tags[?Key==`RestoreDrillId`].Value|[0],Tags[?Key==`Purpose`].Value|[0],length(IpPermissions[?length(IpRanges) > `0` || length(Ipv6Ranges) > `0` || length(PrefixListIds) > `0`]),length(IpPermissions[?IpProtocol != `tcp` || FromPort != `5432` || ToPort != `5432`]),length(IpPermissions[].UserIdGroupPairs[?GroupId == `'"$VALIDATION_CLIENT_SECURITY_GROUP_ID"'`][]),length(IpPermissions[].UserIdGroupPairs[?GroupId != `'"$VALIDATION_CLIENT_SECURITY_GROUP_ID"'`][]) ]' \
  --output text)"
[[ "$restore_vpc" == "$source_vpc" &&
   "$restore_environment" == RestoreDrill &&
   "$restore_production" == false &&
   "$restore_drill" == "$RESTORE_DRILL_ID" &&
   "$restore_purpose" == RestoreTarget &&
   "$unsafe_rules" == 0 &&
   "$invalid_ports" == 0 &&
   "$validation_rules" -ge 1 &&
   "$unexpected_sources" == 0 ]] || fail "Restore SG does not satisfy the isolation contract."

read -r earliest latest <<<"$(aws_cli rds describe-db-instance-automated-backups \
  --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --query 'DBInstanceAutomatedBackups[0].RestoreWindow.[EarliestTime,LatestTime]' --output text)"
earliest_epoch="$(date -u -d "$earliest" +%s)"
latest_epoch="$(date -u -d "$latest" +%s)"
((restore_epoch >= earliest_epoch && restore_epoch <= latest_epoch)) || \
  fail "Restore timestamp is outside $earliest to $latest."

target_error=""
if target_error="$(aws_cli rds describe-db-instances \
  --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" 2>&1)"; then
  fail "Restore target already exists."
fi
[[ "$target_error" == *DBInstanceNotFound* ]] || fail "Could not verify target absence: $target_error"

log INFO "source=$SOURCE_DB_IDENTIFIER target=$RESTORE_TARGET_IDENTIFIER restore_time=$restore_time"
phase_done
if [[ "$PREFLIGHT_ONLY" == true ]]; then
  PHASE=complete
  log INFO "preflight_only_passed no_rds_instance_created"
  exit 0
fi
[[ "$CONFIRM_PITR_RESTORE" == YES ]] || fail "Set CONFIRM_PITR_RESTORE=YES."
[[ "$CONFIRM_ACCOUNTING_IMPORT" == YES ]] || fail "Set CONFIRM_ACCOUNTING_IMPORT=YES."

cleanup_after="$(date -u -d "+${TTL_HOURS} hours" +"%Y-%m-%dT%H:%M:%SZ")"
RTO_START="$(date +%s)"
log INFO "rto_start restore_time=$restore_time"

phase restore_request
aws_cli rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --target-db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" \
  --restore-time "$restore_time" \
  --db-instance-class "$instance_class" \
  --db-subnet-group-name "$DB_SUBNET_GROUP_NAME" \
  --vpc-security-group-ids "$RESTORE_SECURITY_GROUP_ID" \
  --no-publicly-accessible --no-multi-az --copy-tags-to-snapshot \
  --tags Key=Owner,Value=CDO08 Key=Environment,Value=RestoreDrill \
    Key=Mandate,Value=20 Key=Task,Value=CDO08-REL-25 \
    Key=RestoreDrillId,Value="$RESTORE_DRILL_ID" Key=TTLHours,Value="$TTL_HOURS" \
    Key=CleanupAfter,Value="$cleanup_after" Key=CostCenter,Value=ReliabilityDrill \
    Key=Purpose,Value=AccountingPITR Key=Production,Value=false \
  --query 'DBInstance.[DBInstanceIdentifier,DBInstanceStatus]' --output text
phase_done

phase wait_initial_available
wait_for_rds
phase_done

phase apply_network_access
aws_cli rds modify-db-instance --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" \
  --vpc-security-group-ids "$RESTORE_SECURITY_GROUP_ID" --apply-immediately \
  --query 'DBInstance.[DBInstanceIdentifier,DBInstanceStatus]' --output text
phase_done

phase wait_network_available
wait_for_rds
phase_done

phase verify_target
read -r target_status endpoint target_public target_subnet target_sg <<<"$(aws_cli rds describe-db-instances \
  --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" \
  --query 'DBInstances[0].[DBInstanceStatus,Endpoint.Address,PubliclyAccessible,DBSubnetGroup.DBSubnetGroupName,VpcSecurityGroups[0].VpcSecurityGroupId]' \
  --output text)"
[[ "$target_status" == available &&
   "$target_public" == False &&
   "$target_subnet" == "$DB_SUBNET_GROUP_NAME" &&
   "$target_sg" == "$RESTORE_SECURITY_GROUP_ID" ]] || fail "Restored target metadata is unsafe."
log INFO "target_status=$target_status public=$target_public network_configuration_verified=true"
RESTORE_ENDPOINT="$endpoint"
[[ "$ACCOUNTING_TARGET_HOST" != "$RESTORE_ENDPOINT" ]] || fail "Accounting import target equals PITR staging endpoint."
phase_done

phase validate_network_access
wait_for_network "$endpoint" pitr_staging
wait_for_network "$ACCOUNTING_TARGET_HOST" accounting_drill_target
phase_done

phase export_accounting_schema
kubectl -n "$NAMESPACE" exec "pod/$VALIDATION_POD" -- \
  pg_dump "host=$RESTORE_ENDPOINT port=5432 dbname=$SOURCE_DB_NAME user=$SOURCE_DB_USER sslmode=$PGSSLMODE" \
    --format=custom --no-owner --no-privileges --schema=accounting --file="$REMOTE_DUMP"
kubectl -n "$NAMESPACE" exec "pod/$VALIDATION_POD" -- test -s "$REMOTE_DUMP" || \
  fail "Accounting schema dump was not created."
phase_done

phase prepare_accounting_target
kubectl -n "$NAMESPACE" exec "pod/$VALIDATION_POD" -- \
  psql "host=$ACCOUNTING_TARGET_HOST port=5432 dbname=$ACCOUNTING_TARGET_DB user=$ACCOUNTING_TARGET_USER sslmode=$PGSSLMODE" \
    -v ON_ERROR_STOP=1 -c 'drop schema if exists accounting cascade; create schema accounting;'
phase_done

phase import_accounting_schema
kubectl -n "$NAMESPACE" exec "pod/$VALIDATION_POD" -- \
  pg_restore "host=$ACCOUNTING_TARGET_HOST port=5432 dbname=$ACCOUNTING_TARGET_DB user=$ACCOUNTING_TARGET_USER sslmode=$PGSSLMODE" \
    --no-owner --no-privileges --schema=accounting --exit-on-error "$REMOTE_DUMP"
phase_done

phase validate_accounting_integrity
read -r order_count shipping_orphans item_orphans unexpected_schemas <<<"$(kubectl -n "$NAMESPACE" exec "pod/$VALIDATION_POD" -- \
  psql "host=$ACCOUNTING_TARGET_HOST port=5432 dbname=$ACCOUNTING_TARGET_DB user=$ACCOUNTING_TARGET_USER sslmode=$PGSSLMODE" \
    -v ON_ERROR_STOP=1 -At -F ' ' -c \
    "select
       (select count(*) from accounting.\"order\"),
       (select count(*) from accounting.shipping s left join accounting.\"order\" o on o.order_id = s.order_id where o.order_id is null),
       (select count(*) from accounting.orderitem i left join accounting.\"order\" o on o.order_id = i.order_id where o.order_id is null),
       (select count(*) from information_schema.schemata where schema_name in ('catalog','reviews'));" \
)"
[[ "$shipping_orphans" == 0 && "$item_orphans" == 0 && "$unexpected_schemas" == 0 ]] || \
  fail "Accounting validation failed order_count=$order_count shipping_orphans=$shipping_orphans item_orphans=$item_orphans unexpected_schemas=$unexpected_schemas."
log INFO "order_count=$order_count shipping_orphans=$shipping_orphans item_orphans=$item_orphans unexpected_schemas=$unexpected_schemas"
phase_done

phase cleanup_temporary_artifacts
kubectl -n "$NAMESPACE" exec "pod/$VALIDATION_POD" -- rm -f "$REMOTE_DUMP"
phase_done

PHASE=complete
log INFO "rto_end rto_seconds=$(( $(date +%s) - RTO_START ))"
log INFO "accounting_schema_recovery_completed production_source_was_not_modified"
exit 0
