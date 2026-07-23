#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_PROFILE="${AWS_PROFILE:-}"
SOURCE_DB_IDENTIFIER="techx-tf4-postgresql"
RESTORE_DRILL_ID="${RESTORE_DRILL_ID:-}"
RESTORE_TIMESTAMP="${RESTORE_TIMESTAMP:-}"
RESTORE_TARGET_IDENTIFIER="${RESTORE_TARGET_IDENTIFIER:-}"
DB_SUBNET_GROUP_NAME="${DB_SUBNET_GROUP_NAME:-techx-tf4-postgresql-private}"
RESTORE_SECURITY_GROUP_IDS="${RESTORE_SECURITY_GROUP_IDS:-}"
DB_INSTANCE_CLASS="${DB_INSTANCE_CLASS:-}"
CONFIRM_PITR_RESTORE="${CONFIRM_PITR_RESTORE:-}"
WAIT_TIMEOUT_SECONDS="${WAIT_TIMEOUT_SECONDS:-3600}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-30}"
TTL_HOURS="${TTL_HOURS:-24}"
export AWS_PAGER="${AWS_PAGER:-}"

CURRENT_PHASE="initialization"
RTO_START_EPOCH=0

timestamp() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

log() {
  printf '%s level=%s phase=%s message=%q\n' \
    "$(timestamp)" "$1" "$CURRENT_PHASE" "$2"
}

fail() {
  log "ERROR" "$1" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

require_non_empty() {
  [[ -n "${!1:-}" ]] || fail "Set $1 before running the PITR restore."
}

phase_start() {
  CURRENT_PHASE="$1"
  PHASE_START_EPOCH="$(date +%s)"
  log "INFO" "phase_start"
}

phase_end() {
  local phase_end_epoch
  phase_end_epoch="$(date +%s)"
  log "INFO" "phase_end duration_seconds=$((phase_end_epoch - PHASE_START_EPOCH))"
}

on_exit() {
  local exit_code=$?
  if ((exit_code != 0)); then
    local elapsed=0
    if ((RTO_START_EPOCH > 0)); then
      elapsed=$(( $(date +%s) - RTO_START_EPOCH ))
    fi
    log "ERROR" "restore_failed exit_code=$exit_code rto_elapsed_seconds=$elapsed"
  fi
}
trap on_exit EXIT

wait_for_available() {
  local deadline=$(( $(date +%s) + WAIT_TIMEOUT_SECONDS ))
  local status

  while (( $(date +%s) < deadline )); do
    status="$(aws rds describe-db-instances \
      --region "$AWS_REGION" \
      --profile "$AWS_PROFILE" \
      --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" \
      --query 'DBInstances[0].DBInstanceStatus' \
      --output text)"
    log "INFO" "target_status=$status"

    [[ "$status" == "available" ]] && return 0
    [[ "$status" == "failed" || "$status" == "incompatible-restore" ]] && \
      fail "Restore target entered terminal status: $status"

    sleep "$POLL_INTERVAL_SECONDS"
  done

  fail "Timed out waiting ${WAIT_TIMEOUT_SECONDS}s for restore target to become available."
}

require_cmd aws
require_cmd date
require_cmd sed
require_cmd sort
require_cmd tr
require_non_empty AWS_PROFILE
require_non_empty RESTORE_DRILL_ID
require_non_empty RESTORE_TIMESTAMP
require_non_empty RESTORE_TARGET_IDENTIFIER
require_non_empty DB_SUBNET_GROUP_NAME
require_non_empty RESTORE_SECURITY_GROUP_IDS

[[ "$RESTORE_DRILL_ID" =~ ^[a-z0-9][a-z0-9-]{2,40}$ ]] || \
  fail "RESTORE_DRILL_ID must be 3-41 lowercase letters, numbers, or hyphens."

expected_prefix="techx-tf4-drill-${RESTORE_DRILL_ID}-"
[[ "$RESTORE_TARGET_IDENTIFIER" == "${expected_prefix}"*"accounting"*"restore"* ]] || \
  fail "Target identifier must start with $expected_prefix and contain accounting and restore."

[[ "$RESTORE_TARGET_IDENTIFIER" != "$SOURCE_DB_IDENTIFIER" ]] || \
  fail "Restore target must not equal production source identifier."

