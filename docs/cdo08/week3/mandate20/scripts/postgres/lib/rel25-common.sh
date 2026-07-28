#!/usr/bin/env bash

# Shared runtime functions for rel25-restore-accounting-pitr.sh.
# The entry point defines configuration and resource-state globals before sourcing.

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
