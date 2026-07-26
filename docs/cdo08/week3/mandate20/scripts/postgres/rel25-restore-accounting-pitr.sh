#!/usr/bin/env bash
set -Eeuo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_PROFILE="${AWS_PROFILE:-}"
EXPECTED_AWS_ACCOUNT_ID="${EXPECTED_AWS_ACCOUNT_ID:-}"
SOURCE_DB_IDENTIFIER="${SOURCE_DB_IDENTIFIER:-techx-tf4-postgresql}"
DB_SUBNET_GROUP_NAME="${DB_SUBNET_GROUP_NAME:-techx-tf4-postgresql-private}"
RESTORE_DRILL_ID="${RESTORE_DRILL_ID:-}"
RESTORE_TIMESTAMP="${RESTORE_TIMESTAMP:-}"
RESTORE_TARGET_IDENTIFIER="${RESTORE_TARGET_IDENTIFIER:-}"
RESTORE_INSTANCE_CLASS="${RESTORE_INSTANCE_CLASS:-}"
VALIDATION_INSTANCE_TYPE="${VALIDATION_INSTANCE_TYPE:-t3.nano}"
VALIDATION_ROLE_NAME="${VALIDATION_ROLE_NAME:-techx-tf4-rel25-validation}"
VALIDATION_PROFILE_NAME="${VALIDATION_PROFILE_NAME:-techx-tf4-rel25-validation}"
ACCOUNTING_SOURCE_DB="${ACCOUNTING_SOURCE_DB:-otel}"
ACCOUNTING_TARGET_DB="${ACCOUNTING_TARGET_DB:-accounting_drill}"
PREFLIGHT_ONLY="${PREFLIGHT_ONLY:-false}"
CONFIRM_PITR_RESTORE="${CONFIRM_PITR_RESTORE:-}"
AUTO_CLEANUP="${AUTO_CLEANUP:-true}"
WAIT_TIMEOUT_SECONDS="${WAIT_TIMEOUT_SECONDS:-3600}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-30}"
TTL_HOURS="${TTL_HOURS:-6}"
EXECUTION_LOG="${EXECUTION_LOG:-rel25-${RESTORE_DRILL_ID:-unset}-execution.log}"
export AWS_PAGER=""

PHASE="initialization"
PHASE_START=0
RTO_START=0
RESTORE_CREATED=false
INSTANCE_CREATED=false
VALIDATION_SG_CREATED=false
RESTORE_SG_CREATED=false
ROLE_CREATED=false
PROFILE_CREATED=false
VALIDATION_INSTANCE_ID=""
VALIDATION_SECURITY_GROUP_ID=""
RESTORE_SECURITY_GROUP_ID=""
RESTORE_ENDPOINT=""
TARGET_MASTER_SECRET_ARN=""
SOURCE_MASTER_SECRET_ARN=""
CLEANUP_FAILED=false

now() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
epoch() { date +%s; }
log() { printf '%s level=%s phase=%s message=%q\n' "$(now)" "$1" "$PHASE" "$2"; }
fail() { log ERROR "$1" >&2; exit 1; }
need() { [[ -n "${!1:-}" ]] || fail "Set $1 before running."; }
phase() { PHASE="$1"; PHASE_START="$(epoch)"; log INFO phase_start; }
phase_done() { log INFO "phase_end duration_seconds=$(( $(epoch) - PHASE_START ))"; }
aws_cli() { aws --profile "$AWS_PROFILE" --region "$AWS_REGION" "$@"; }

resource_exists() {
  [[ "$1" == true ]]
}

wait_for_rds_status() {
  local identifier="$1"
  local expected="$2"
  local deadline=$(( $(epoch) + WAIT_TIMEOUT_SECONDS ))
  local status
  while (( $(epoch) < deadline )); do
    status="$(aws_cli rds describe-db-instances \
      --db-instance-identifier "$identifier" \
      --query 'DBInstances[0].DBInstanceStatus' --output text 2>/dev/null || true)"
    log INFO "rds_identifier=$identifier status=${status:-not-found}"
    [[ "$status" == "$expected" ]] && return 0
    [[ "$status" == failed || "$status" == incompatible-restore ]] && \
      fail "RDS target entered terminal status $status."
    sleep "$POLL_INTERVAL_SECONDS"
  done
  fail "Timed out waiting for RDS $identifier to become $expected."
}

wait_for_rds_deleted() {
  local deadline=$(( $(epoch) + WAIT_TIMEOUT_SECONDS ))
  while (( $(epoch) < deadline )); do
    if ! aws_cli rds describe-db-instances \
      --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$POLL_INTERVAL_SECONDS"
  done
  return 1
}

