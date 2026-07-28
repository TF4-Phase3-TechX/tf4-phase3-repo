#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPLAY_SCRIPT="$SCRIPT_DIR/rel25-replay-orders-archive.sh"

AWS_PROFILE="${AWS_PROFILE:-default}"
AWS_REGION="${AWS_REGION:-us-east-1}"
EXPECTED_AWS_ACCOUNT_ID="${EXPECTED_AWS_ACCOUNT_ID:-511825856493}"
EXPECTED_KUBE_CONTEXT="${EXPECTED_KUBE_CONTEXT:-arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster}"
ARCHIVE_BUCKET="${ARCHIVE_BUCKET:-tf4-msk-orders-archive-511825856493-us-east-1}"
ARCHIVE_PREFIX="${ARCHIVE_PREFIX:-orders/orders}"
START_TIME="${START_TIME:-2026-07-27T05:00:00Z}"
END_TIME="${END_TIME:-2026-07-27T06:00:00Z}"
RESTORE_DRILL_ID="${RESTORE_DRILL_ID:-rel25-$(date -u +"%Y%m%d")-msk-demo}"
TARGET_TOPIC="${TARGET_TOPIC:-orders-replay-drill-${RESTORE_DRILL_ID}}"
KAFKA_NAMESPACE="${KAFKA_NAMESPACE:-techx-tf4}"
KAFKA_CONNECT_DEPLOYMENT="${KAFKA_CONNECT_DEPLOYMENT:-kafka-connect-orders-archive}"
KAFKA_CLIENT_CONFIG="${KAFKA_CLIENT_CONFIG:-/tmp/client.properties}"
MAX_OBJECTS="${MAX_OBJECTS:-100}"
CONSUMER_TIMEOUT_MS="${CONSUMER_TIMEOUT_MS:-60000}"
REPORT_DIR="${REPORT_DIR:-$PWD/rel25-replay-reports}"
DEMO_LOG="${DEMO_LOG:-$PWD/${RESTORE_DRILL_ID}-msk-replay-demo.log}"

exec > >(tee "$DEMO_LOG") 2>&1

section() {
  printf '\n=== REL-25 MSK replay demo stage: %s ===\n' "$1"
}

run_replay_script() {
  AWS_PROFILE="$AWS_PROFILE" \
  AWS_REGION="$AWS_REGION" \
  EXPECTED_AWS_ACCOUNT_ID="$EXPECTED_AWS_ACCOUNT_ID" \
  EXPECTED_KUBE_CONTEXT="$EXPECTED_KUBE_CONTEXT" \
  ARCHIVE_BUCKET="$ARCHIVE_BUCKET" \
  ARCHIVE_PREFIX="$ARCHIVE_PREFIX" \
  START_TIME="$START_TIME" \
  END_TIME="$END_TIME" \
  RESTORE_DRILL_ID="$RESTORE_DRILL_ID" \
  TARGET_TOPIC="$TARGET_TOPIC" \
  KAFKA_NAMESPACE="$KAFKA_NAMESPACE" \
  KAFKA_CONNECT_DEPLOYMENT="$KAFKA_CONNECT_DEPLOYMENT" \
  KAFKA_CLIENT_CONFIG="$KAFKA_CLIENT_CONFIG" \
  PREFLIGHT_ONLY="${PREFLIGHT_ONLY:-false}" \
  CONFIRM_REPLAY="${CONFIRM_REPLAY:-}" \
  KEEP_TOPIC="${KEEP_TOPIC:-false}" \
  MAX_OBJECTS="$MAX_OBJECTS" \
  CONSUMER_TIMEOUT_MS="$CONSUMER_TIMEOUT_MS" \
  REPORT_DIR="$REPORT_DIR" \
  bash "$REPLAY_SCRIPT"
}

bootstrap_servers() {
  kubectl -n "$KAFKA_NAMESPACE" exec "deployment/$KAFKA_CONNECT_DEPLOYMENT" -- \
    printenv CONNECT_BOOTSTRAP_SERVERS
}

