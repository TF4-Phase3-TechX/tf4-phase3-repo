#!/usr/bin/env bash
set -Eeuo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_PROFILE="${AWS_PROFILE:-default}"
EXPECTED_AWS_ACCOUNT_ID="${EXPECTED_AWS_ACCOUNT_ID:-511825856493}"
SOURCE_DB_IDENTIFIER="${SOURCE_DB_IDENTIFIER:-techx-tf4-postgresql}"
DB_SUBNET_GROUP_NAME="${DB_SUBNET_GROUP_NAME:-techx-tf4-postgresql-private}"
APP_SECRET_ID="${APP_SECRET_ID:-techx/tf4/rds-postgres}"
REL26_DRILL_ID="${REL26_DRILL_ID:-rel26-$(date -u +"%Y%m%d")}"
SOURCE_RESTORE_TIMESTAMP="${SOURCE_RESTORE_TIMESTAMP:-}"
TEMP_SOURCE_IDENTIFIER="${TEMP_SOURCE_IDENTIFIER:-techx-tf4-drill-${REL26_DRILL_ID}-accounting-source}"
DRILL_TARGET_IDENTIFIER="${DRILL_TARGET_IDENTIFIER:-techx-tf4-drill-${REL26_DRILL_ID}-accounting-restore}"
RESTORE_INSTANCE_CLASS="${RESTORE_INSTANCE_CLASS:-}"
VALIDATION_INSTANCE_TYPE="${VALIDATION_INSTANCE_TYPE:-t3.nano}"
VALIDATION_ROLE_NAME="${VALIDATION_ROLE_NAME:-techx-tf4-rel26-validation}"
VALIDATION_PROFILE_NAME="${VALIDATION_PROFILE_NAME:-techx-tf4-rel26-validation}"
ACCOUNTING_DB="${ACCOUNTING_DB:-otel}"
PREFLIGHT_ONLY="${PREFLIGHT_ONLY:-false}"
CONFIRM_REL26_DRILL="${CONFIRM_REL26_DRILL:-}"
AUTO_CLEANUP="${AUTO_CLEANUP:-true}"
WAIT_TIMEOUT_SECONDS="${WAIT_TIMEOUT_SECONDS:-5400}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-30}"
TTL_HOURS="${TTL_HOURS:-6}"
MARKER_SETTLE_SECONDS="${MARKER_SETTLE_SECONDS:-90}"
MARKER_ORDER_ID="${MARKER_ORDER_ID:-${REL26_DRILL_ID}-controlled-delete-order}"
MARKER_SHIPPING_ID="${MARKER_SHIPPING_ID:-${REL26_DRILL_ID}-controlled-delete-shipping}"
MARKER_PRODUCT_ID="${MARKER_PRODUCT_ID:-${REL26_DRILL_ID}-controlled-delete-product}"
EXECUTION_LOG="${EXECUTION_LOG:-${REL26_DRILL_ID}-execution.log}"
export AWS_PAGER=""

PHASE="initialization"
PHASE_START=0
DRILL_SETUP_START=0
DRILL_SETUP_END=0
RECOVERY_RTO_START=0
RECOVERY_RTO_END=0
TEMP_SOURCE_CREATED=false
DRILL_TARGET_CREATED=false
INSTANCE_CREATED=false
VALIDATION_SG_CREATED=false
RDS_SG_CREATED=false
ROLE_CREATED=false
PROFILE_CREATED=false
VALIDATION_INSTANCE_ID=""
VALIDATION_SECURITY_GROUP_ID=""
RDS_SECURITY_GROUP_ID=""
TEMP_SOURCE_ENDPOINT=""
DRILL_TARGET_ENDPOINT=""
SOURCE_MASTER_SECRET_ARN=""
TEMP_MASTER_SECRET_ARN=""
DRILL_MASTER_SECRET_ARN=""
APP_SECRET_ARN=""
DRILL_RESTORE_TIME=""
CLEANUP_FAILED=false
LOG_TO_FILE=false

now() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
epoch() { date +%s; }
parse_utc_epoch() {
  local value="$1"
  local normalized="${value%%.*}"
  normalized="${normalized%+00:00}Z"
  normalized="${normalized%Z}Z"
  date -u -d "$value" +%s 2>/dev/null ||
    date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$normalized" +%s 2>/dev/null
}
format_utc_epoch() {
  local value="$1"
  date -u -d "@$value" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null ||
    date -u -r "$value" +"%Y-%m-%dT%H:%M:%SZ"
}
utc_after_hours() {
  local hours="$1"
  date -u -d "+${hours} hours" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null ||
    date -u -v+"${hours}"H +"%Y-%m-%dT%H:%M:%SZ"
}
log() {
  local line
  printf -v line '%s | %-5s | %-32s | %s' "$(now)" "$1" "$PHASE" "$2"
  printf '%s\n' "$line"
  if [[ "$LOG_TO_FILE" == true ]]; then
    printf '%s\n' "$line" >>"$EXECUTION_LOG"
  fi
}
stage_banner() {
  printf '\n=== REL-26 stage: %s ===\n' "$1"
  printf '    %s\n\n' "$2"
  if [[ "$LOG_TO_FILE" == true ]]; then
    {
      printf '\n=== REL-26 stage: %s ===\n' "$1"
      printf '    %s\n\n' "$2"
    } >>"$EXECUTION_LOG"
  fi
}
fail() { log ERROR "$1" >&2; exit 1; }
need() { [[ -n "${!1:-}" ]] || fail "Set $1 before running."; }
phase() {
  PHASE="$1"
  PHASE_START="$(epoch)"
  case "$1" in
    environment_preflight)
      stage_banner "$1" "Check AWS account, production RDS, PITR window, naming guardrails, and target absence."
      ;;
    create_validation_identity)
      stage_banner "$1" "Create temporary IAM role/profile for private EC2 validation."
      ;;
    create_isolated_network)
      stage_banner "$1" "Create temporary security groups for private validation and temporary RDS instances."
      ;;
    create_validation_ec2)
      stage_banner "$1" "Launch private validation EC2 and verify SSM, AWS CLI, jq, and PostgreSQL tools."
      ;;
    create_temp_source_from_prod)
      stage_banner "$1" "Create a temporary RDS source from production PITR. Production is not modified."
      ;;
    seed_marker_dataset)
      stage_banner "$1" "Insert controlled marker rows into the temporary source and print their exact values."
      ;;
    wait_marker_recoverable)
      stage_banner "$1" "Wait until the temporary source PITR window can restore to a point after marker insert."
      ;;
    controlled_delete)
      stage_banner "$1" "Delete the marker from the temporary source and print before/after proof."
      ;;
    create_drill_restore_from_temp)
      stage_banner "$1" "Create a second RDS drill target from the temporary source PITR before the deletion."
      ;;
    verify_drill_contains_marker)
      stage_banner "$1" "Verify the drill restore contains the marker data that was deleted from the temporary source."
      ;;
    restore_marker_to_temp_source)
      stage_banner "$1" "Restore accounting schema from drill target back into the temporary source."
      ;;
    final_validation)
      stage_banner "$1" "Verify the deleted marker exists again in the temporary source after restore."
      ;;
    cleanup)
      stage_banner "$1" "Delete temporary RDS, EC2, SG, IAM role/profile created by the drill."
      ;;
    *)
      stage_banner "$1" "Running REL-26 step."
      ;;
  esac
  log INFO phase_start
}
phase_done() { log INFO "phase_end duration_seconds=$(( $(epoch) - PHASE_START ))"; }
aws_cli() { aws --profile "$AWS_PROFILE" --region "$AWS_REGION" "$@"; }
resource_exists() { [[ "$1" == true ]]; }

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
  local identifier="$1"
  local deadline=$(( $(epoch) + WAIT_TIMEOUT_SECONDS ))
  while (( $(epoch) < deadline )); do
    if ! aws_cli rds describe-db-instances \
      --db-instance-identifier "$identifier" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$POLL_INTERVAL_SECONDS"
  done
  return 1
}