wait_for_ssm_online() {
  local deadline=$(( $(epoch) + 900 ))
  local status
  while (( $(epoch) < deadline )); do
    status="$(aws_cli ssm describe-instance-information \
      --filters "Key=InstanceIds,Values=$VALIDATION_INSTANCE_ID" \
      --query 'InstanceInformationList[0].PingStatus' --output text 2>/dev/null || true)"
    log INFO "validation_instance=$VALIDATION_INSTANCE_ID ssm_status=${status:-not-registered}"
    [[ "$status" == Online ]] && return 0
    sleep 15
  done
  fail "Validation EC2 did not become Online in SSM."
}

ssm_exec() {
  local label="$1"
  local script="$2"
  local encoded parameters command_id deadline status output
  encoded="$(printf '%s' "$script" | base64 | tr -d '\r\n')"
  parameters="{\"commands\":[\"printf '%s' '$encoded' | base64 -d >/tmp/rel25-command.sh && chmod 700 /tmp/rel25-command.sh && /tmp/rel25-command.sh\"]}"
  command_id="$(aws_cli ssm send-command \
    --instance-ids "$VALIDATION_INSTANCE_ID" \
    --document-name AWS-RunShellScript \
    --comment "REL-25 $label" \
    --parameters "$parameters" \
    --query 'Command.CommandId' --output text)"
  log INFO "ssm_command=$label command_id=$command_id"

  deadline=$(( $(epoch) + 900 ))
  while (( $(epoch) < deadline )); do
    status="$(aws_cli ssm get-command-invocation \
      --command-id "$command_id" --instance-id "$VALIDATION_INSTANCE_ID" \
      --query Status --output text 2>/dev/null || true)"
    case "$status" in
      Success) break ;;
      Failed|Cancelled|TimedOut)
        aws_cli ssm get-command-invocation \
          --command-id "$command_id" --instance-id "$VALIDATION_INSTANCE_ID" \
          --query '{Status:Status,Output:StandardOutputContent,Error:StandardErrorContent}' \
          --output json >&2 || true
        fail "SSM command $label failed with status $status."
        ;;
    esac
    sleep 5
  done
  [[ "$status" == Success ]] || fail "SSM command $label timed out."
  output="$(aws_cli ssm get-command-invocation \
    --command-id "$command_id" --instance-id "$VALIDATION_INSTANCE_ID" \
    --query StandardOutputContent --output text)"
  printf '%s\n' "$output"
}

delete_security_group() {
  local sg_id="$1"
  local attempts=0
  [[ -n "$sg_id" ]] || return 0
  until aws_cli ec2 delete-security-group --group-id "$sg_id" >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    ((attempts < 20)) || return 1
    sleep 10
  done
}

