#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-drill}"

AWS_PROFILE="${AWS_PROFILE:-default}"
AWS_REGION="${AWS_REGION:-us-east-1}"
EXPECTED_AWS_ACCOUNT_ID="${EXPECTED_AWS_ACCOUNT_ID:-511825856493}"
EXPECTED_KUBE_CONTEXT="${EXPECTED_KUBE_CONTEXT:-arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster}"
APP_NAMESPACE="${APP_NAMESPACE:-techx-tf4}"
OBSERVABILITY_NAMESPACE="${OBSERVABILITY_NAMESPACE:-techx-observability}"

REL35_DRILL_ID="${REL35_DRILL_ID:-rel35-$(date -u +"%Y%m%dT%H%M%SZ")}"
REL35_INTERVAL="${REL35_INTERVAL:-10}"
REL35_OBSERVE_DURATION="${REL35_OBSERVE_DURATION:-900}"
REL35_OUTPUT="${REL35_OUTPUT:-artifacts/rel35/${REL35_DRILL_ID}-az-loss-drill.log}"
REL35_TARGET_AZ="${REL35_TARGET_AZ:-}"

# mentor: run preflight/observer and wait for an external AZ fault injection.
# ec2-az-loss: stop On-Demand nodes and terminate Spot nodes in REL35_TARGET_AZ, then observe.
REL35_FAULT_MODE="${REL35_FAULT_MODE:-mentor}"
CONFIRM_REL35_AZ_LOSS="${CONFIRM_REL35_AZ_LOSS:-}"
REL35_AUTO_RECOVER="${REL35_AUTO_RECOVER:-true}"

OBSERVER_SCRIPT="${OBSERVER_SCRIPT:-docs/cdo08/week3/mandate21/scripts/rel33-az-loss-observer.sh}"

usage() {
  cat <<'EOF'
Usage:
  rel35-one-az-loss-drill.sh preflight
  rel35-one-az-loss-drill.sh drill

Common env:
  REL35_TARGET_AZ=us-east-1b
  REL35_OBSERVE_DURATION=900
  REL35_INTERVAL=10
  REL35_FAULT_MODE=mentor|ec2-az-loss

Safe official mode:
  make rel35-drill

Self-injection mode:
  REL35_FAULT_MODE=ec2-az-loss CONFIRM_REL35_AZ_LOSS=YES make rel35-drill
EOF
}

case "$MODE" in
  preflight|drill) ;;
  -h|--help) usage; exit 0 ;;
  *) echo "Unknown mode: $MODE" >&2; usage >&2; exit 64 ;;
esac

mkdir -p "$(dirname "$REL35_OUTPUT")"
touch "$REL35_OUTPUT"
chmod 600 "$REL35_OUTPUT" 2>/dev/null || true

timestamp() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
emit() { printf '%s\n' "$*" | tee -a "$REL35_OUTPUT"; }
section() {
  emit ""
  emit "=== REL-35 stage: $1 ==="
  emit "timestamp=$(timestamp)"
}

aws_cli() {
  aws --profile "$AWS_PROFILE" --region "$AWS_REGION" "$@"
}

run_logged() {
  emit "+ $*"
  "$@" 2>&1 | tee -a "$REL35_OUTPUT"
}

require_commands() {
  local command
  for command in aws kubectl awk sort sed tee date bash; do
    command -v "$command" >/dev/null 2>&1 || {
      emit "status=FAIL phase=local_dependencies missing=$command"
      exit 64
    }
  done
  [[ -x "$OBSERVER_SCRIPT" || -f "$OBSERVER_SCRIPT" ]] || {
    emit "status=FAIL phase=local_dependencies missing_observer_script=$OBSERVER_SCRIPT"
    exit 64
  }
}