wait_for_temp_pitr_after() {
  local min_epoch="$1"
  local deadline=$(( $(epoch) + WAIT_TIMEOUT_SECONDS ))
  local earliest latest latest_epoch
  while (( $(epoch) < deadline )); do
    if read -r earliest latest <<<"$(aws_cli rds describe-db-instance-automated-backups \
      --db-instance-identifier "$TEMP_SOURCE_IDENTIFIER" \
      --query 'DBInstanceAutomatedBackups[0].RestoreWindow.[EarliestTime,LatestTime]' \
      --output text 2>/dev/null)"; then
      latest_epoch="$(parse_utc_epoch "$latest" 2>/dev/null || true)"
      log INFO "temp_source=$TEMP_SOURCE_IDENTIFIER pitr_latest=${latest:-none} required=$(format_utc_epoch "$min_epoch")"
      [[ -n "$latest_epoch" ]] && (( latest_epoch >= min_epoch )) && return 0
    else
      log INFO "temp_source=$TEMP_SOURCE_IDENTIFIER pitr_window=not-ready"
    fi
    sleep "$POLL_INTERVAL_SECONDS"
  done
  fail "Timed out waiting for temporary source PITR to cover marker restore time."
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

update_validation_secret_policy() {
  local resources_json=""
  local arn
  for arn in "$@"; do
    [[ -n "$arn" && "$arn" != None ]] || continue
    resources_json="${resources_json:+$resources_json,}\"$arn\""
  done
  [[ -n "$resources_json" ]] || fail "No Secrets Manager ARNs available for validation role."
  local policy
  policy="{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadOnlyRDSApplicationCredentials\",\"Effect\":\"Allow\",\"Action\":[\"secretsmanager:DescribeSecret\",\"secretsmanager:GetSecretValue\"],\"Resource\":[$resources_json]}]}"
  aws iam put-role-policy --profile "$AWS_PROFILE" \
    --role-name "$VALIDATION_ROLE_NAME" \
    --policy-name REL26RDSAppSecretRead \
    --policy-document "$policy"
  log INFO "validation_secret_policy_updated resources=[$resources_json]"
}

ssm_exec() {
  local label="$1"
  local script="$2"
  local encoded parameters command_id deadline status output
  encoded="$(printf '%s' "$script" | base64 | tr -d '\r\n')"
  parameters="{\"commands\":[\"printf '%s' '$encoded' | base64 -d >/tmp/rel26-command.sh && chmod 700 /tmp/rel26-command.sh && /tmp/rel26-command.sh\"]}"
  command_id="$(aws_cli ssm send-command \
    --instance-ids "$VALIDATION_INSTANCE_ID" \
    --document-name AWS-RunShellScript \
    --comment "REL-26 $label" \
    --parameters "$parameters" \
    --query 'Command.CommandId' --output text)"
  log INFO "ssm_command=$label command_id=$command_id"

  deadline=$(( $(epoch) + 1200 ))
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
  phase cleanup
  log INFO "cleanup_start original_exit_code=$original_code"

  if resource_exists "$DRILL_TARGET_CREATED"; then
    if aws_cli rds delete-db-instance \
      --db-instance-identifier "$DRILL_TARGET_IDENTIFIER" \
      --skip-final-snapshot --delete-automated-backups >/dev/null 2>&1 &&
      wait_for_rds_deleted "$DRILL_TARGET_IDENTIFIER"; then
      DRILL_TARGET_CREATED=false
      log INFO "cleanup_deleted_rds=$DRILL_TARGET_IDENTIFIER"
    else
      CLEANUP_FAILED=true
      log ERROR "cleanup_remaining_rds=$DRILL_TARGET_IDENTIFIER"
    fi
  fi

  if resource_exists "$TEMP_SOURCE_CREATED"; then
    if aws_cli rds delete-db-instance \
      --db-instance-identifier "$TEMP_SOURCE_IDENTIFIER" \
      --skip-final-snapshot --delete-automated-backups >/dev/null 2>&1 &&
      wait_for_rds_deleted "$TEMP_SOURCE_IDENTIFIER"; then
      TEMP_SOURCE_CREATED=false
      log INFO "cleanup_deleted_rds=$TEMP_SOURCE_IDENTIFIER"
    else
      CLEANUP_FAILED=true
      log ERROR "cleanup_remaining_rds=$TEMP_SOURCE_IDENTIFIER"
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

  if resource_exists "$RDS_SG_CREATED" && resource_exists "$VALIDATION_SG_CREATED"; then
    aws_cli ec2 revoke-security-group-ingress \
      --group-id "$RDS_SECURITY_GROUP_ID" \
      --ip-permissions \
        "IpProtocol=tcp,FromPort=5432,ToPort=5432,UserIdGroupPairs=[{GroupId=$VALIDATION_SECURITY_GROUP_ID}]" \
      >/dev/null 2>&1 || true
    aws_cli ec2 revoke-security-group-egress \
      --group-id "$VALIDATION_SECURITY_GROUP_ID" \
      --ip-permissions \
        "IpProtocol=tcp,FromPort=5432,ToPort=5432,UserIdGroupPairs=[{GroupId=$RDS_SECURITY_GROUP_ID}]" \
      >/dev/null 2>&1 || true
  fi

  if resource_exists "$RDS_SG_CREATED"; then
    if delete_security_group "$RDS_SECURITY_GROUP_ID"; then
      RDS_SG_CREATED=false
      log INFO "cleanup_deleted_sg=$RDS_SECURITY_GROUP_ID"
    else
      CLEANUP_FAILED=true
      log ERROR "cleanup_remaining_sg=$RDS_SECURITY_GROUP_ID"
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
      --policy-name REL26RDSAppSecretRead >/dev/null 2>&1 || true
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
    log WARN "auto_cleanup_disabled temp_source=$TEMP_SOURCE_IDENTIFIER drill_target=$DRILL_TARGET_IDENTIFIER ec2=$VALIDATION_INSTANCE_ID validation_sg=$VALIDATION_SECURITY_GROUP_ID rds_sg=$RDS_SECURITY_GROUP_ID role=$VALIDATION_ROLE_NAME profile=$VALIDATION_PROFILE_NAME"
  fi
  exit "$code"
}

remote_action_script() {
  cat <<'REMOTE_ACTION_SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

for variable in AWS_REGION TARGET_APP_SECRET_ID REL26_REMOTE_ACTION ACCOUNTING_DB MARKER_ORDER_ID MARKER_SHIPPING_ID MARKER_PRODUCT_ID; do
  [[ -n "${!variable:-}" ]] || {
    echo "Missing remote variable $variable" >&2
    exit 1
  }
done

umask 077
RESTORE_SQL=/tmp/rel26-accounting-marker-restore.sql
trap 'rm -f "$RESTORE_SQL"' EXIT

SECRET_JSON="$(aws secretsmanager get-secret-value \
  --region "$AWS_REGION" \
  --secret-id "$TARGET_APP_SECRET_ID" \
  --query SecretString --output text)"
PGUSER="$(printf '%s' "$SECRET_JSON" | jq -r .username)"
PGPASSWORD="$(printf '%s' "$SECRET_JSON" | jq -r .password)"
secret_dbname="$(printf '%s' "$SECRET_JSON" | jq -r '.dbname // empty')"
if [[ -n "$secret_dbname" ]]; then
  ACCOUNTING_DB="$secret_dbname"
fi
export PGUSER PGPASSWORD PGSSLMODE=require
unset SECRET_JSON secret_dbname

print_marker_rows() {
  local endpoint="$1"
  psql -h "$endpoint" -d "$ACCOUNTING_DB" \
    -v ON_ERROR_STOP=1 \
    -v order_id="$MARKER_ORDER_ID" \
    -v shipping_id="$MARKER_SHIPPING_ID" \
    -v product_id="$MARKER_PRODUCT_ID" <<'SQL'
\pset pager off
\pset border 0
\pset tuples_only on
\pset format unaligned
select E'\n--- marker_order ---\n' || jsonb_pretty(to_jsonb(o))
from accounting."order" o
where o.order_id = :'order_id';

select E'\n--- marker_shipping ---\n' || jsonb_pretty(to_jsonb(s))
from accounting.shipping s
where s.shipping_tracking_id = :'shipping_id';

select E'\n--- marker_orderitem ---\n' || jsonb_pretty(to_jsonb(i))
from accounting.orderitem i
where i.order_id = :'order_id' and i.product_id = :'product_id';
SQL
}

assert_marker_count() {
  local endpoint="$1"
  local expected="$2"
  local count
  count="$(psql -h "$endpoint" -d "$ACCOUNTING_DB" -At \
    -v ON_ERROR_STOP=1 \
    -v order_id="$MARKER_ORDER_ID" <<'SQL'
select count(*)
from accounting."order"
where order_id = :'order_id';
SQL
)"
  echo "marker_count endpoint=$endpoint expected=$expected actual=$count"
  test "$count" = "$expected"
}

case "$REL26_REMOTE_ACTION" in
  seed_marker)
    : "${TEMP_SOURCE_ENDPOINT:?Missing TEMP_SOURCE_ENDPOINT}"
    echo "remote_stage=seed_marker endpoint=$TEMP_SOURCE_ENDPOINT"
    psql -h "$TEMP_SOURCE_ENDPOINT" -d "$ACCOUNTING_DB" -v ON_ERROR_STOP=1 \
      -v order_id="$MARKER_ORDER_ID" \
      -v shipping_id="$MARKER_SHIPPING_ID" \
      -v product_id="$MARKER_PRODUCT_ID" <<'SQL'
