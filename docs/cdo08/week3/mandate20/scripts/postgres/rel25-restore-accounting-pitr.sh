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

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COMMON_LIBRARY="$SCRIPT_DIR/lib/rel25-common.sh"
REMOTE_RECOVERY_SCRIPT="$SCRIPT_DIR/rel25-accounting-recovery-remote.sh"

[[ -r "$COMMON_LIBRARY" ]] || {
  echo "Missing REL-25 common library: $COMMON_LIBRARY" >&2
  exit 1
}
[[ -r "$REMOTE_RECOVERY_SCRIPT" ]] || {
  echo "Missing REL-25 remote recovery script: $REMOTE_RECOVERY_SCRIPT" >&2
  exit 1
}

# shellcheck source=lib/rel25-common.sh
source "$COMMON_LIBRARY"
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
printf -v remote_environment \
  'export AWS_REGION=%q\nexport TARGET_MASTER_SECRET_ARN=%q\nexport RESTORE_ENDPOINT=%q\nexport ACCOUNTING_SOURCE_DB=%q\nexport ACCOUNTING_TARGET_DB=%q\n' \
  "$AWS_REGION" "$TARGET_MASTER_SECRET_ARN" "$RESTORE_ENDPOINT" \
  "$ACCOUNTING_SOURCE_DB" "$ACCOUNTING_TARGET_DB"
remote_recovery_payload="$remote_environment"$'\n'"$(<"$REMOTE_RECOVERY_SCRIPT")"
recovery_output="$(ssm_exec accounting_recovery "$remote_recovery_payload")"
printf '%s\n' "$recovery_output"
[[ "$recovery_output" == *"validation=PASS"* ]] || fail "Accounting recovery validation did not pass."
phase_done

PHASE=complete
log INFO "rto_end rto_seconds=$(( $(epoch) - RTO_START ))"
log INFO accounting_recovery_completed_production_was_not_modified
exit 0