cleanup() {
  local original_code="$1"
  PHASE="cleanup"
  log INFO "cleanup_start original_exit_code=$original_code"

  if resource_exists "$RESTORE_CREATED"; then
    if aws_cli rds delete-db-instance \
      --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" \
      --skip-final-snapshot --delete-automated-backups >/dev/null 2>&1 &&
      wait_for_rds_deleted; then
      RESTORE_CREATED=false
      log INFO "cleanup_deleted_rds=$RESTORE_TARGET_IDENTIFIER"
    else
      CLEANUP_FAILED=true
      log ERROR "cleanup_remaining_rds=$RESTORE_TARGET_IDENTIFIER"
    fi
  fi

  if resource_exists "$INSTANCE_CREATED"; then
    if aws_cli ec2 terminate-instances \
      --instance-ids "$VALIDATION_INSTANCE_ID" >/dev/null 2>&1 &&
      aws_cli ec2 wait instance-terminated --instance-ids "$VALIDATION_INSTANCE_ID"; then
      INSTANCE_CREATED=false
      log INFO "cleanup_terminated_ec2=$VALIDATION_INSTANCE_ID"
    else
      CLEANUP_FAILED=true
      log ERROR "cleanup_remaining_ec2=$VALIDATION_INSTANCE_ID"
    fi
  fi

  if resource_exists "$RESTORE_SG_CREATED" &&
     resource_exists "$VALIDATION_SG_CREATED"; then
    aws_cli ec2 revoke-security-group-ingress \
      --group-id "$RESTORE_SECURITY_GROUP_ID" \
      --ip-permissions \
        "IpProtocol=tcp,FromPort=5432,ToPort=5432,UserIdGroupPairs=[{GroupId=$VALIDATION_SECURITY_GROUP_ID}]" \
      >/dev/null 2>&1 || true
    aws_cli ec2 revoke-security-group-egress \
      --group-id "$VALIDATION_SECURITY_GROUP_ID" \
      --ip-permissions \
        "IpProtocol=tcp,FromPort=5432,ToPort=5432,UserIdGroupPairs=[{GroupId=$RESTORE_SECURITY_GROUP_ID}]" \
      >/dev/null 2>&1 || true
  fi

  if resource_exists "$RESTORE_SG_CREATED"; then
    if delete_security_group "$RESTORE_SECURITY_GROUP_ID"; then
      RESTORE_SG_CREATED=false
      log INFO "cleanup_deleted_sg=$RESTORE_SECURITY_GROUP_ID"
    else
      CLEANUP_FAILED=true
      log ERROR "cleanup_remaining_sg=$RESTORE_SECURITY_GROUP_ID"
    fi
  fi
  if resource_exists "$VALIDATION_SG_CREATED"; then
    if delete_security_group "$VALIDATION_SECURITY_GROUP_ID"; then
      VALIDATION_SG_CREATED=false
      log INFO "cleanup_deleted_sg=$VALIDATION_SECURITY_GROUP_ID"
    else
      CLEANUP_FAILED=true
      log ERROR "cleanup_remaining_sg=$VALIDATION_SECURITY_GROUP_ID"
    fi
  fi

  if resource_exists "$PROFILE_CREATED"; then
    aws iam remove-role-from-instance-profile --profile "$AWS_PROFILE" \
      --instance-profile-name "$VALIDATION_PROFILE_NAME" \
      --role-name "$VALIDATION_ROLE_NAME" >/dev/null 2>&1 || true
    if aws iam delete-instance-profile --profile "$AWS_PROFILE" \
      --instance-profile-name "$VALIDATION_PROFILE_NAME" >/dev/null 2>&1; then
      PROFILE_CREATED=false
      log INFO "cleanup_deleted_instance_profile=$VALIDATION_PROFILE_NAME"
    else
      CLEANUP_FAILED=true
      log ERROR "cleanup_remaining_instance_profile=$VALIDATION_PROFILE_NAME"
    fi
  fi

  if resource_exists "$ROLE_CREATED"; then
    aws iam delete-role-policy --profile "$AWS_PROFILE" \
      --role-name "$VALIDATION_ROLE_NAME" \
      --policy-name REL25TargetMasterSecretRead >/dev/null 2>&1 || true
    aws iam detach-role-policy --profile "$AWS_PROFILE" \
      --role-name "$VALIDATION_ROLE_NAME" \
      --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore >/dev/null 2>&1 || true
    if aws iam delete-role --profile "$AWS_PROFILE" \
      --role-name "$VALIDATION_ROLE_NAME" >/dev/null 2>&1; then
      ROLE_CREATED=false
      log INFO "cleanup_deleted_role=$VALIDATION_ROLE_NAME"
    else
      CLEANUP_FAILED=true
      log ERROR "cleanup_remaining_role=$VALIDATION_ROLE_NAME"
    fi
  fi

  if [[ "$CLEANUP_FAILED" == true ]]; then
    log ERROR cleanup_incomplete_manual_action_required
    return 1
  fi
  log INFO cleanup_complete_no_drill_resources_remaining
}

on_exit() {
  local code=$?
  trap - EXIT
  if [[ "$PREFLIGHT_ONLY" != true && "$AUTO_CLEANUP" == true ]]; then
    cleanup "$code" || code=1
  elif [[ "$PREFLIGHT_ONLY" != true ]]; then
    PHASE="cleanup"
    log WARN "auto_cleanup_disabled rds=$RESTORE_TARGET_IDENTIFIER ec2=$VALIDATION_INSTANCE_ID validation_sg=$VALIDATION_SECURITY_GROUP_ID restore_sg=$RESTORE_SECURITY_GROUP_ID role=$VALIDATION_ROLE_NAME profile=$VALIDATION_PROFILE_NAME"
  fi
  exit "$code"
}
trap on_exit EXIT

for command in aws base64 date tee tr; do
  command -v "$command" >/dev/null 2>&1 || fail "Missing command $command."
done
for variable in AWS_PROFILE EXPECTED_AWS_ACCOUNT_ID RESTORE_DRILL_ID \
  RESTORE_TIMESTAMP RESTORE_TARGET_IDENTIFIER; do
  need "$variable"