begin;
delete from accounting."order" where order_id = :'order_id';
insert into accounting."order"(order_id) values (:'order_id');
insert into accounting.shipping(
  shipping_tracking_id,
  shipping_cost_currency_code,
  shipping_cost_units,
  shipping_cost_nanos,
  street_address,
  city,
  state,
  country,
  zip_code,
  order_id
) values (
  :'shipping_id',
  'USD',
  12,
  340000000,
  'REL26 controlled delete drill',
  'Ho Chi Minh City',
  'SG',
  'VN',
  '700000',
  :'order_id'
);
insert into accounting.orderitem(
  item_cost_currency_code,
  item_cost_units,
  item_cost_nanos,
  product_id,
  quantity,
  order_id
) values (
  'USD',
  99,
  990000000,
  :'product_id',
  2,
  :'order_id'
);
commit;
SQL
    echo "marker_values_after_insert"
    print_marker_rows "$TEMP_SOURCE_ENDPOINT"
    assert_marker_count "$TEMP_SOURCE_ENDPOINT" 1
    echo "seed_marker=PASS order_id=$MARKER_ORDER_ID shipping_id=$MARKER_SHIPPING_ID product_id=$MARKER_PRODUCT_ID"
    ;;

  delete_marker)
    : "${TEMP_SOURCE_ENDPOINT:?Missing TEMP_SOURCE_ENDPOINT}"
    echo "remote_stage=delete_marker endpoint=$TEMP_SOURCE_ENDPOINT"
    echo "marker_values_before_delete"
    print_marker_rows "$TEMP_SOURCE_ENDPOINT"
    psql -h "$TEMP_SOURCE_ENDPOINT" -d "$ACCOUNTING_DB" -v ON_ERROR_STOP=1 \
      -v order_id="$MARKER_ORDER_ID" -At <<'SQL'
delete from accounting."order"
where order_id = :'order_id'
returning order_id;
SQL
    assert_marker_count "$TEMP_SOURCE_ENDPOINT" 0
    echo "controlled_delete=PASS deleted_order_id=$MARKER_ORDER_ID cascade_removed_shipping_and_items=true"
    ;;

  verify_drill_marker)
    : "${DRILL_TARGET_ENDPOINT:?Missing DRILL_TARGET_ENDPOINT}"
    echo "remote_stage=verify_drill_marker endpoint=$DRILL_TARGET_ENDPOINT"
    echo "marker_values_on_drill_restore"
    print_marker_rows "$DRILL_TARGET_ENDPOINT"
    assert_marker_count "$DRILL_TARGET_ENDPOINT" 1
    echo "verify_drill_marker=PASS"
    ;;

  restore_schema_to_temp)
    : "${TEMP_SOURCE_ENDPOINT:?Missing TEMP_SOURCE_ENDPOINT}"
    : "${DRILL_TARGET_ENDPOINT:?Missing DRILL_TARGET_ENDPOINT}"
    echo "remote_stage=build_marker_row_restore_sql_from_drill"
    {
      echo "begin;"
      echo "delete from accounting.\"order\" where order_id = '$MARKER_ORDER_ID';"
      psql -h "$DRILL_TARGET_ENDPOINT" -d "$ACCOUNTING_DB" -At \
        -v ON_ERROR_STOP=1 \
        -v order_id="$MARKER_ORDER_ID" \
        -v shipping_id="$MARKER_SHIPPING_ID" \
        -v product_id="$MARKER_PRODUCT_ID" <<'SQL'
select format(
  'insert into accounting."order"(order_id) values (%L);',
  o.order_id
)
from accounting."order" o
where o.order_id = :'order_id';

select format(
  'insert into accounting.shipping(shipping_tracking_id, shipping_cost_currency_code, shipping_cost_units, shipping_cost_nanos, street_address, city, state, country, zip_code, order_id) values (%L, %L, %s, %s, %L, %L, %L, %L, %L, %L);',
  s.shipping_tracking_id,
  s.shipping_cost_currency_code,
  s.shipping_cost_units,
  s.shipping_cost_nanos,
  s.street_address,
  s.city,
  s.state,
  s.country,
  s.zip_code,
  s.order_id
)
from accounting.shipping s
where s.shipping_tracking_id = :'shipping_id';

select format(
  'insert into accounting.orderitem(item_cost_currency_code, item_cost_units, item_cost_nanos, product_id, quantity, order_id) values (%L, %s, %s, %L, %s, %L);',
  i.item_cost_currency_code,
  i.item_cost_units,
  i.item_cost_nanos,
  i.product_id,
  i.quantity,
  i.order_id
)
from accounting.orderitem i
where i.order_id = :'order_id' and i.product_id = :'product_id';
SQL
      echo "commit;"
    } >"$RESTORE_SQL"
    test -s "$RESTORE_SQL"
    echo "marker_restore_sql_preview"
    sed 's/Password=[^;]*/Password=***REDACTED***/g' "$RESTORE_SQL"
    echo "remote_stage=restore_marker_rows_to_temp_source"
    psql -h "$TEMP_SOURCE_ENDPOINT" -d "$ACCOUNTING_DB" \
      -v ON_ERROR_STOP=1 -f "$RESTORE_SQL"
    echo "restore_schema_to_temp=PASS restored_marker_rows_only=true"
    ;;

  verify_temp_marker_restored)
    : "${TEMP_SOURCE_ENDPOINT:?Missing TEMP_SOURCE_ENDPOINT}"
    echo "remote_stage=verify_temp_marker_restored endpoint=$TEMP_SOURCE_ENDPOINT"
    echo "marker_values_after_restore_to_temp"
    print_marker_rows "$TEMP_SOURCE_ENDPOINT"
    assert_marker_count "$TEMP_SOURCE_ENDPOINT" 1
    echo "final_validation=PASS marker_restored_to_temp_source=true"
    ;;

  *)
    echo "Unknown REL26_REMOTE_ACTION=$REL26_REMOTE_ACTION" >&2
    exit 1
    ;;
