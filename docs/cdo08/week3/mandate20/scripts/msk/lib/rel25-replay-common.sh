#!/usr/bin/env bash

now_utc() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

log() {
  printf '%s level=%s phase=%s message=%s\n' "$(now_utc)" "$1" "$PHASE" "$2"
}

fail() {
  log ERROR "$1" >&2
  exit 1
}

need() {
  [[ -n "${!1:-}" ]] || fail "Set $1 before running."
}

phase() {
  PHASE="$1"
  PHASE_START="$(date +%s)"
  log INFO phase_start
}

phase_done() {
  log INFO "phase_end duration_seconds=$(( $(date +%s) - PHASE_START ))"
}

aws_cli() {
  aws --profile "$AWS_PROFILE" --region "$AWS_REGION" "$@"
}

kube_exec() {
  MSYS_NO_PATHCONV=1 kubectl -n "$KAFKA_NAMESPACE" \
    exec "deployment/$KAFKA_CONNECT_DEPLOYMENT" -- "$@"
}

topic_exists() {
  kube_exec /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" \
    --command-config "$KAFKA_CLIENT_CONFIG" \
    --list | grep -Fxq "$TARGET_TOPIC"
}

delete_drill_topic() {
  local attempt

  [[ "$TOPIC_CREATED" == true ]] || return 0
  [[ "$TARGET_TOPIC" =~ ^orders-replay-drill-rel25-[a-z0-9-]+$ ]] || {
    log ERROR "cleanup_refused unsafe_topic=$TARGET_TOPIC"
    CLEANUP_FAILED=true
    return 1
  }

  log INFO "cleanup_topic_start topic=$TARGET_TOPIC"
  if ! kube_exec /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" \
    --command-config "$KAFKA_CLIENT_CONFIG" \
    --delete --topic "$TARGET_TOPIC"; then
    log WARN "cleanup_topic_delete_command_failed checking_actual_state=true topic=$TARGET_TOPIC"
  fi

  for attempt in {1..30}; do
    if ! topic_exists; then
      TOPIC_CREATED=false
      log INFO "cleanup_topic_complete topic=$TARGET_TOPIC"
      return 0
    fi
    sleep 2
  done

  log ERROR "cleanup_topic_still_exists topic=$TARGET_TOPIC"
  CLEANUP_FAILED=true
  return 1
}

delete_drill_consumer_group() {
  [[ "$CONSUMER_GROUP_USED" == true ]] || return 0
  [[ "$CONSUMER_GROUP" =~ ^rel25-replay-verify-[a-z0-9-]+$ ]] || {
    log ERROR "cleanup_refused unsafe_consumer_group=$CONSUMER_GROUP"
    CLEANUP_FAILED=true
    return 1
  }

  kube_exec /opt/kafka/bin/kafka-consumer-groups.sh \
    --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" \
    --command-config "$KAFKA_CLIENT_CONFIG" \
    --delete --group "$CONSUMER_GROUP" >/dev/null 2>&1 || true
  log INFO "cleanup_consumer_group_requested group=$CONSUMER_GROUP"
}

cleanup_local_files() {
  [[ -n "${WORK_DIR:-}" && -d "$WORK_DIR" ]] || return 0
  rm -rf -- "$WORK_DIR"
  log INFO local_temporary_files_removed
}

on_exit() {
  local code=$?
  PHASE=cleanup

  delete_drill_consumer_group || true
  delete_drill_topic || true
  cleanup_local_files || true

  if [[ "$CLEANUP_FAILED" == true ]]; then
    log ERROR "cleanup_failed topic=$TARGET_TOPIC group=$CONSUMER_GROUP"
    exit 1
  fi

  if ((code != 0)); then
    log ERROR "replay_failed exit_code=$code"
  fi
  exit "$code"
}