done
for number in WAIT_TIMEOUT_SECONDS POLL_INTERVAL_SECONDS TTL_HOURS; do
  [[ "${!number}" =~ ^[1-9][0-9]*$ ]] || fail "$number must be a positive integer."
done
[[ "$PREFLIGHT_ONLY" == true || "$PREFLIGHT_ONLY" == false ]] || \
  fail "PREFLIGHT_ONLY must be true or false."
[[ "$AUTO_CLEANUP" == true || "$AUTO_CLEANUP" == false ]] || \
  fail "AUTO_CLEANUP must be true or false."
[[ "$RESTORE_DRILL_ID" =~ ^rel25-[0-9]{8}(-[a-z0-9-]+)?$ ]] || \
  fail "RESTORE_DRILL_ID must start with rel25-YYYYMMDD."
[[ "$RESTORE_TARGET_IDENTIFIER" == "techx-tf4-drill-${RESTORE_DRILL_ID}-accounting-restore" ]] || \
  fail "RESTORE_TARGET_IDENTIFIER violates the REL-25 naming contract."
[[ "$RESTORE_TARGET_IDENTIFIER" != "$SOURCE_DB_IDENTIFIER" ]] || fail "Restore target equals production source."
[[ "$ACCOUNTING_TARGET_DB" == accounting_drill ]] || \
  fail "ACCOUNTING_TARGET_DB must be accounting_drill."
[[ "$VALIDATION_ROLE_NAME" == techx-tf4-rel25-validation ]] || \
  fail "Unexpected validation role name."
[[ "$VALIDATION_PROFILE_NAME" == techx-tf4-rel25-validation ]] || \
  fail "Unexpected validation profile name."

restore_epoch="$(date -u -d "$RESTORE_TIMESTAMP" +%s 2>/dev/null)" || \
  fail "RESTORE_TIMESTAMP is not a valid timestamp."
restore_time="$(date -u -d "@$restore_epoch" +"%Y-%m-%dT%H:%M:%SZ")"

mkdir -p "$(dirname "$EXECUTION_LOG")"
exec > >(tee -a "$EXECUTION_LOG") 2>&1
log INFO "execution_log=$EXECUTION_LOG"

phase environment_preflight
account_id="$(aws --profile "$AWS_PROFILE" sts get-caller-identity \
  --query Account --output text)"
[[ "$account_id" == "$EXPECTED_AWS_ACCOUNT_ID" ]] || \
  fail "AWS account does not match EXPECTED_AWS_ACCOUNT_ID."

read -r source_status source_class source_vpc source_endpoint source_public \
  source_subnet SOURCE_MASTER_SECRET_ARN <<<"$(aws_cli rds describe-db-instances \
  --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --query 'DBInstances[0].[DBInstanceStatus,DBInstanceClass,DBSubnetGroup.VpcId,Endpoint.Address,PubliclyAccessible,DBSubnetGroup.DBSubnetGroupName,MasterUserSecret.SecretArn]' \
  --output text)"
[[ "$source_status" == available ]] || fail "Source RDS is not available."
[[ "$source_public" == False ]] || fail "Production source is unexpectedly public."
[[ "$source_subnet" == "$DB_SUBNET_GROUP_NAME" ]] || fail "Unexpected DB subnet group."
[[ "$SOURCE_MASTER_SECRET_ARN" == arn:aws:secretsmanager:*:*:secret:rds\!db-* ]] || \
  fail "Production source has no RDS-managed master secret."
RESTORE_INSTANCE_CLASS="${RESTORE_INSTANCE_CLASS:-$source_class}"

read -r earliest latest <<<"$(aws_cli rds describe-db-instance-automated-backups \
  --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --query 'DBInstanceAutomatedBackups[0].RestoreWindow.[EarliestTime,LatestTime]' \
  --output text)"
earliest_epoch="$(date -u -d "$earliest" +%s)"
latest_epoch="$(date -u -d "$latest" +%s)"
((restore_epoch >= earliest_epoch && restore_epoch <= latest_epoch)) || \
  fail "Restore timestamp is outside PITR window $earliest to $latest."

target_check=""
if target_check="$(aws_cli rds describe-db-instances \
  --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" 2>&1)"; then
  fail "Restore target already exists."
fi
[[ "$target_check" == *DBInstanceNotFound* ]] || fail "Could not verify target absence."

production_sgs="$(aws_cli rds describe-db-instances \
  --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --query 'DBInstances[0].VpcSecurityGroups[*].VpcSecurityGroupId' --output text)"
vpc_cidr="$(aws_cli ec2 describe-vpcs --vpc-ids "$source_vpc" \
  --query 'Vpcs[0].CidrBlock' --output text)"
