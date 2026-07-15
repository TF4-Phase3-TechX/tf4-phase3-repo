#!/usr/bin/env bash
set -euo pipefail

# Prevent Git Bash on Windows from rewriting container paths such as /opt/kafka.
export MSYS_NO_PATHCONV=1

NAMESPACE="${NAMESPACE:-techx-tf4}"
DEPLOYMENT="${DEPLOYMENT:-kafka}"
PVC="${PVC:-kafka-pvc}"
EXPECTED_CONTEXT_PATTERN="${EXPECTED_CONTEXT_PATTERN:-techx-tf4-cluster}"
EXPECTED_STORAGE_CLASS="${EXPECTED_STORAGE_CLASS:-gp3}"
BOOTSTRAP="${BOOTSTRAP:-kafka:9092}"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
TOPIC="${TOPIC:-rel03c-pvc-proof-${STAMP,,}}"
MARKER="${MARKER:-rel03c-event-${STAMP}}"
KAFKA_BIN="/opt/kafka/bin"

kafka_exec() {
  kubectl -n "$NAMESPACE" exec "deployment/$DEPLOYMENT" -- env \
    KAFKA_OPTS= KAFKA_HEAP_OPTS="-Xms64m -Xmx128m" "$@"
}

require_target() {
  local context status storage_class log_dirs
  context="$(kubectl config current-context)"
  [[ "$context" == *"$EXPECTED_CONTEXT_PATTERN"* ]] || { echo "Refusing context: $context" >&2; exit 1; }
  status="$(kubectl -n "$NAMESPACE" get pvc "$PVC" -o jsonpath='{.status.phase}')"
  storage_class="$(kubectl -n "$NAMESPACE" get pvc "$PVC" -o jsonpath='{.spec.storageClassName}')"
  [[ "$status" == "Bound" ]] || { echo "$PVC is not Bound" >&2; exit 1; }
  if [[ "$storage_class" != "$EXPECTED_STORAGE_CLASS" ]]; then
    [[ "${ALLOW_CURRENT_STORAGE_CLASS:-}" == "$storage_class" ]] || {
      echo "StorageClass is '$storage_class', expected '$EXPECTED_STORAGE_CLASS'." >&2
      echo "Use a separate PVC migration; acknowledge only with ALLOW_CURRENT_STORAGE_CLASS=$storage_class." >&2
      exit 1
    }
    echo "WARNING: verifying StorageClass=$storage_class deviation; gp3 requires separate migration."
  fi
  kubectl -n "$NAMESPACE" rollout status "deployment/$DEPLOYMENT" --timeout=180s
  log_dirs="$(kubectl -n "$NAMESPACE" exec "deployment/$DEPLOYMENT" -- printenv KAFKA_LOG_DIRS | tr -d '\r')"
  [[ -n "$log_dirs" ]]
  kubectl -n "$NAMESPACE" exec "deployment/$DEPLOYMENT" -- sh -c 'test -d "$KAFKA_LOG_DIRS"'
  echo "Context: $context"
  echo "PVC: $PVC status=$status storageClass=$storage_class"
  echo "Kafka log directory on PVC: $log_dirs"
}

create_and_produce() {
  kafka_exec "$KAFKA_BIN/kafka-topics.sh" --bootstrap-server "$BOOTSTRAP" \
    --create --if-not-exists --topic "$TOPIC" --partitions 1 --replication-factor 1
  printf '%s\n' "$MARKER" | kubectl -n "$NAMESPACE" exec -i "deployment/$DEPLOYMENT" -- env \
    KAFKA_OPTS= KAFKA_HEAP_OPTS="-Xms64m -Xmx128m" \
    "$KAFKA_BIN/kafka-console-producer.sh" --bootstrap-server "$BOOTSTRAP" --topic "$TOPIC"
  echo "Produced marker: topic=$TOPIC value=$MARKER"
}

consume_marker() {
  local output
  output="$(kafka_exec "$KAFKA_BIN/kafka-console-consumer.sh" --bootstrap-server "$BOOTSTRAP" \
    --topic "$TOPIC" --from-beginning --max-messages 1 --timeout-ms 60000 2>&1)"
  printf '%s\n' "$output"
  grep -Fq "$MARKER" <<<"$output"
}

consumer_groups() {
  kafka_exec "$KAFKA_BIN/kafka-consumer-groups.sh" --bootstrap-server "$BOOTSTRAP" \
    --group accounting --describe
  kafka_exec "$KAFKA_BIN/kafka-consumer-groups.sh" --bootstrap-server "$BOOTSTRAP" \
    --group fraud-detection --describe
}

cleanup_topic() {
  kafka_exec "$KAFKA_BIN/kafka-topics.sh" --bootstrap-server "$BOOTSTRAP" \
    --delete --if-exists --topic "$TOPIC" >/dev/null || true
}

wait_for_broker_api() {
  local attempt
  for attempt in $(seq 1 18); do
    if kafka_exec "$KAFKA_BIN/kafka-topics.sh" --bootstrap-server "$BOOTSTRAP" --list >/dev/null 2>&1; then
      echo "Kafka API ready after restart (attempt $attempt)."
      return 0
    fi
    sleep 10
  done
  echo "Kafka API did not become ready within the recovery window." >&2
  return 1
}

verify() {
  create_and_produce
  consume_marker
  consumer_groups
  cleanup_topic
  echo "Kafka event smoke passed before recreation."
}

recreate_proof() {
  [[ "${CONFIRM_RECREATE:-}" == "${NAMESPACE}/${DEPLOYMENT}" ]] || {
    echo "Rerun with CONFIRM_RECREATE=${NAMESPACE}/${DEPLOYMENT}" >&2
    exit 1
  }
  local before_uid after_uid
  before_uid="$(kubectl -n "$NAMESPACE" get pod -l app.kubernetes.io/component=kafka -o jsonpath='{.items[0].metadata.uid}')"
  create_and_produce
  consume_marker
  consumer_groups
  kubectl -n "$NAMESPACE" delete pod -l app.kubernetes.io/component=kafka --wait=true
  kubectl -n "$NAMESPACE" rollout status "deployment/$DEPLOYMENT" --timeout=420s
  wait_for_broker_api
  after_uid="$(kubectl -n "$NAMESPACE" get pod -l app.kubernetes.io/component=kafka -o jsonpath='{.items[0].metadata.uid}')"
  [[ "$before_uid" != "$after_uid" ]]
  consume_marker
  consumer_groups
  cleanup_topic
  echo "Old pod UID: $before_uid"
  echo "New pod UID: $after_uid"
  echo "Kafka recreation proof passed: marker and consumer groups survived pod replacement."
}

require_target
case "${1:-}" in
  verify) verify ;;
  recreate-proof) recreate_proof ;;
  *) echo "Usage: $0 verify|recreate-proof" >&2; exit 2 ;;
esac