restore_epoch="$(date -u -d "$RESTORE_TIMESTAMP" +%s 2>/dev/null)" || \
  fail "RESTORE_TIMESTAMP must be a valid ISO-8601 timestamp."
normalized_restore_timestamp="$(date -u -d "@$restore_epoch" +"%Y-%m-%dT%H:%M:%SZ")"

phase_start "preflight"

source_metadata="$(aws rds describe-db-instances \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --query 'DBInstances[0].{Status:DBInstanceStatus,Class:DBInstanceClass,SubnetVpc:DBSubnetGroup.VpcId,SecurityGroups:VpcSecurityGroups[*].VpcSecurityGroupId}' \
  --output json)"

source_status="$(aws rds describe-db-instances \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --query 'DBInstances[0].DBInstanceStatus' \
  --output text)"
[[ "$source_status" == "available" ]] || fail "Production source must be available; status=$source_status"

if [[ -z "$DB_INSTANCE_CLASS" ]]; then
  DB_INSTANCE_CLASS="$(aws rds describe-db-instances \
    --region "$AWS_REGION" \
    --profile "$AWS_PROFILE" \
    --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
    --query 'DBInstances[0].DBInstanceClass' \
    --output text)"
fi

source_vpc_id="$(aws rds describe-db-instances \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --query 'DBInstances[0].DBSubnetGroup.VpcId' \
  --output text)"

production_security_groups="$(aws rds describe-db-instances \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --query 'DBInstances[0].VpcSecurityGroups[*].VpcSecurityGroupId' \
  --output text)"

read -r -a restore_security_groups <<<"$RESTORE_SECURITY_GROUP_IDS"
for restore_sg in "${restore_security_groups[@]}"; do
  [[ " $production_security_groups " != *" $restore_sg "* ]] || \
    fail "Restore security group must not reuse production security group: $restore_sg"

  sg_vpc_id="$(aws ec2 describe-security-groups \
    --region "$AWS_REGION" \
    --profile "$AWS_PROFILE" \
    --group-ids "$restore_sg" \
    --query 'SecurityGroups[0].VpcId' \
    --output text)"
  [[ "$sg_vpc_id" == "$source_vpc_id" ]] || \
    fail "Restore security group $restore_sg is not in source VPC $source_vpc_id."
done

subnet_vpc_id="$(aws rds describe-db-subnet-groups \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --db-subnet-group-name "$DB_SUBNET_GROUP_NAME" \
  --query 'DBSubnetGroups[0].VpcId' \
  --output text)"
[[ "$subnet_vpc_id" == "$source_vpc_id" ]] || \
  fail "DB subnet group is not in source VPC $source_vpc_id."

restore_window="$(aws rds describe-db-instance-automated-backups \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --query 'DBInstanceAutomatedBackups[0].RestoreWindow.{Earliest:EarliestTime,Latest:LatestTime}' \
  --output json)"
earliest_restore="$(aws rds describe-db-instance-automated-backups \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --query 'DBInstanceAutomatedBackups[0].RestoreWindow.EarliestTime' \
  --output text)"
latest_restore="$(aws rds describe-db-instance-automated-backups \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --query 'DBInstanceAutomatedBackups[0].RestoreWindow.LatestTime' \
  --output text)"

earliest_epoch="$(date -u -d "$earliest_restore" +%s)"
latest_epoch="$(date -u -d "$latest_restore" +%s)"
((restore_epoch >= earliest_epoch && restore_epoch <= latest_epoch)) || \
  fail "Restore timestamp is outside the available PITR window: $restore_window"

target_lookup_output=""
if target_lookup_output="$(aws rds describe-db-instances \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" 2>&1)"; then
  fail "Restore target already exists: $RESTORE_TARGET_IDENTIFIER"
fi
[[ "$target_lookup_output" == *"DBInstanceNotFound"* ]] || \
  fail "Could not safely verify target absence: $target_lookup_output"

[[ "$CONFIRM_PITR_RESTORE" == "YES" ]] || \
  fail "Set CONFIRM_PITR_RESTORE=YES after reviewing source, target, timestamp, subnet, and security groups."