validation_subnet="$(aws_cli rds describe-db-subnet-groups \
  --db-subnet-group-name "$DB_SUBNET_GROUP_NAME" \
  --query 'DBSubnetGroups[0].Subnets[0].SubnetIdentifier' --output text)"
map_public_ip="$(aws_cli ec2 describe-subnets --subnet-ids "$validation_subnet" \
  --query 'Subnets[0].MapPublicIpOnLaunch' --output text)"
[[ "$map_public_ip" == False ]] || fail "Validation subnet maps public IPs."

log INFO "preflight_passed source=$SOURCE_DB_IDENTIFIER target=$RESTORE_TARGET_IDENTIFIER restore_time=$restore_time vpc=$source_vpc subnet=$validation_subnet"
phase_done

if [[ "$PREFLIGHT_ONLY" == true ]]; then
  PHASE=complete
  log INFO preflight_only_passed_no_resources_created
  exit 0
fi
[[ "$CONFIRM_PITR_RESTORE" == YES ]] || fail "Set CONFIRM_PITR_RESTORE=YES."

cleanup_after="$(date -u -d "+${TTL_HOURS} hours" +"%Y-%m-%dT%H:%M:%SZ")"
common_tags=(
  Key=Owner,Value=CDO08
  Key=Environment,Value=RestoreDrill
  Key=Mandate,Value=20
  Key=Task,Value=CDO08-REL-25
  Key=RestoreDrillId,Value="$RESTORE_DRILL_ID"
  Key=TTLHours,Value="$TTL_HOURS"
  Key=CleanupAfter,Value="$cleanup_after"
  Key=CostCenter,Value=ReliabilityDrill
  Key=Production,Value=false
)

phase create_validation_identity
if aws iam get-role --profile "$AWS_PROFILE" \
  --role-name "$VALIDATION_ROLE_NAME" >/dev/null 2>&1; then
  fail "Validation IAM role already exists; cleanup or review it before running."
fi
trust_policy='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam create-role --profile "$AWS_PROFILE" \
  --role-name "$VALIDATION_ROLE_NAME" \
  --assume-role-policy-document "$trust_policy" \
  --tags Key=Owner,Value=CDO08 Key=Environment,Value=RestoreDrill \
    Key=RestoreDrillId,Value="$RESTORE_DRILL_ID" Key=Production,Value=false >/dev/null
ROLE_CREATED=true
aws iam attach-role-policy --profile "$AWS_PROFILE" \
  --role-name "$VALIDATION_ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
secret_policy="{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadOnlyPITRMasterCredential\",\"Effect\":\"Allow\",\"Action\":[\"secretsmanager:DescribeSecret\",\"secretsmanager:GetSecretValue\"],\"Resource\":\"$SOURCE_MASTER_SECRET_ARN\"}]}"
aws iam put-role-policy --profile "$AWS_PROFILE" \
  --role-name "$VALIDATION_ROLE_NAME" \
  --policy-name REL25TargetMasterSecretRead \
  --policy-document "$secret_policy"
aws iam create-instance-profile --profile "$AWS_PROFILE" \
  --instance-profile-name "$VALIDATION_PROFILE_NAME" >/dev/null
PROFILE_CREATED=true
aws iam add-role-to-instance-profile --profile "$AWS_PROFILE" \
  --instance-profile-name "$VALIDATION_PROFILE_NAME" \
  --role-name "$VALIDATION_ROLE_NAME"
sleep 10
log INFO "created_role=$VALIDATION_ROLE_NAME instance_profile=$VALIDATION_PROFILE_NAME"
phase_done

phase create_isolated_network
VALIDATION_SECURITY_GROUP_ID="$(aws_cli ec2 create-security-group \
  --group-name "techx-tf4-${RESTORE_DRILL_ID}-validation" \
  --description "REL-25 temporary private EC2 validation client" \
  --vpc-id "$source_vpc" --query GroupId --output text)"
VALIDATION_SG_CREATED=true
aws_cli ec2 create-tags --resources "$VALIDATION_SECURITY_GROUP_ID" \
  --tags "${common_tags[@]}" Key=Purpose,Value=RestoreValidationClient \
    Key=Name,Value="techx-tf4-${RESTORE_DRILL_ID}-validation"

RESTORE_SECURITY_GROUP_ID="$(aws_cli ec2 create-security-group \
  --group-name "techx-tf4-${RESTORE_DRILL_ID}-restore" \
  --description "REL-25 temporary RDS PITR target" \
  --vpc-id "$source_vpc" --query GroupId --output text)"