esac
REMOTE_ACTION_SCRIPT
}

run_remote_action() {
  local action="$1"
  local env_block
  printf -v env_block \
    'export AWS_REGION=%q\nexport TARGET_APP_SECRET_ID=%q\nexport REL26_REMOTE_ACTION=%q\nexport ACCOUNTING_DB=%q\nexport TEMP_SOURCE_ENDPOINT=%q\nexport DRILL_TARGET_ENDPOINT=%q\nexport MARKER_ORDER_ID=%q\nexport MARKER_SHIPPING_ID=%q\nexport MARKER_PRODUCT_ID=%q\n' \
    "$AWS_REGION" "$APP_SECRET_ID" "$action" "$ACCOUNTING_DB" \
    "$TEMP_SOURCE_ENDPOINT" "$DRILL_TARGET_ENDPOINT" \
    "$MARKER_ORDER_ID" "$MARKER_SHIPPING_ID" "$MARKER_PRODUCT_ID"
  ssm_exec "$action" "$env_block"$'\n'"$(remote_action_script)"
}

trap on_exit EXIT

for command in aws base64 date tee tr; do
  command -v "$command" >/dev/null 2>&1 || fail "Missing command $command."
done
for variable in AWS_PROFILE EXPECTED_AWS_ACCOUNT_ID REL26_DRILL_ID; do
  need "$variable"
done
for number in WAIT_TIMEOUT_SECONDS POLL_INTERVAL_SECONDS TTL_HOURS MARKER_SETTLE_SECONDS; do
  [[ "${!number}" =~ ^[1-9][0-9]*$ ]] || fail "$number must be a positive integer."
done
[[ "$PREFLIGHT_ONLY" == true || "$PREFLIGHT_ONLY" == false ]] || fail "PREFLIGHT_ONLY must be true or false."
[[ "$AUTO_CLEANUP" == true || "$AUTO_CLEANUP" == false ]] || fail "AUTO_CLEANUP must be true or false."
[[ "$REL26_DRILL_ID" =~ ^rel26-[0-9]{8}(-[a-z0-9-]+)?$ ]] || fail "REL26_DRILL_ID must start with rel26-YYYYMMDD."
[[ "$TEMP_SOURCE_IDENTIFIER" == "techx-tf4-drill-${REL26_DRILL_ID}-accounting-source" ]] || fail "TEMP_SOURCE_IDENTIFIER violates naming contract."
[[ "$DRILL_TARGET_IDENTIFIER" == "techx-tf4-drill-${REL26_DRILL_ID}-accounting-restore" ]] || fail "DRILL_TARGET_IDENTIFIER violates naming contract."
[[ "$TEMP_SOURCE_IDENTIFIER" != "$SOURCE_DB_IDENTIFIER" ]] || fail "Temp source equals production source."
[[ "$DRILL_TARGET_IDENTIFIER" != "$SOURCE_DB_IDENTIFIER" ]] || fail "Drill target equals production source."
[[ "$TEMP_SOURCE_IDENTIFIER" != "$DRILL_TARGET_IDENTIFIER" ]] || fail "Temp source equals drill target."
[[ "$VALIDATION_ROLE_NAME" == techx-tf4-rel26-validation ]] || fail "Unexpected validation role name."
[[ "$VALIDATION_PROFILE_NAME" == techx-tf4-rel26-validation ]] || fail "Unexpected validation profile name."

if [[ -z "$SOURCE_RESTORE_TIMESTAMP" ]]; then
  SOURCE_RESTORE_TIMESTAMP="$(format_utc_epoch "$(( $(epoch) - 1800 ))")"
fi
source_restore_epoch="$(parse_utc_epoch "$SOURCE_RESTORE_TIMESTAMP")" || fail "SOURCE_RESTORE_TIMESTAMP is not valid."
source_restore_time="$(format_utc_epoch "$source_restore_epoch")"

mkdir -p "$(dirname "$EXECUTION_LOG")"
touch "$EXECUTION_LOG"
LOG_TO_FILE=true
log INFO "execution_log=$EXECUTION_LOG"

phase environment_preflight
account_id="$(aws --profile "$AWS_PROFILE" sts get-caller-identity --query Account --output text)"
[[ "$account_id" == "$EXPECTED_AWS_ACCOUNT_ID" ]] || fail "AWS account does not match EXPECTED_AWS_ACCOUNT_ID."

read -r source_status source_class source_vpc source_endpoint source_public source_subnet SOURCE_MASTER_SECRET_ARN <<<"$(aws_cli rds describe-db-instances \
  --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --query 'DBInstances[0].[DBInstanceStatus,DBInstanceClass,DBSubnetGroup.VpcId,Endpoint.Address,PubliclyAccessible,DBSubnetGroup.DBSubnetGroupName,MasterUserSecret.SecretArn]' \
  --output text)"
[[ "$source_status" == available ]] || fail "Production source RDS is not available."
[[ "$source_public" == False ]] || fail "Production source is unexpectedly public."
[[ "$source_subnet" == "$DB_SUBNET_GROUP_NAME" ]] || fail "Unexpected DB subnet group."
[[ "$SOURCE_MASTER_SECRET_ARN" == arn:aws:secretsmanager:*:*:secret:rds\!db-* ]] || fail "Production source has no RDS-managed master secret."
RESTORE_INSTANCE_CLASS="${RESTORE_INSTANCE_CLASS:-$source_class}"
APP_SECRET_ARN="$(aws_cli secretsmanager describe-secret \
  --secret-id "$APP_SECRET_ID" \
  --query ARN --output text)"