check_identity() {
  section "identity_guardrail"

  local account_id
  account_id="$(aws_cli sts get-caller-identity --query Account --output text)"
  emit "aws_account_id=$account_id expected=$EXPECTED_AWS_ACCOUNT_ID"
  if [[ "$account_id" != "$EXPECTED_AWS_ACCOUNT_ID" ]]; then
    emit "status=FAIL phase=identity_guardrail reason=unexpected_aws_account"
    exit 2
  fi

  local context
  context="$(kubectl config current-context)"
  emit "kube_context=$context expected=$EXPECTED_KUBE_CONTEXT"
  if [[ "$context" != "$EXPECTED_KUBE_CONTEXT" ]]; then
    emit "status=FAIL phase=identity_guardrail reason=unexpected_kube_context"
    exit 2
  fi

  emit "status=PASS phase=identity_guardrail"
}

run_observer_preflight() {
  section "observer_preflight"
  AWS_PROFILE="$AWS_PROFILE" \
  EXPECTED_AWS_ACCOUNT_ID="$EXPECTED_AWS_ACCOUNT_ID" \
  EXPECTED_KUBE_CONTEXT="$EXPECTED_KUBE_CONTEXT" \
  KUBE_NAMESPACE="$APP_NAMESPACE" \
  OBSERVABILITY_NAMESPACE="$OBSERVABILITY_NAMESPACE" \
    bash "$OBSERVER_SCRIPT" preflight --output "$REL35_OUTPUT"
  emit "status=PASS phase=observer_preflight"
}

print_runtime_baseline() {
  section "runtime_baseline"
  emit "nodes_by_zone"
  run_logged kubectl get nodes -L topology.kubernetes.io/zone -o wide
  emit "revenue_path_pods"
  run_logged kubectl -n "$APP_NAMESPACE" get pods -o wide
  emit "observability_pods"
  run_logged kubectl -n "$OBSERVABILITY_NAMESPACE" get pods -o wide
  emit "pdb"
  run_logged kubectl -n "$APP_NAMESPACE" get pdb
  emit "hpa"
  run_logged kubectl -n "$APP_NAMESPACE" get hpa
}

pick_target_az() {
  local prometheus_node prometheus_az zone
  prometheus_node="$(kubectl -n "$OBSERVABILITY_NAMESPACE" get pod \
    -l app.kubernetes.io/name=prometheus \
    -o jsonpath='{.items[0].spec.nodeName}' 2>/dev/null || true)"

  if [[ -n "$prometheus_node" ]]; then
    prometheus_az="$(kubectl get node "$prometheus_node" \
      -o jsonpath='{.metadata.labels.topology\.kubernetes\.io/zone}' 2>/dev/null || true)"
    emit "prometheus_node=$prometheus_node prometheus_az=$prometheus_az"
  else
    prometheus_az=""
    emit "prometheus_node=UNKNOWN prometheus_az=UNKNOWN"
  fi

  if [[ -n "$REL35_TARGET_AZ" ]]; then
    TARGET_AZ_SELECTED="$REL35_TARGET_AZ"
    return
  fi

  while IFS= read -r zone; do
    [[ -n "$zone" ]] || continue
    if [[ -z "$prometheus_az" || "$zone" != "$prometheus_az" ]]; then
      TARGET_AZ_SELECTED="$zone"
      return
    fi
  done < <(kubectl get nodes -L topology.kubernetes.io/zone --no-headers \
    | awk '$2 ~ /^Ready/ {print $NF}' \
    | sort -u)

  emit "status=FAIL phase=target_az_selection reason=cannot_find_non_prometheus_az"
  exit 2
}

