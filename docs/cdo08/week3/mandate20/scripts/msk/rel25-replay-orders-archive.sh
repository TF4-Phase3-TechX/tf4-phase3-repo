#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COMMON_LIBRARY="$SCRIPT_DIR/lib/rel25-replay-common.sh"
ARCHIVE_TOOL="$SCRIPT_DIR/rel25-orders-archive-tool.py"

[[ -r "$COMMON_LIBRARY" ]] || {
  echo "Missing common library: $COMMON_LIBRARY" >&2
  exit 1
}
[[ -r "$ARCHIVE_TOOL" ]] || {
  echo "Missing archive tool: $ARCHIVE_TOOL" >&2
  exit 1
}

# shellcheck source=lib/rel25-replay-common.sh
source "$COMMON_LIBRARY"

AWS_PROFILE="${AWS_PROFILE:-}"
AWS_REGION="${AWS_REGION:-us-east-1}"
EXPECTED_AWS_ACCOUNT_ID="${EXPECTED_AWS_ACCOUNT_ID:-}"
EXPECTED_KUBE_CONTEXT="${EXPECTED_KUBE_CONTEXT:-}"
ARCHIVE_BUCKET="${ARCHIVE_BUCKET:-}"
ARCHIVE_PREFIX="${ARCHIVE_PREFIX:-orders/orders}"
START_TIME="${START_TIME:-}"
END_TIME="${END_TIME:-}"
RESTORE_DRILL_ID="${RESTORE_DRILL_ID:-}"
TARGET_TOPIC="${TARGET_TOPIC:-}"
KAFKA_NAMESPACE="${KAFKA_NAMESPACE:-techx-tf4}"
KAFKA_CONNECT_DEPLOYMENT="${KAFKA_CONNECT_DEPLOYMENT:-kafka-connect-orders-archive}"
KAFKA_CLIENT_CONFIG="${KAFKA_CLIENT_CONFIG:-/tmp/client.properties}"
PREFLIGHT_ONLY="${PREFLIGHT_ONLY:-false}"
CONFIRM_REPLAY="${CONFIRM_REPLAY:-}"
KEEP_TOPIC="${KEEP_TOPIC:-false}"
MAX_OBJECTS="${MAX_OBJECTS:-100}"
CONSUMER_TIMEOUT_MS="${CONSUMER_TIMEOUT_MS:-60000}"
REPORT_DIR="${REPORT_DIR:-$PWD/rel25-replay-reports}"

PHASE=initialization
PHASE_START=0
TOPIC_CREATED=false
CONSUMER_GROUP_USED=false
CLEANUP_FAILED=false
WORK_DIR=""
KAFKA_BOOTSTRAP_SERVERS=""
CONSUMER_GROUP="rel25-replay-verify-${RESTORE_DRILL_ID:-unset}"
BATCH_ID="${RESTORE_DRILL_ID:-unset}"

trap on_exit EXIT

for command in aws date jq kubectl python3; do
  command -v "$command" >/dev/null 2>&1 || fail "Missing command $command."
done
for variable in AWS_PROFILE EXPECTED_AWS_ACCOUNT_ID EXPECTED_KUBE_CONTEXT \
  ARCHIVE_BUCKET START_TIME END_TIME RESTORE_DRILL_ID TARGET_TOPIC; do
  need "$variable"
done
for number in MAX_OBJECTS CONSUMER_TIMEOUT_MS; do
  [[ "${!number}" =~ ^[1-9][0-9]*$ ]] || fail "$number must be a positive integer."
done
[[ "$PREFLIGHT_ONLY" == true || "$PREFLIGHT_ONLY" == false ]] || \
  fail "PREFLIGHT_ONLY must be true or false."
[[ "$KEEP_TOPIC" == true || "$KEEP_TOPIC" == false ]] || \
  fail "KEEP_TOPIC must be true or false."