aws_cli secretsmanager get-secret-value \
  --secret-id "$APP_SECRET_ID" \
  --query SecretString --output text >/dev/null

read -r earliest latest <<<"$(aws_cli rds describe-db-instance-automated-backups \
  --db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --query 'DBInstanceAutomatedBackups[0].RestoreWindow.[EarliestTime,LatestTime]' \
  --output text)"
earliest_epoch="$(parse_utc_epoch "$earliest")"
latest_epoch="$(parse_utc_epoch "$latest")"
(( source_restore_epoch >= earliest_epoch && source_restore_epoch <= latest_epoch )) || fail "SOURCE_RESTORE_TIMESTAMP is outside production PITR window $earliest to $latest."

for identifier in "$TEMP_SOURCE_IDENTIFIER" "$DRILL_TARGET_IDENTIFIER"; do
  target_check=""
  if target_check="$(aws_cli rds describe-db-instances --db-instance-identifier "$identifier" 2>&1)"; then
    fail "RDS target already exists: $identifier"
  fi
  [[ "$target_check" == *DBInstanceNotFound* ]] || fail "Could not verify target absence: $identifier"
done

vpc_cidr="$(aws_cli ec2 describe-vpcs --vpc-ids "$source_vpc" --query 'Vpcs[0].CidrBlock' --output text)"
validation_subnet="$(aws_cli rds describe-db-subnet-groups \
  --db-subnet-group-name "$DB_SUBNET_GROUP_NAME" \
  --query 'DBSubnetGroups[0].Subnets[0].SubnetIdentifier' --output text)"
map_public_ip="$(aws_cli ec2 describe-subnets --subnet-ids "$validation_subnet" \
  --query 'Subnets[0].MapPublicIpOnLaunch' --output text)"
[[ "$map_public_ip" == False ]] || fail "Validation subnet maps public IPs."

log INFO "preflight_passed prod=$SOURCE_DB_IDENTIFIER temp_source=$TEMP_SOURCE_IDENTIFIER drill_target=$DRILL_TARGET_IDENTIFIER source_restore_time=$source_restore_time app_secret=$APP_SECRET_ID marker_order_id=$MARKER_ORDER_ID"
phase_done

if [[ "$PREFLIGHT_ONLY" == true ]]; then
  PHASE=complete
  log INFO preflight_only_passed_no_resources_created
  exit 0
fi
[[ "$CONFIRM_REL26_DRILL" == YES ]] || fail "Set CONFIRM_REL26_DRILL=YES."

cleanup_after="$(utc_after_hours "$TTL_HOURS")"
common_tags=(
  Key=Owner,Value=CDO08
  Key=Environment,Value=RestoreDrill
  Key=Mandate,Value=20
  Key=Task,Value=CDO08-REL-26
  Key=RestoreDrillId,Value="$REL26_DRILL_ID"
  Key=TTLHours,Value="$TTL_HOURS"
  Key=CleanupAfter,Value="$cleanup_after"
  Key=CostCenter,Value=ReliabilityDrill
  Key=Production,Value=false
)

phase create_validation_identity
if aws iam get-role --profile "$AWS_PROFILE" --role-name "$VALIDATION_ROLE_NAME" >/dev/null 2>&1; then
  fail "Validation IAM role already exists; cleanup or review it before running."
fi
trust_policy='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam create-role --profile "$AWS_PROFILE" \
  --role-name "$VALIDATION_ROLE_NAME" \
  --assume-role-policy-document "$trust_policy" \
  --tags Key=Owner,Value=CDO08 Key=Environment,Value=RestoreDrill Key=RestoreDrillId,Value="$REL26_DRILL_ID" Key=Production,Value=false >/dev/null
ROLE_CREATED=true
aws iam attach-role-policy --profile "$AWS_PROFILE" \
  --role-name "$VALIDATION_ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
update_validation_secret_policy "$APP_SECRET_ARN"
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
  --group-name "techx-tf4-${REL26_DRILL_ID}-validation" \
  --description "REL-26 temporary private EC2 validation client" \
  --vpc-id "$source_vpc" --query GroupId --output text)"
VALIDATION_SG_CREATED=true
aws_cli ec2 create-tags --resources "$VALIDATION_SECURITY_GROUP_ID" \
  --tags "${common_tags[@]}" Key=Purpose,Value=RestoreValidationClient Key=Name,Value="techx-tf4-${REL26_DRILL_ID}-validation"

RDS_SECURITY_GROUP_ID="$(aws_cli ec2 create-security-group \
  --group-name "techx-tf4-${REL26_DRILL_ID}-rds" \
  --description "REL-26 temporary RDS source and drill target" \
  --vpc-id "$source_vpc" --query GroupId --output text)"
RDS_SG_CREATED=true
aws_cli ec2 create-tags --resources "$RDS_SECURITY_GROUP_ID" \
  --tags "${common_tags[@]}" Key=Purpose,Value=RestoreTarget Key=Name,Value="techx-tf4-${REL26_DRILL_ID}-rds"

aws_cli ec2 revoke-security-group-egress --group-id "$VALIDATION_SECURITY_GROUP_ID" \
  --ip-permissions '[{"IpProtocol":"-1","IpRanges":[{"CidrIp":"0.0.0.0/0"}]}]' >/dev/null
aws_cli ec2 revoke-security-group-egress --group-id "$RDS_SECURITY_GROUP_ID" \
  --ip-permissions '[{"IpProtocol":"-1","IpRanges":[{"CidrIp":"0.0.0.0/0"}]}]' >/dev/null