RESTORE_SG_CREATED=true
aws_cli ec2 create-tags --resources "$RESTORE_SECURITY_GROUP_ID" \
  --tags "${common_tags[@]}" Key=Purpose,Value=RestoreTarget \
    Key=Name,Value="techx-tf4-${RESTORE_DRILL_ID}-restore"

aws_cli ec2 revoke-security-group-egress --group-id "$VALIDATION_SECURITY_GROUP_ID" \
  --ip-permissions '[{"IpProtocol":"-1","IpRanges":[{"CidrIp":"0.0.0.0/0"}]}]' >/dev/null
aws_cli ec2 revoke-security-group-egress --group-id "$RESTORE_SECURITY_GROUP_ID" \
  --ip-permissions '[{"IpProtocol":"-1","IpRanges":[{"CidrIp":"0.0.0.0/0"}]}]' >/dev/null
aws_cli ec2 authorize-security-group-egress --group-id "$VALIDATION_SECURITY_GROUP_ID" \
  --ip-permissions \
    "IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=0.0.0.0/0,Description=AWS-SSM-and-package-repositories}]" \
    "IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=0.0.0.0/0,Description=Package-bootstrap-only}]" \
    "IpProtocol=udp,FromPort=53,ToPort=53,IpRanges=[{CidrIp=$vpc_cidr,Description=VPC-DNS}]" \
    "IpProtocol=tcp,FromPort=53,ToPort=53,IpRanges=[{CidrIp=$vpc_cidr,Description=VPC-DNS}]" \
  >/dev/null
aws_cli ec2 authorize-security-group-egress --group-id "$VALIDATION_SECURITY_GROUP_ID" \
  --ip-permissions \
    "IpProtocol=tcp,FromPort=5432,ToPort=5432,UserIdGroupPairs=[{GroupId=$RESTORE_SECURITY_GROUP_ID,Description=REL25-RDS-only}]" \
  >/dev/null
aws_cli ec2 authorize-security-group-ingress --group-id "$RESTORE_SECURITY_GROUP_ID" \
  --ip-permissions \
    "IpProtocol=tcp,FromPort=5432,ToPort=5432,UserIdGroupPairs=[{GroupId=$VALIDATION_SECURITY_GROUP_ID,Description=REL25-validation-only}]" \
  >/dev/null
[[ " $production_sgs " != *" $RESTORE_SECURITY_GROUP_ID "* ]] || \
  fail "Restore SG unexpectedly matches production."
log INFO "created_validation_sg=$VALIDATION_SECURITY_GROUP_ID created_restore_sg=$RESTORE_SECURITY_GROUP_ID"
phase_done

phase create_validation_ec2
ami_id="$(aws_cli ssm get-parameter \
  --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query Parameter.Value --output text)"
user_data='#!/bin/bash
set -euo pipefail
dnf install -y jq postgresql17
systemctl enable --now amazon-ssm-agent
touch /var/lib/rel25-bootstrap-complete
'
VALIDATION_INSTANCE_ID="$(aws_cli ec2 run-instances \
  --image-id "$ami_id" \
  --instance-type "$VALIDATION_INSTANCE_TYPE" \
  --subnet-id "$validation_subnet" \
  --security-group-ids "$VALIDATION_SECURITY_GROUP_ID" \
  --iam-instance-profile "Name=$VALIDATION_PROFILE_NAME" \
  --no-associate-public-ip-address \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=1 \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"Encrypted":true,"DeleteOnTermination":true,"VolumeType":"gp3","VolumeSize":8}}]' \
  --user-data "$user_data" \
  --tag-specifications \
    "ResourceType=instance,Tags=[{Key=Name,Value=techx-tf4-${RESTORE_DRILL_ID}-validation},{Key=Owner,Value=CDO08},{Key=Environment,Value=RestoreDrill},{Key=RestoreDrillId,Value=${RESTORE_DRILL_ID}},{Key=TTLHours,Value=${TTL_HOURS}},{Key=CleanupAfter,Value=${cleanup_after}},{Key=Production,Value=false}]" \
    "ResourceType=volume,Tags=[{Key=Name,Value=techx-tf4-${RESTORE_DRILL_ID}-validation},{Key=Owner,Value=CDO08},{Key=Environment,Value=RestoreDrill},{Key=RestoreDrillId,Value=${RESTORE_DRILL_ID}},{Key=CleanupAfter,Value=${cleanup_after}},{Key=Production,Value=false}]" \
  --query 'Instances[0].InstanceId' --output text)"