[[ "$RESTORE_DRILL_ID" =~ ^rel25-[0-9]{8}(-[a-z0-9-]+)?$ ]] || \
  fail "RESTORE_DRILL_ID must match rel25-YYYYMMDD[-suffix]."
[[ "$TARGET_TOPIC" =~ ^orders-replay-drill-rel25-[a-z0-9-]+$ ]] || \
  fail "TARGET_TOPIC must match orders-replay-drill-rel25-*."
[[ "$TARGET_TOPIC" != orders ]] || fail "Production topic orders is forbidden."
case "$TARGET_TOPIC" in
  orders-archive-dlq|orders-archive-connect-*)
    fail "Kafka Connect internal/archive topics are forbidden."
    ;;
esac
[[ "$CONSUMER_GROUP" =~ ^rel25-replay-verify-[a-z0-9-]+$ ]] || \
  fail "Unsafe consumer group name."

phase environment_preflight
actual_account="$(aws_cli sts get-caller-identity --query Account --output text)"
[[ "$actual_account" == "$EXPECTED_AWS_ACCOUNT_ID" ]] || \
  fail "AWS account mismatch expected=$EXPECTED_AWS_ACCOUNT_ID actual=$actual_account."
actual_context="$(kubectl config current-context)"
[[ "$actual_context" == "$EXPECTED_KUBE_CONTEXT" ]] || \
  fail "Kubernetes context mismatch."
aws_cli s3api head-bucket --bucket "$ARCHIVE_BUCKET"
kubectl -n "$KAFKA_NAMESPACE" rollout status \
  "deployment/$KAFKA_CONNECT_DEPLOYMENT" --timeout=60s
KAFKA_BOOTSTRAP_SERVERS="$(
  kubectl -n "$KAFKA_NAMESPACE" exec "deployment/$KAFKA_CONNECT_DEPLOYMENT" -- \
    printenv CONNECT_BOOTSTRAP_SERVERS
)"
[[ -n "$KAFKA_BOOTSTRAP_SERVERS" ]] || fail "Cannot resolve Kafka bootstrap servers."
kube_exec test -r "$KAFKA_CLIENT_CONFIG" || fail "Kafka client config is missing."
kube_exec /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" \
  --command-config "$KAFKA_CLIENT_CONFIG" --list >/dev/null
phase_done

phase target_guardrail
if topic_exists; then
  fail "Target topic already exists; refusing a non-idempotent retry."
fi
log INFO "target_guardrail_passed production_topic=orders target_topic=$TARGET_TOPIC"
phase_done

phase discover_archive_window
prefixes=()
while IFS= read -r prefix; do
  [[ -n "$prefix" ]] && prefixes+=("$prefix")