aws_cli ec2 authorize-security-group-egress --group-id "$VALIDATION_SECURITY_GROUP_ID" \
  --ip-permissions \
    "IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=0.0.0.0/0,Description=AWS-SSM-and-package-repositories}]" \
    "IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=0.0.0.0/0,Description=Package-bootstrap-only}]" \
    "IpProtocol=udp,FromPort=53,ToPort=53,IpRanges=[{CidrIp=$vpc_cidr,Description=VPC-DNS}]" \
    "IpProtocol=tcp,FromPort=53,ToPort=53,IpRanges=[{CidrIp=$vpc_cidr,Description=VPC-DNS}]" >/dev/null
aws_cli ec2 authorize-security-group-egress --group-id "$VALIDATION_SECURITY_GROUP_ID" \
  --ip-permissions "IpProtocol=tcp,FromPort=5432,ToPort=5432,UserIdGroupPairs=[{GroupId=$RDS_SECURITY_GROUP_ID,Description=REL26-RDS-only}]" >/dev/null
aws_cli ec2 authorize-security-group-ingress --group-id "$RDS_SECURITY_GROUP_ID" \
  --ip-permissions "IpProtocol=tcp,FromPort=5432,ToPort=5432,UserIdGroupPairs=[{GroupId=$VALIDATION_SECURITY_GROUP_ID,Description=REL26-validation-only}]" >/dev/null
log INFO "created_validation_sg=$VALIDATION_SECURITY_GROUP_ID created_rds_sg=$RDS_SECURITY_GROUP_ID"
phase_done

phase create_validation_ec2
ami_id="$(aws_cli ssm get-parameter \
  --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query Parameter.Value --output text)"
user_data='#!/bin/bash
set -euo pipefail
dnf install -y jq postgresql17
systemctl enable --now amazon-ssm-agent
touch /var/lib/rel26-bootstrap-complete
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
    "ResourceType=instance,Tags=[{Key=Name,Value=techx-tf4-${REL26_DRILL_ID}-validation},{Key=Owner,Value=CDO08},{Key=Environment,Value=RestoreDrill},{Key=RestoreDrillId,Value=${REL26_DRILL_ID}},{Key=TTLHours,Value=${TTL_HOURS}},{Key=CleanupAfter,Value=${cleanup_after}},{Key=Production,Value=false}]" \
    "ResourceType=volume,Tags=[{Key=Name,Value=techx-tf4-${REL26_DRILL_ID}-validation},{Key=Owner,Value=CDO08},{Key=Environment,Value=RestoreDrill},{Key=RestoreDrillId,Value=${REL26_DRILL_ID}},{Key=CleanupAfter,Value=${cleanup_after}},{Key=Production,Value=false}]" \
  --query 'Instances[0].InstanceId' --output text)"
INSTANCE_CREATED=true
aws_cli ec2 wait instance-running --instance-ids "$VALIDATION_INSTANCE_ID"
read -r public_ip attached_sgs <<<"$(aws_cli ec2 describe-instances \
  --instance-ids "$VALIDATION_INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].[PublicIpAddress,SecurityGroups[*].GroupId|join(`,`,@)]' --output text)"
[[ "$public_ip" == None ]] || fail "Validation EC2 unexpectedly has a public IP."
[[ "$attached_sgs" == "$VALIDATION_SECURITY_GROUP_ID" ]] || fail "Validation EC2 has an unexpected SG."
wait_for_ssm_online
ssm_exec bootstrap_check 'set -euo pipefail
deadline=$(( $(date +%s) + 600 ))
while [[ ! -f /var/lib/rel26-bootstrap-complete ]] && (( $(date +%s) < deadline )); do sleep 10; done
test -f /var/lib/rel26-bootstrap-complete
command -v aws >/dev/null
command -v jq >/dev/null
command -v pg_isready >/dev/null
command -v pg_dump >/dev/null
command -v pg_restore >/dev/null
command -v psql >/dev/null
echo bootstrap_check=PASS' >/dev/null
log INFO "created_validation_ec2=$VALIDATION_INSTANCE_ID public_ip=none ssm=Online"
phase_done

DRILL_SETUP_START="$(epoch)"
log INFO "drill_setup_start source_restore_time=$source_restore_time"

phase create_temp_source_from_prod
aws_cli rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier "$SOURCE_DB_IDENTIFIER" \
  --target-db-instance-identifier "$TEMP_SOURCE_IDENTIFIER" \
  --restore-time "$source_restore_time" \
  --db-instance-class "$RESTORE_INSTANCE_CLASS" \
  --db-subnet-group-name "$DB_SUBNET_GROUP_NAME" \
  --vpc-security-group-ids "$RDS_SECURITY_GROUP_ID" \
  --no-publicly-accessible --no-multi-az --copy-tags-to-snapshot \
  --tags "${common_tags[@]}" Key=Purpose,Value=REL26TemporarySource >/dev/null
TEMP_SOURCE_CREATED=true
wait_for_rds_status "$TEMP_SOURCE_IDENTIFIER" available
read -r temp_status TEMP_SOURCE_ENDPOINT temp_public temp_sgs TEMP_MASTER_SECRET_ARN <<<"$(aws_cli rds describe-db-instances \
  --db-instance-identifier "$TEMP_SOURCE_IDENTIFIER" \
  --query 'DBInstances[0].[DBInstanceStatus,Endpoint.Address,PubliclyAccessible,VpcSecurityGroups[*].VpcSecurityGroupId|join(`,`,@),MasterUserSecret.SecretArn]' \
  --output text)"
[[ "$temp_status" == available ]] || fail "Temp source is not available."
[[ "$temp_public" == False ]] || fail "Temp source is public."
[[ "$temp_sgs" == "$RDS_SECURITY_GROUP_ID" ]] || fail "Temp source uses unexpected SG."
[[ "$TEMP_SOURCE_ENDPOINT" != "$source_endpoint" ]] || fail "Temp source endpoint equals production."
if [[ "$TEMP_MASTER_SECRET_ARN" == None ]]; then
  TEMP_MASTER_SECRET_ARN="$SOURCE_MASTER_SECRET_ARN"