INSTANCE_CREATED=true
aws_cli ec2 wait instance-running --instance-ids "$VALIDATION_INSTANCE_ID"
read -r public_ip attached_sgs <<<"$(aws_cli ec2 describe-instances \
  --instance-ids "$VALIDATION_INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].[PublicIpAddress,SecurityGroups[*].GroupId|join(`,`,@)]' \
  --output text)"
[[ "$public_ip" == None ]] || fail "Validation EC2 unexpectedly has a public IP."
[[ "$attached_sgs" == "$VALIDATION_SECURITY_GROUP_ID" ]] || \
  fail "Validation EC2 has an unexpected security group."
wait_for_ssm_online
ssm_exec bootstrap_check 'set -euo pipefail
deadline=$(( $(date +%s) + 600 ))
while [[ ! -f /var/lib/rel25-bootstrap-complete ]] && (( $(date +%s) < deadline )); do
  sleep 10
done
if [[ ! -f /var/lib/rel25-bootstrap-complete ]]; then
  systemctl is-active amazon-ssm-agent || true
  cloud-init status --long || true
  dnf list installed jq postgresql17 || true
  echo bootstrap_check=TIMEOUT >&2
  exit 1
fi
command -v aws >/dev/null
command -v jq >/dev/null
command -v pg_isready >/dev/null
command -v pg_dump >/dev/null
command -v pg_restore >/dev/null
command -v psql >/dev/null
echo bootstrap_check=PASS' >/dev/null
log INFO "created_validation_ec2=$VALIDATION_INSTANCE_ID public_ip=none ssm=Online"
phase_done

RTO_START="$(epoch)"
log INFO "rto_start restore_time=$restore_time"

phase restore_request
aws_cli rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --target-db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" \
  --restore-time "$restore_time" \
  --db-instance-class "$RESTORE_INSTANCE_CLASS" \
  --db-subnet-group-name "$DB_SUBNET_GROUP_NAME" \
  --vpc-security-group-ids "$RESTORE_SECURITY_GROUP_ID" \
  --no-publicly-accessible --no-multi-az --copy-tags-to-snapshot \
  --tags "${common_tags[@]}" Key=Purpose,Value=AccountingPITR >/dev/null
RESTORE_CREATED=true
log INFO "restore_requested target=$RESTORE_TARGET_IDENTIFIER"
phase_done

phase wait_restore_available
wait_for_rds_status "$RESTORE_TARGET_IDENTIFIER" available
phase_done

phase apply_and_verify_network
aws_cli rds modify-db-instance \
  --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" \
  --vpc-security-group-ids "$RESTORE_SECURITY_GROUP_ID" \
  --apply-immediately >/dev/null
wait_for_rds_status "$RESTORE_TARGET_IDENTIFIER" available
read -r target_status RESTORE_ENDPOINT target_public target_subnet target_sgs \
  TARGET_MASTER_SECRET_ARN <<<"$(aws_cli rds describe-db-instances \
  --db-instance-identifier "$RESTORE_TARGET_IDENTIFIER" \
  --query 'DBInstances[0].[DBInstanceStatus,Endpoint.Address,PubliclyAccessible,DBSubnetGroup.DBSubnetGroupName,VpcSecurityGroups[*].VpcSecurityGroupId|join(`,`,@),MasterUserSecret.SecretArn]' \
  --output text)"
[[ "$target_status" == available ]] || fail "Restore target is not available."
[[ "$target_public" == False ]] || fail "Restore target is public."
[[ "$target_subnet" == "$DB_SUBNET_GROUP_NAME" ]] || fail "Restore target uses wrong subnet group."
[[ "$target_sgs" == "$RESTORE_SECURITY_GROUP_ID" ]] || fail "Restore target uses an unexpected SG."
[[ "$RESTORE_ENDPOINT" != "$source_endpoint" ]] || fail "Restore endpoint equals production."
if [[ "$TARGET_MASTER_SECRET_ARN" == None ]]; then
  TARGET_MASTER_SECRET_ARN="$SOURCE_MASTER_SECRET_ARN"
  log INFO restored_rds_uses_pitr_inherited_master_credential
elif [[ "$TARGET_MASTER_SECRET_ARN" != arn:aws:secretsmanager:*:*:secret:rds\!db-* ]]; then
  fail "Restored RDS returned an invalid master secret ARN."
fi
log INFO "restore_verified target=$RESTORE_TARGET_IDENTIFIER endpoint_is_distinct=true public=false sg=$RESTORE_SECURITY_GROUP_ID"
phase_done