done < <(
  python3 "$ARCHIVE_TOOL" prefixes \
    --start-time "$START_TIME" \
    --end-time "$END_TIME" \
    --base-prefix "$ARCHIVE_PREFIX" | tr -d '\r'
)
(( ${#prefixes[@]} > 0 )) || fail "No hourly archive prefixes generated."

object_keys=()
for prefix in "${prefixes[@]}"; do
  while IFS= read -r key; do
    [[ -n "$key" && "$key" != None ]] && object_keys+=("$key")
  done < <(
    aws_cli s3api list-objects-v2 \
      --bucket "$ARCHIVE_BUCKET" \
      --prefix "$prefix" \
      --query 'Contents[].Key' \
      --output json | jq -r '.[]? | select(test("\\.(bin|json)$"))' | tr -d '\r'
  )
done
(( ${#object_keys[@]} > 0 )) || fail "No archive objects found in the requested window."
(( ${#object_keys[@]} <= MAX_OBJECTS )) || \
  fail "Window contains ${#object_keys[@]} objects, above MAX_OBJECTS=$MAX_OBJECTS."
log INFO "archive_window_discovered prefixes=${#prefixes[@]} objects=${#object_keys[@]}"
phase_done

if [[ "$PREFLIGHT_ONLY" == true ]]; then
  PHASE=complete
  log INFO "preflight_only_passed no_topic_created=true objects=${#object_keys[@]}"
  exit 0
fi
[[ "$CONFIRM_REPLAY" == YES ]] || fail "Set CONFIRM_REPLAY=YES for live replay."

mkdir -p "$REPORT_DIR"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/rel25-msk-replay.XXXXXX")"
ARCHIVE_DIR="$WORK_DIR/archive"
PRODUCER_FILE="$WORK_DIR/producer.tsv"
MANIFEST_FILE="$WORK_DIR/manifest.jsonl"
PREPARE_SUMMARY="$WORK_DIR/prepare-summary.json"
CONSUMED_FILE="$WORK_DIR/consumed.tsv"
VERIFY_RESULT="$WORK_DIR/verify-result.json"
mkdir -p "$ARCHIVE_DIR"

phase download_archive_objects
index=0
for prefix in "${prefixes[@]}"; do
  index=$((index + 1))
  destination="$ARCHIVE_DIR/$(printf '%04d' "$index")"
  mkdir -p "$destination"
  aws_cli s3 cp "s3://$ARCHIVE_BUCKET/$prefix" "$destination" \
    --recursive --exclude '*' --include '*.bin' --include '*.json' \
    --only-show-errors
done
downloaded_count="$(find "$ARCHIVE_DIR" -type f | wc -l | tr -d '[:space:]')"
[[ "$downloaded_count" == "${#object_keys[@]}" ]] || \
  fail "Downloaded object count mismatch expected=${#object_keys[@]} actual=$downloaded_count."
phase_done

phase parse_normalize_deduplicate
if ! python3 "$ARCHIVE_TOOL" prepare \
    --input-dir "$ARCHIVE_DIR" \
    --producer-file "$PRODUCER_FILE" \
    --manifest-file "$MANIFEST_FILE" \
    --summary-file "$PREPARE_SUMMARY" \
    --batch-id "$BATCH_ID" \
    --start-time "$START_TIME" \
    --end-time "$END_TIME"; then
  if [[ -s "$PREPARE_SUMMARY" ]]; then
    cp "$PREPARE_SUMMARY" \
      "$REPORT_DIR/${RESTORE_DRILL_ID}-msk-replay-prepare-failure.json"
    log ERROR "prepare_failure_report_written report_dir=$REPORT_DIR"
  fi
  fail "Archive payload integrity/normalization failed before topic creation."
fi
records_read="$(jq -r .records_read "$PREPARE_SUMMARY")"
replay_candidates="$(jq -r .replay_candidates "$PREPARE_SUMMARY")"
duplicates_skipped="$(jq -r .duplicates_skipped "$PREPARE_SUMMARY")"
parse_failed="$(jq -r .failed "$PREPARE_SUMMARY")"
source_marker_candidates="$(jq -r .source_marker_candidates "$PREPARE_SUMMARY")"
[[ "$parse_failed" == 0 ]] || fail "Parser reported failed=$parse_failed."
phase_done

phase create_isolated_topic
if kube_exec /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" \
    --command-config "$KAFKA_CLIENT_CONFIG" \
    --create --topic "$TARGET_TOPIC" \
    --partitions 1 --replication-factor 2 \
    --config cleanup.policy=delete \
    --config retention.ms=21600000; then
  TOPIC_CREATED=true
else
  sleep 3
  if topic_exists; then
    TOPIC_CREATED=true
    log WARN "create_command_failed_but_topic_exists continuing=true"
  else
    fail "Topic creation failed and target does not exist."
  fi
fi
kube_exec /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" \
  --command-config "$KAFKA_CLIENT_CONFIG" \
  --describe --topic "$TARGET_TOPIC"
phase_done

phase replay_batch
MSYS_NO_PATHCONV=1 kubectl -n "$KAFKA_NAMESPACE" \
  exec -i "deployment/$KAFKA_CONNECT_DEPLOYMENT" -- \
  /opt/kafka/bin/kafka-console-producer.sh \
    --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" \
    --producer.config "$KAFKA_CLIENT_CONFIG" \
    --topic "$TARGET_TOPIC" \
    --property parse.key=true \
    --property key.separator=$'\t' \
    --producer-property enable.idempotence=true \
    --producer-property acks=all <"$PRODUCER_FILE"
log INFO "batch_produced start_markers=1 replayed=$replay_candidates end_markers=1"
phase_done

phase consume_validate_batch
expected_messages=$((replay_candidates + 2))
CONSUMER_GROUP_USED=true
kube_exec /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" \
  --consumer.config "$KAFKA_CLIENT_CONFIG" \
  --topic "$TARGET_TOPIC" \
  --group "$CONSUMER_GROUP" \
  --from-beginning \
  --max-messages "$expected_messages" \
  --timeout-ms "$CONSUMER_TIMEOUT_MS" \
  --property print.key=true \
  --property key.separator=$'\t' >"$CONSUMED_FILE"

python3 "$ARCHIVE_TOOL" verify \
  --manifest-file "$MANIFEST_FILE" \
  --consumed-file "$CONSUMED_FILE" \
  --result-file "$VERIFY_RESULT" \
  --batch-id "$BATCH_ID"
validation="$(jq -r .validation "$VERIFY_RESULT")"
replayed="$(jq -r .replayed "$VERIFY_RESULT")"
validation_failed="$(jq -r .failed "$VERIFY_RESULT")"
source_markers_replayed="$(jq -r .source_markers_replayed "$VERIFY_RESULT")"
[[ "$validation" == PASS ]] || fail "Replay validation failed."
[[ "$source_markers_replayed" == "$source_marker_candidates" ]] || \
  fail "Source marker count mismatch expected=$source_marker_candidates actual=$source_markers_replayed."
phase_done

phase write_report
REPORT_FILE="$REPORT_DIR/${RESTORE_DRILL_ID}-msk-replay-report.json"
jq -n \
  --arg drill_id "$RESTORE_DRILL_ID" \
  --arg target_topic "$TARGET_TOPIC" \
  --arg start_time "$START_TIME" \
  --arg end_time "$END_TIME" \
  --arg completed_at "$(now_utc)" \
  --argjson objects_read "${#object_keys[@]}" \
  --argjson records_read "$records_read" \
  --argjson replayed "$replayed" \
  --argjson failed "$((parse_failed + validation_failed))" \
  --argjson duplicates_skipped "$duplicates_skipped" \
  --argjson source_markers_replayed "$source_markers_replayed" \
  --argjson control_markers_replayed 2 \
  --arg validation "$validation" \
  '{
    drill_id:$drill_id,
    target_topic:$target_topic,
    source_window:{start:$start_time,end:$end_time},
    completed_at:$completed_at,
    counters:{
      objects_read:$objects_read,
      records_read:$records_read,
      replayed:$replayed,
      failed:$failed,
      duplicates_skipped:$duplicates_skipped,
      source_markers_replayed:$source_markers_replayed,
      control_markers_replayed:$control_markers_replayed
    },
    validation:$validation
  }' >"$REPORT_FILE"
log INFO "report_written path=$REPORT_FILE"
phase_done

PHASE=complete
log INFO "replay_passed objects_read=${#object_keys[@]} records_read=$records_read replayed=$replayed failed=$((parse_failed + validation_failed)) duplicates_skipped=$duplicates_skipped source_markers_replayed=$source_markers_replayed control_markers_replayed=2"

if [[ "$KEEP_TOPIC" == true ]]; then
  TOPIC_CREATED=false
  log WARN "topic_retained_by_request topic=$TARGET_TOPIC"
fi