kafka_topics() {
  local bootstrap="$1"
  shift
  kubectl -n "$KAFKA_NAMESPACE" exec "deployment/$KAFKA_CONNECT_DEPLOYMENT" -- \
    /opt/kafka/bin/kafka-topics.sh \
      --bootstrap-server "$bootstrap" \
      --command-config "$KAFKA_CLIENT_CONFIG" "$@"
}

section "demo_summary"
cat <<EOF
Purpose: prove MSK orders archive can be replayed into an isolated drill topic.
Production topic: orders
Drill topic: $TARGET_TOPIC
Archive window: $START_TIME -> $END_TIME
Archive bucket: $ARCHIVE_BUCKET
Report directory: $REPORT_DIR
Demo log: $DEMO_LOG
Production safety: this demo never produces to topic orders.
EOF

section "local_syntax_check"
bash -n "$REPLAY_SCRIPT"
bash -n "$SCRIPT_DIR/lib/rel25-replay-common.sh"
python3 -m py_compile "$SCRIPT_DIR/rel25-orders-archive-tool.py"
echo "syntax_check=PASS"

section "runtime_baseline"
aws --profile "$AWS_PROFILE" --region "$AWS_REGION" sts get-caller-identity \
  --query '{Account:Account,Arn:Arn}' --output table
kubectl config current-context
kubectl -n "$KAFKA_NAMESPACE" rollout status \
  "deployment/$KAFKA_CONNECT_DEPLOYMENT" --timeout=60s
kubectl -n "$KAFKA_NAMESPACE" exec "deployment/$KAFKA_CONNECT_DEPLOYMENT" -- \
  sh -c 'curl -fsS http://127.0.0.1:8083/connectors/orders-s3-archive/status' | jq .

section "production_topic_before"
bootstrap="$(bootstrap_servers)"
kafka_topics "$bootstrap" --list | sort
kafka_topics "$bootstrap" --describe --topic orders

section "archive_window_preflight"
PREFLIGHT_ONLY=true run_replay_script

section "negative_guardrail_production_topic"
set +e
PREFLIGHT_ONLY=true TARGET_TOPIC=orders run_replay_script
guardrail_exit=$?
set -e
if [[ "$guardrail_exit" -eq 0 ]]; then
  echo "negative_guardrail=FAIL expected non-zero exit when TARGET_TOPIC=orders"
  exit 1
fi
echo "negative_guardrail=PASS target_topic_orders_rejected=true exit_code=$guardrail_exit"

section "live_replay_to_isolated_topic"
PREFLIGHT_ONLY=false CONFIRM_REPLAY=YES run_replay_script

section "report"
report_file="$REPORT_DIR/${RESTORE_DRILL_ID}-msk-replay-report.json"
test -s "$report_file"
jq . "$report_file"
validation="$(jq -r .validation "$report_file")"
failed="$(jq -r .counters.failed "$report_file")"
replayed="$(jq -r .counters.replayed "$report_file")"
if [[ "$validation" != PASS || "$failed" != 0 || "$replayed" -lt 1 ]]; then
  echo "report_validation=FAIL validation=$validation failed=$failed replayed=$replayed"
  exit 1
fi
echo "report_validation=PASS validation=$validation failed=$failed replayed=$replayed"

section "cleanup_verification"
if kafka_topics "$bootstrap" --list | grep -Fx "$TARGET_TOPIC"; then
  echo "cleanup_verification=FAIL drill_topic_still_exists=$TARGET_TOPIC"
  exit 1
fi
echo "drill_topic_present=false"
if kafka_topics "$bootstrap" --list | grep -Fx orders; then
  echo "production_topic_present=true"
else
  echo "cleanup_verification=FAIL production_topic_missing=orders"
  exit 1
fi
kubectl -n "$KAFKA_NAMESPACE" exec "deployment/$KAFKA_CONNECT_DEPLOYMENT" -- \
  sh -c 'curl -fsS http://127.0.0.1:8083/connectors/orders-s3-archive/status' | jq \
    '{connector:.connector.state, tasks:[.tasks[] | {id:.id,state:.state}]}'

section "final_result"
cat <<EOF
REL25_MSK_REPLAY_DRILL=PASS
drill_id=$RESTORE_DRILL_ID
target_topic=$TARGET_TOPIC
source_window=$START_TIME->$END_TIME
report_file=$report_file
demo_log=$DEMO_LOG
EOF