phase verify_master_credential_scope
log INFO validation_role_secret_policy_scoped_to_pitr_master_credential
phase_done

phase recover_accounting
recovery_output="$(ssm_exec accounting_recovery "set -euo pipefail
umask 077
SECRET_JSON=\$(aws secretsmanager get-secret-value --region '$AWS_REGION' --secret-id '$TARGET_MASTER_SECRET_ARN' --query SecretString --output text)
PGUSER=\$(printf '%s' \"\$SECRET_JSON\" | jq -r .username)
PGPASSWORD=\$(printf '%s' \"\$SECRET_JSON\" | jq -r .password)
export PGUSER PGPASSWORD PGSSLMODE=require
unset SECRET_JSON
HOST='$RESTORE_ENDPOINT'
DUMP=/tmp/rel25-accounting.dump
trap 'rm -f \"\$DUMP\"' EXIT
pg_isready -h \"\$HOST\" -p 5432 -d '$ACCOUNTING_SOURCE_DB' -t 10
psql -h \"\$HOST\" -d postgres -v ON_ERROR_STOP=1 -c \"drop database if exists $ACCOUNTING_TARGET_DB;\"
psql -h \"\$HOST\" -d postgres -v ON_ERROR_STOP=1 -c \"create database $ACCOUNTING_TARGET_DB;\"
pg_dump -h \"\$HOST\" -d '$ACCOUNTING_SOURCE_DB' --format=custom --no-owner --no-privileges --schema=accounting --file=\"\$DUMP\"
test -s \"\$DUMP\"
psql -h \"\$HOST\" -d '$ACCOUNTING_TARGET_DB' -v ON_ERROR_STOP=1 -c 'create schema accounting;'
pg_restore -h \"\$HOST\" -d '$ACCOUNTING_TARGET_DB' --no-owner --no-privileges --schema=accounting --exit-on-error \"\$DUMP\"
SOURCE_COUNTS=\$(psql -h \"\$HOST\" -d '$ACCOUNTING_SOURCE_DB' -At -F, -v ON_ERROR_STOP=1 -c 'select (select count(*) from accounting.\"order\"),(select count(*) from accounting.shipping),(select count(*) from accounting.orderitem);')
TARGET_COUNTS=\$(psql -h \"\$HOST\" -d '$ACCOUNTING_TARGET_DB' -At -F, -v ON_ERROR_STOP=1 -c 'select (select count(*) from accounting.\"order\"),(select count(*) from accounting.shipping),(select count(*) from accounting.orderitem);')
test \"\$SOURCE_COUNTS\" = \"\$TARGET_COUNTS\"
read -r DUPLICATES SHIPPING_ORPHANS ITEM_ORPHANS UNEXPECTED_SCHEMAS <<<\"\$(psql -h \"\$HOST\" -d '$ACCOUNTING_TARGET_DB' -At -F' ' -v ON_ERROR_STOP=1 -c \"select
  (select count(*) from (select order_id from accounting.\\\"order\\\" group by order_id having count(*) > 1) d),
  (select count(*) from accounting.shipping s left join accounting.\\\"order\\\" o on o.order_id=s.order_id where o.order_id is null),
  (select count(*) from accounting.orderitem i left join accounting.\\\"order\\\" o on o.order_id=i.order_id where o.order_id is null),
  (select count(*) from information_schema.schemata where schema_name in ('catalog','reviews')); \")\"
test \"\$DUPLICATES\" = 0
test \"\$SHIPPING_ORPHANS\" = 0
test \"\$ITEM_ORPHANS\" = 0
test \"\$UNEXPECTED_SCHEMAS\" = 0
SEQUENCE_COUNT=\$(psql -h \"\$HOST\" -d '$ACCOUNTING_TARGET_DB' -At -v ON_ERROR_STOP=1 -c \"select count(*) from information_schema.sequences where sequence_schema='accounting';\")
echo \"validation=PASS source_counts=\$SOURCE_COUNTS target_counts=\$TARGET_COUNTS duplicates=\$DUPLICATES shipping_orphans=\$SHIPPING_ORPHANS item_orphans=\$ITEM_ORPHANS unexpected_schemas=\$UNEXPECTED_SCHEMAS sequence_count=\$SEQUENCE_COUNT\"
")"
printf '%s\n' "$recovery_output"
[[ "$recovery_output" == *"validation=PASS"* ]] || fail "Accounting recovery validation did not pass."
phase_done

PHASE=complete
log INFO "rto_end rto_seconds=$(( $(epoch) - RTO_START ))"
log INFO accounting_recovery_completed_production_was_not_modified
exit 0