fi
update_validation_secret_policy "$APP_SECRET_ARN"
log INFO "temp_source_ready identifier=$TEMP_SOURCE_IDENTIFIER endpoint=$TEMP_SOURCE_ENDPOINT public=false sg=$RDS_SECURITY_GROUP_ID production_modified=false"
phase_done

phase seed_marker_dataset
seed_output="$(run_remote_action seed_marker)"
printf '%s\n' "$seed_output"
[[ "$seed_output" == *"seed_marker=PASS"* ]] || fail "Marker seed did not pass."
phase_done

phase wait_marker_recoverable
log INFO "settle_before_restore_point seconds=$MARKER_SETTLE_SECONDS"
sleep "$MARKER_SETTLE_SECONDS"
DRILL_RESTORE_TIME="$(now)"
drill_restore_epoch="$(parse_utc_epoch "$DRILL_RESTORE_TIME")"
wait_for_temp_pitr_after "$drill_restore_epoch"
log INFO "drill_restore_time_selected=$DRILL_RESTORE_TIME marker_order_id=$MARKER_ORDER_ID"
DRILL_SETUP_END="$(epoch)"
log INFO "drill_setup_ready setup_seconds=$(( DRILL_SETUP_END - DRILL_SETUP_START )) note=setup_time_is_not_recovery_rto"
phase_done

phase controlled_delete
delete_output="$(run_remote_action delete_marker)"
printf '%s\n' "$delete_output"
[[ "$delete_output" == *"controlled_delete=PASS"* ]] || fail "Controlled delete did not pass."
RECOVERY_RTO_START="$(epoch)"
log INFO "recovery_rto_start incident=controlled_delete_confirmed marker_order_id=$MARKER_ORDER_ID"
phase_done

phase create_drill_restore_from_temp
aws_cli rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier "$TEMP_SOURCE_IDENTIFIER" \
  --target-db-instance-identifier "$DRILL_TARGET_IDENTIFIER" \
  --restore-time "$DRILL_RESTORE_TIME" \
  --db-instance-class "$RESTORE_INSTANCE_CLASS" \
  --db-subnet-group-name "$DB_SUBNET_GROUP_NAME" \
  --vpc-security-group-ids "$RDS_SECURITY_GROUP_ID" \
  --no-publicly-accessible --no-multi-az --copy-tags-to-snapshot \
  --tags "${common_tags[@]}" Key=Purpose,Value=REL26DrillRestore >/dev/null
DRILL_TARGET_CREATED=true
wait_for_rds_status "$DRILL_TARGET_IDENTIFIER" available
read -r drill_status DRILL_TARGET_ENDPOINT drill_public drill_sgs DRILL_MASTER_SECRET_ARN <<<"$(aws_cli rds describe-db-instances \
  --db-instance-identifier "$DRILL_TARGET_IDENTIFIER" \
  --query 'DBInstances[0].[DBInstanceStatus,Endpoint.Address,PubliclyAccessible,VpcSecurityGroups[*].VpcSecurityGroupId|join(`,`,@),MasterUserSecret.SecretArn]' \
  --output text)"
[[ "$drill_status" == available ]] || fail "Drill target is not available."
[[ "$drill_public" == False ]] || fail "Drill target is public."
[[ "$drill_sgs" == "$RDS_SECURITY_GROUP_ID" ]] || fail "Drill target uses unexpected SG."
[[ "$DRILL_TARGET_ENDPOINT" != "$TEMP_SOURCE_ENDPOINT" ]] || fail "Drill endpoint equals temp source."
if [[ "$DRILL_MASTER_SECRET_ARN" == None ]]; then
  DRILL_MASTER_SECRET_ARN="$TEMP_MASTER_SECRET_ARN"
fi
update_validation_secret_policy "$APP_SECRET_ARN"
log INFO "drill_target_ready identifier=$DRILL_TARGET_IDENTIFIER endpoint=$DRILL_TARGET_ENDPOINT restore_time=$DRILL_RESTORE_TIME public=false"
phase_done

phase verify_drill_contains_marker
verify_drill_output="$(run_remote_action verify_drill_marker)"
printf '%s\n' "$verify_drill_output"
[[ "$verify_drill_output" == *"verify_drill_marker=PASS"* ]] || fail "Drill restore marker validation failed."
phase_done

phase restore_marker_to_temp_source
restore_output="$(run_remote_action restore_schema_to_temp)"
printf '%s\n' "$restore_output"
[[ "$restore_output" == *"restore_schema_to_temp=PASS"* ]] || fail "Schema restore to temp source failed."
phase_done

phase final_validation
final_output="$(run_remote_action verify_temp_marker_restored)"
printf '%s\n' "$final_output"
[[ "$final_output" == *"final_validation=PASS"* ]] || fail "Final validation failed."
phase_done

PHASE=complete
RECOVERY_RTO_END="$(epoch)"
log INFO "recovery_rto_end recovery_rto_seconds=$(( RECOVERY_RTO_END - RECOVERY_RTO_START ))"
log INFO "rel26_completed production_modified=false temp_source_corrupted=true marker_restored=true marker_order_id=$MARKER_ORDER_ID drill_setup_seconds=$(( DRILL_SETUP_END - DRILL_SETUP_START )) recovery_rto_seconds=$(( RECOVERY_RTO_END - RECOVERY_RTO_START ))"
printf '\n=== REL-26 recovery summary ===\n'
printf 'Drill setup time: %ss (not counted as RTO)\n' "$(( DRILL_SETUP_END - DRILL_SETUP_START ))"
printf 'Recovery RTO:     %ss\n' "$(( RECOVERY_RTO_END - RECOVERY_RTO_START ))"
printf 'Production touched: no\n'
printf 'Marker restored:    yes\n\n'
exit 0