collect_target_nodes_and_instances() {
  local target_az="$1"
  TARGET_NODES=()
  TARGET_INSTANCES=()
  TARGET_ONDEMAND_INSTANCES=()
  TARGET_SPOT_INSTANCES=()

  while IFS= read -r node; do
    [[ -n "$node" ]] || continue
    TARGET_NODES+=("$node")
  done < <(kubectl get nodes -L topology.kubernetes.io/zone --no-headers \
    | awk -v az="$target_az" '$2 ~ /^Ready/ && $NF == az {print $1}')

  local node provider_id instance_id
  for node in "${TARGET_NODES[@]}"; do
    provider_id="$(kubectl get node "$node" -o jsonpath='{.spec.providerID}')"
    instance_id="${provider_id##*/}"
    if [[ "$instance_id" == i-* ]]; then
      TARGET_INSTANCES+=("$instance_id")
    fi
  done

  if (( ${#TARGET_INSTANCES[@]} > 0 )); then
    local instance_lifecycle instance_id
    while read -r instance_id instance_lifecycle; do
      [[ -n "$instance_id" ]] || continue
      if [[ "$instance_lifecycle" == "spot" ]]; then
        TARGET_SPOT_INSTANCES+=("$instance_id")
      else
        TARGET_ONDEMAND_INSTANCES+=("$instance_id")
      fi
    done < <(aws_cli ec2 describe-instances \
      --instance-ids "${TARGET_INSTANCES[@]}" \
      --query 'Reservations[].Instances[].[InstanceId, InstanceLifecycle]' \
      --output text | awk '{print $1, ($2 == "None" ? "" : $2)}')
  fi
}

print_target_plan() {
  local target_az="$1"
  section "target_az_plan"
  emit "target_az=$target_az"
  emit "target_nodes=${TARGET_NODES[*]:-NONE}"
  emit "target_instances=${TARGET_INSTANCES[*]:-NONE}"
  emit "target_ondemand_instances=${TARGET_ONDEMAND_INSTANCES[*]:-NONE}"
  emit "target_spot_instances=${TARGET_SPOT_INSTANCES[*]:-NONE}"

  if [[ "${#TARGET_NODES[@]}" -eq 0 || "${#TARGET_INSTANCES[@]}" -eq 0 ]]; then
    emit "status=FAIL phase=target_az_plan reason=no_ready_worker_instances_in_target_az"
    exit 2
  fi

  emit "status=PASS phase=target_az_plan"
}

inject_fault_if_requested() {
  local target_az="$1"

  section "fault_injection"
  if [[ "$REL35_FAULT_MODE" == "mentor" ]]; then
    emit "fault_mode=mentor"
    emit "action=wait_for_external_fault_injection target_az=$target_az"
    emit "instruction=Ask mentor/operator to isolate or stop AZ now, then press Enter to start observer."
    if [[ -t 0 ]]; then
      read -r -p "Press Enter after the AZ fault has been injected..."
    else
      emit "status=FAIL phase=fault_injection reason=non_interactive_mentor_mode"
      exit 64
    fi
    emit "status=PASS phase=fault_injection detail=external_fault_confirmed_by_operator"
    return
  fi

  if [[ "$REL35_FAULT_MODE" != "ec2-az-loss" ]]; then
    emit "status=FAIL phase=fault_injection reason=unsupported_fault_mode value=$REL35_FAULT_MODE"
    exit 64
  fi

  if [[ "$CONFIRM_REL35_AZ_LOSS" != "YES" ]]; then
    emit "status=FAIL phase=fault_injection reason=missing_confirmation"
    emit "rerun=REL35_FAULT_MODE=ec2-az-loss CONFIRM_REL35_AZ_LOSS=YES make rel35-drill"
    exit 64
  fi

  emit "fault_mode=ec2-az-loss"
  emit "guardrail=Before running this mode, block Karpenter Spot replacement in target_az=$target_az through the temporary reviewed Terraform/GitOps change."

  if (( ${#TARGET_ONDEMAND_INSTANCES[@]} > 0 )); then
    emit "action=aws_ec2_stop_instances target_az=$target_az instances=${TARGET_ONDEMAND_INSTANCES[*]}"
    aws_cli ec2 stop-instances --instance-ids "${TARGET_ONDEMAND_INSTANCES[@]}" 2>&1 | tee -a "$REL35_OUTPUT"
    STOPPED_INSTANCES=("${TARGET_ONDEMAND_INSTANCES[@]}")
  else
    emit "action=aws_ec2_stop_instances skipped=true reason=no_ondemand_instances"
  fi

  if (( ${#TARGET_SPOT_INSTANCES[@]} > 0 )); then
    emit "action=aws_ec2_terminate_instances target_az=$target_az instances=${TARGET_SPOT_INSTANCES[*]}"
    aws_cli ec2 terminate-instances --instance-ids "${TARGET_SPOT_INSTANCES[@]}" 2>&1 | tee -a "$REL35_OUTPUT"
    TERMINATED_SPOT_INSTANCES=("${TARGET_SPOT_INSTANCES[@]}")
  else
    emit "action=aws_ec2_terminate_instances skipped=true reason=no_spot_instances"
  fi

  emit "status=PASS phase=fault_injection detail=stop_ondemand_terminate_spot_requested"
}

recover_if_needed() {
  if [[ "${REL35_FAULT_MODE:-}" != "ec2-az-loss" ]]; then
    return
  fi
  if [[ "${REL35_AUTO_RECOVER:-true}" != "true" ]]; then
    emit "auto_recover=false skipped=true"
    return
  fi
  if (( ${#STOPPED_INSTANCES[@]} == 0 )); then
    return
  fi

  section "auto_recover"
  emit "action=aws_ec2_start_instances instances=${STOPPED_INSTANCES[*]}"
  aws_cli ec2 start-instances --instance-ids "${STOPPED_INSTANCES[@]}" 2>&1 | tee -a "$REL35_OUTPUT" || true
  emit "action=aws_ec2_wait_instance_running instances=${STOPPED_INSTANCES[*]}"
  aws_cli ec2 wait instance-running --instance-ids "${STOPPED_INSTANCES[@]}" 2>&1 | tee -a "$REL35_OUTPUT" || true
  emit "status=COMPLETE phase=auto_recover"
}

run_observation_window() {
  section "observation_window"
  AWS_PROFILE="$AWS_PROFILE" \
  EXPECTED_AWS_ACCOUNT_ID="$EXPECTED_AWS_ACCOUNT_ID" \
  EXPECTED_KUBE_CONTEXT="$EXPECTED_KUBE_CONTEXT" \
  KUBE_NAMESPACE="$APP_NAMESPACE" \
  OBSERVABILITY_NAMESPACE="$OBSERVABILITY_NAMESPACE" \
    bash "$OBSERVER_SCRIPT" observe \
      --interval "$REL35_INTERVAL" \
      --duration "$REL35_OBSERVE_DURATION" \
      --output "$REL35_OUTPUT"
  emit "status=PASS phase=observation_window"
}

print_final_state() {
  section "final_state"
  run_logged kubectl get nodes -L topology.kubernetes.io/zone
  run_logged kubectl -n "$APP_NAMESPACE" get deploy,pods,hpa,pdb -o wide
  run_logged kubectl -n "$OBSERVABILITY_NAMESPACE" get deploy,pods -o wide
  emit "evidence_log=$REL35_OUTPUT"
  emit "status=COMPLETE phase=rel35_one_command_drill"
}

STOPPED_INSTANCES=()
TERMINATED_SPOT_INSTANCES=()
TARGET_NODES=()
TARGET_INSTANCES=()
TARGET_ONDEMAND_INSTANCES=()
TARGET_SPOT_INSTANCES=()
TARGET_AZ_SELECTED=""
trap recover_if_needed EXIT

section "start"
emit "rel35_drill_id=$REL35_DRILL_ID mode=$MODE fault_mode=$REL35_FAULT_MODE output=$REL35_OUTPUT"

require_commands
check_identity
run_observer_preflight
print_runtime_baseline

pick_target_az
collect_target_nodes_and_instances "$TARGET_AZ_SELECTED"
print_target_plan "$TARGET_AZ_SELECTED"

if [[ "$MODE" == "preflight" ]]; then
  emit "status=COMPLETE phase=preflight_only"
  exit 0
fi

inject_fault_if_requested "$TARGET_AZ_SELECTED"
run_observation_window
print_final_state