log "INFO" "source=$SOURCE_DB_IDENTIFIER target=$RESTORE_TARGET_IDENTIFIER restore_time=$normalized_restore_timestamp"
log "INFO" "instance_class=$DB_INSTANCE_CLASS subnet_group=$DB_SUBNET_GROUP_NAME restore_security_groups=$RESTORE_SECURITY_GROUP_IDS"
log "INFO" "source_metadata=$source_metadata"
phase_end

cleanup_after="$(date -u -d "+${TTL_HOURS} hours" +"%Y-%m-%dT%H:%M:%SZ")"
RTO_START_EPOCH="$(date +%s)"
log "INFO" "rto_start restore_time=$normalized_restore_timestamp"

phase_start "restore_request"
aws rds restore-db-instance-to-point-in-time \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --source-db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --target-db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" \
  --restore-time "$normalized_restore_timestamp" \
  --db-instance-class "$DB_INSTANCE_CLASS" \
  --db-subnet-group-name "$DB_SUBNET_GROUP_NAME" \
  --vpc-security-group-ids "${restore_security_groups[@]}" \
  --no-publicly-accessible \
  --no-multi-az \
  --copy-tags-to-snapshot \
  --tags \
    Key=Owner,Value=CDO08 \
    Key=Team,Value=CDO08 \
    Key=Project,Value=TF4 \
    Key=Environment,Value=RestoreDrill \
    Key=Mandate,Value=20 \
    Key=Task,Value=CDO08-REL-25 \
    Key=RestoreDrillId,Value="$RESTORE_DRILL_ID" \
    Key=TTLHours,Value="$TTL_HOURS" \
    Key=CleanupAfter,Value="$cleanup_after" \
    Key=Production,Value=false \
  --query 'DBInstance.{Identifier:DBInstanceIdentifier,Status:DBInstanceStatus,RestoreTime:InstanceCreateTime}' \
  --output json
phase_end

phase_start "wait_initial_available"
wait_for_available
phase_end

phase_start "apply_network_access"
aws rds modify-db-instance \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" \
  --vpc-security-group-ids "${restore_security_groups[@]}" \
  --apply-immediately \
  --query 'DBInstance.{Identifier:DBInstanceIdentifier,Status:DBInstanceStatus,SecurityGroups:VpcSecurityGroups[*].VpcSecurityGroupId}' \
  --output json
phase_end

phase_start "wait_network_available"
wait_for_available
phase_end

phase_start "verify_target"
target_metadata="$(aws rds describe-db-instances \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" \
  --query 'DBInstances[0].{Identifier:DBInstanceIdentifier,Status:DBInstanceStatus,Endpoint:Endpoint.Address,Public:PubliclyAccessible,SubnetGroup:DBSubnetGroup.DBSubnetGroupName,SecurityGroups:VpcSecurityGroups[*].VpcSecurityGroupId}' \
  --output json)"
target_public="$(aws rds describe-db-instances \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" \
  --query 'DBInstances[0].PubliclyAccessible' \
  --output text)"
[[ "$target_public" == "False" ]] || fail "Restored target is publicly accessible."

target_subnet_group="$(aws rds describe-db-instances \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" \
  --query 'DBInstances[0].DBSubnetGroup.DBSubnetGroupName' \
  --output text)"
[[ "$target_subnet_group" == "$DB_SUBNET_GROUP_NAME" ]] || \
  fail "Restored target subnet group does not match requested subnet group."

target_security_groups="$(aws rds describe-db-instances \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" \
  --query 'DBInstances[0].VpcSecurityGroups[*].VpcSecurityGroupId' \
  --output text)"
expected_sg_set="$(printf '%s\n' "${restore_security_groups[@]}" | sort)"
actual_sg_set="$(tr '\t ' '\n' <<<"$target_security_groups" | sed '/^$/d' | sort)"
[[ "$actual_sg_set" == "$expected_sg_set" ]] || \
  fail "Restored target security groups do not match requested restore-only security groups."

log "INFO" "target_metadata=$target_metadata"
phase_end

rto_end_epoch="$(date +%s)"
CURRENT_PHASE="complete"
log "INFO" "rto_end rto_seconds=$((rto_end_epoch - RTO_START_EPOCH))"
log "INFO" "PITR restore completed; production source was not modified."
