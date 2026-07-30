#!/usr/bin/env bash
set -uo pipefail

MODE="${MODE:-preflight}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-30}"
DURATION_SECONDS="${DURATION_SECONDS:-0}"
OUTPUT_FILE="${OUTPUT_FILE:-rel33-az-loss-$(date -u +%Y%m%dT%H%M%SZ).log}"
AWS_PROFILE="${AWS_PROFILE:-default}"
AWS_REGION="${AWS_REGION:-us-east-1}"
EXPECTED_AWS_ACCOUNT_ID="${EXPECTED_AWS_ACCOUNT_ID:-}"
EXPECTED_KUBE_CONTEXT="${EXPECTED_KUBE_CONTEXT:-}"
KUBE_NAMESPACE="${KUBE_NAMESPACE:-techx-tf4}"
OBSERVABILITY_NAMESPACE="${OBSERVABILITY_NAMESPACE:-techx-observability}"
RDS_IDENTIFIER="${RDS_IDENTIFIER:-techx-tf4-postgresql}"
VALKEY_REPLICATION_GROUP_ID="${VALKEY_REPLICATION_GROUP_ID:-techx-tf4-valkey-cart}"
MSK_CLUSTER_NAME="${MSK_CLUSTER_NAME:-techx-tf4-orders}"

# Expected baseline from REL-32; update these lists if classification changes.
REQUIRED_DEPLOYMENTS="${REQUIRED_DEPLOYMENTS:-frontend-proxy frontend product-catalog cart checkout payment shipping currency quote}"
REQUIRED_TWO_AZ_DEPLOYMENTS="${REQUIRED_TWO_AZ_DEPLOYMENTS:-frontend-proxy frontend product-catalog cart checkout payment shipping currency quote}"
REQUIRED_PDBS="${REQUIRED_PDBS:-frontend-proxy frontend product-catalog cart checkout payment shipping currency quote}"
LOAD_GENERATOR_DEPLOYMENT="${LOAD_GENERATOR_DEPLOYMENT:-load-generator}"

BROWSE_SLO_MIN="${BROWSE_SLO_MIN:-99.5}"
CART_SLO_MIN="${CART_SLO_MIN:-99.5}"
CHECKOUT_SLO_MIN="${CHECKOUT_SLO_MIN:-99.0}"
MIN_REQUEST_RATE="${MIN_REQUEST_RATE:-0.01}"

BROWSE_QUERY='100 * sum(rate(traces_span_metrics_calls_total{service_name="frontend",span_kind="SPAN_KIND_SERVER",span_name=~"GET /|GET /product.*|GET /api/products.*|GET /api/data.*",status_code!="STATUS_CODE_ERROR"}[5m])) / sum(rate(traces_span_metrics_calls_total{service_name="frontend",span_kind="SPAN_KIND_SERVER",span_name=~"GET /|GET /product.*|GET /api/products.*|GET /api/data.*"}[5m]))'
CART_QUERY='100 * sum(rate(traces_span_metrics_calls_total{service_name="frontend",span_kind="SPAN_KIND_SERVER",span_name=~"(GET|POST|DELETE) /api/cart",status_code!="STATUS_CODE_ERROR"}[5m])) / sum(rate(traces_span_metrics_calls_total{service_name="frontend",span_kind="SPAN_KIND_SERVER",span_name=~"(GET|POST|DELETE) /api/cart"}[5m]))'
CHECKOUT_QUERY='100 * sum(rate(traces_span_metrics_calls_total{service_name="frontend",span_kind="SPAN_KIND_SERVER",span_name="POST /api/checkout",status_code!="STATUS_CODE_ERROR"}[5m])) / sum(rate(traces_span_metrics_calls_total{service_name="frontend",span_kind="SPAN_KIND_SERVER",span_name="POST /api/checkout"}[5m]))'
REQUEST_RATE_QUERY='sum(rate(traces_span_metrics_calls_total{service_name="frontend",span_kind="SPAN_KIND_SERVER"}[5m]))'

PREFLIGHT_FAILURES=0
HARD_STOP_FAILURES=0
MSK_CLUSTER_ARN=""
STOP_REQUESTED=false
BROWSE_DIP_ACTIVE=false
CART_DIP_ACTIVE=false
CHECKOUT_DIP_ACTIVE=false

usage() {
  cat <<'EOF'
Usage:
  rel33-az-loss-observer.sh preflight [options]
  rel33-az-loss-observer.sh observe [options]

Options:
  --interval SECONDS   Observer interval (default: 30)
  --duration SECONDS   Stop after this duration; 0 means until Ctrl+C
  --output FILE        Evidence log path

Exit codes:
  0  GO / observer completed without hard-stop
  2  NO-GO preflight
  3  Observer hard-stop
  64 Invalid input
EOF
}

while (( $# > 0 )); do
  case "$1" in
    preflight|observe) MODE="$1"; shift ;;
    --interval) INTERVAL_SECONDS="${2:-}"; shift 2 ;;
    --duration) DURATION_SECONDS="${2:-}"; shift 2 ;;
    --output) OUTPUT_FILE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 64 ;;
  esac
done

[[ "$MODE" == preflight || "$MODE" == observe ]] || {
  echo "MODE must be preflight or observe" >&2
  exit 64
}
[[ "$INTERVAL_SECONDS" =~ ^[1-9][0-9]*$ ]] || {
  echo "INTERVAL_SECONDS must be positive" >&2
  exit 64
}
[[ "$DURATION_SECONDS" =~ ^[0-9]+$ ]] || {
  echo "DURATION_SECONDS must be zero or positive" >&2
  exit 64
}
[[ -n "$EXPECTED_AWS_ACCOUNT_ID" && -n "$EXPECTED_KUBE_CONTEXT" ]] || {
  echo "Set EXPECTED_AWS_ACCOUNT_ID and EXPECTED_KUBE_CONTEXT" >&2
  exit 64
}

mkdir -p "$(dirname "$OUTPUT_FILE")"
touch "$OUTPUT_FILE"
chmod 600 "$OUTPUT_FILE" 2>/dev/null || true

timestamp() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
emit() { printf '%s\n' "$*" | tee -a "$OUTPUT_FILE"; }
section() {
  emit ""
  emit "=== $1 timestamp=$(timestamp) ==="
}
gate_pass() { emit "gate=$1 status=PASS detail=$2"; }
gate_fail() {
  emit "gate=$1 status=FAIL detail=$2 remediation_item=$3"
  PREFLIGHT_FAILURES=$((PREFLIGHT_FAILURES + 1))
}
hard_stop() {
  emit "hard_stop=$1 status=TRIGGERED detail=$2 remediation_item=$3"
  HARD_STOP_FAILURES=$((HARD_STOP_FAILURES + 1))
}
aws_cli() { aws --profile "$AWS_PROFILE" --region "$AWS_REGION" "$@"; }

require_commands() {
  local command
  for command in aws kubectl awk sed grep sort tee date; do
    command -v "$command" >/dev/null 2>&1 || {
      emit "gate=local_dependency status=FAIL detail=missing_$command"
      exit 64
    }
  done
}

check_identity() {
  local account context
  account="$(aws --profile "$AWS_PROFILE" sts get-caller-identity \
    --query Account --output text 2>/dev/null || true)"
  context="$(kubectl config current-context 2>/dev/null || true)"
  if [[ "$account" == "$EXPECTED_AWS_ACCOUNT_ID" ]]; then
    gate_pass aws_account "$account"
  else
    gate_fail aws_account "actual=${account:-unavailable}" "Login_to_expected_AWS_account"
  fi
  if [[ "$context" == "$EXPECTED_KUBE_CONTEXT" ]]; then
    gate_pass kube_context "$context"
  else
    gate_fail kube_context "actual=${context:-unavailable}" "Switch_to_expected_EKS_context"
  fi
}

pod_health_rows() {
  kubectl get pods -n "$KUBE_NAMESPACE" -o jsonpath \
    '{range .items[*]}{.metadata.name}{"|"}{.status.phase}{"|"}{range .status.containerStatuses[*]}{.ready}{","}{.state.waiting.reason}{","}{.lastState.terminated.reason}{";"}{end}{"\n"}{end}' \
    2>/dev/null
}

check_pods() {
  local rows bad
  rows="$(pod_health_rows)"
  emit "$rows"
  bad="$(printf '%s\n' "$rows" | awk -F'|' '
    $2 == "Pending" { print; next }
    $2 != "Succeeded" && $3 ~ /(CrashLoopBackOff|CreateContainerConfigError|ImagePullBackOff|ErrImagePull|OOMKilled)/ { print; next }
    $2 == "Running" && $3 ~ /false/ { print }
  ')"
  if [[ -z "$bad" ]]; then
    gate_pass pod_health "no_pending_or_unhealthy_runtime_pods"
  else
    gate_fail pod_health "$(printf '%s' "$bad" | tr '\n' ',')" "Resolve_Pending_CrashLoop_OOM_or_readiness"
  fi
}

check_required_deployments() {
  local deployment desired ready available
  for deployment in $REQUIRED_DEPLOYMENTS; do
    read -r desired ready available <<<"$(kubectl get deployment "$deployment" \
      -n "$KUBE_NAMESPACE" \
      -o jsonpath='{.spec.replicas}{" "}{.status.readyReplicas}{" "}{.status.availableReplicas}' \
      2>/dev/null || true)"
    ready="${ready:-0}"
    available="${available:-0}"
    if [[ "$desired" =~ ^[1-9][0-9]*$ &&
          "$ready" == "$desired" && "$available" == "$desired" ]]; then
      gate_pass "deployment_$deployment" "desired=$desired ready=$ready available=$available"
    else
      gate_fail "deployment_$deployment" \
        "desired=${desired:-missing} ready=$ready available=$available" \
        "Restore_required_deployment_readiness"
    fi
  done
}

check_az_spread() {
  local deployment zones zone_count
  for deployment in $REQUIRED_TWO_AZ_DEPLOYMENTS; do
    zones="$(kubectl get pods -n "$KUBE_NAMESPACE" \
      -l "opentelemetry.io/name=$deployment" \
      -o jsonpath='{range .items[?(@.status.phase=="Running")]}{.spec.nodeName}{"\n"}{end}' \
      2>/dev/null | while read -r node; do
        [[ -n "$node" ]] && kubectl get node "$node" \
          -o jsonpath='{.metadata.labels.topology\.kubernetes\.io/zone}{"\n"}' 2>/dev/null
      done | sort -u)"
    zone_count="$(printf '%s\n' "$zones" | grep -c . || true)"
    if (( zone_count >= 2 )); then
      gate_pass "az_spread_$deployment" "zones=$(printf '%s' "$zones" | tr '\n' ',')"
    else
      gate_fail "az_spread_$deployment" \
        "zones=${zones:-none}" "REL32_spread_required_workload_across_two_AZs"
    fi
  done
}

check_hpa() {
  local name current desired able active failures=0 rows
  rows="$(kubectl get hpa -n "$KUBE_NAMESPACE" \
    -o jsonpath='{range .items[*]}{.metadata.name}{"|"}{.status.currentReplicas}{"|"}{.status.desiredReplicas}{"|"}{range .status.conditions[?(@.type=="AbleToScale")]}{.status}{end}{"|"}{range .status.conditions[?(@.type=="ScalingActive")]}{.status}{end}{"\n"}{end}' \
    2>/dev/null)"
  emit "$rows"
  while IFS='|' read -r name current desired able active; do
    [[ -z "$name" ]] && continue
    if [[ "$current" != "$desired" || "$able" != True || "$active" != True ]]; then
      failures=$((failures + 1))
    fi
  done <<<"$rows"
  if (( failures == 0 )) && [[ -n "$rows" ]]; then
    gate_pass hpa_stable "all_current_equal_desired_and_conditions_true"
  else
    gate_fail hpa_stable "unstable_hpa_count=$failures" "Wait_for_HPA_to_stabilize"
  fi
}

check_pdb() {
  local pdb allowed
  for pdb in $REQUIRED_PDBS; do
    allowed="$(kubectl get pdb "$pdb" -n "$KUBE_NAMESPACE" \
      -o jsonpath='{.status.disruptionsAllowed}' 2>/dev/null || true)"
    if [[ "$allowed" =~ ^[1-9][0-9]*$ ]]; then
      gate_pass "pdb_$pdb" "disruptionsAllowed=$allowed"
    else
      gate_fail "pdb_$pdb" "disruptionsAllowed=${allowed:-missing}" \
        "Create_or_restore_PDB_headroom"
    fi
  done
}

check_quota() {
  local rows exhausted
  rows="$(kubectl get resourcequota -n "$KUBE_NAMESPACE" \
    -o jsonpath='{range .items[*]}{.metadata.name}{"|pods="}{.status.used.pods}{"/"}{.status.hard.pods}{"|requests.cpu="}{.status.used.requests\.cpu}{"/"}{.status.hard.requests\.cpu}{"|requests.memory="}{.status.used.requests\.memory}{"/"}{.status.hard.requests\.memory}{"|limits.cpu="}{.status.used.limits\.cpu}{"/"}{.status.hard.limits\.cpu}{"|limits.memory="}{.status.used.limits\.memory}{"/"}{.status.hard.limits\.memory}{"\n"}{end}' \
    2>/dev/null || true)"
  emit "$rows"
  exhausted="$(printf '%s\n' "$rows" | tr '|' '\n' |
    awk -F'[=/]' 'NF >= 3 && $2 == $3 {print $0}')"
  if [[ -n "$rows" && -z "$exhausted" ]]; then
    gate_pass resource_quota "exists_and_no_resource_equals_hard_limit"
  else
    gate_fail resource_quota "exhausted=${exhausted:-quota_missing}" \
      "Free_or_increase_quota_before_drill"
  fi
}

check_load_generator() {
  local desired ready available
  read -r desired ready available <<<"$(kubectl get deployment "$LOAD_GENERATOR_DEPLOYMENT" \
    -n "$KUBE_NAMESPACE" \
    -o jsonpath='{.spec.replicas}{" "}{.status.readyReplicas}{" "}{.status.availableReplicas}' \
    2>/dev/null || true)"
  if [[ "${desired:-0}" -ge 1 && "$ready" == "$desired" && "$available" == "$desired" ]]; then
    gate_pass load_generator "desired=$desired ready=$ready"
  else
    gate_fail load_generator \
      "desired=${desired:-missing} ready=${ready:-0} available=${available:-0}" \
      "Restore_load_generator_before_drill"
  fi
}

prometheus_query() {
  local query="$1"
  local response
  response="$(kubectl exec -n "$OBSERVABILITY_NAMESPACE" deployment/prometheus \
    -c prometheus-server -- wget -qO- \
    --post-data="query=$query" \
    http://127.0.0.1:9090/api/v1/query 2>/dev/null || true)"
  [[ "$response" == *'"status":"success"'* &&
     "$response" != *'"result":[]'* ]] || return 1
  printf '%s' "$response" | sed -n \
    's/.*"value":\[[^,]*,"\([^"]*\)"\].*/\1/p' | tail -1
}

float_ge() { awk -v actual="$1" -v expected="$2" 'BEGIN {exit !(actual >= expected)}'; }

observe_slo_state() {
  local surface="$1"
  local actual="$2"
  local minimum="$3"
  local state_variable="$4"
  local active="${!state_variable}"
  if float_ge "$actual" "$minimum"; then
    if [[ "$active" == true ]]; then
      emit "slo_recovered surface=$surface actual=$actual minimum=$minimum timestamp=$(timestamp)"
      printf -v "$state_variable" '%s' false
    else
      emit "slo_observation surface=$surface status=HEALTHY actual=$actual minimum=$minimum"
    fi
  else
    if [[ "$active" == false ]]; then
      emit "slo_dip_detected surface=$surface actual=$actual minimum=$minimum timestamp=$(timestamp)"
      printf -v "$state_variable" '%s' true
    else
      emit "slo_observation surface=$surface status=BELOW_THRESHOLD actual=$actual minimum=$minimum"
    fi
  fi
}

check_metrics_and_slo() {
  local check_mode="${1:-preflight}"
  local request_rate browse cart checkout
  request_rate="$(prometheus_query "$REQUEST_RATE_QUERY" || true)"
  browse="$(prometheus_query "$BROWSE_QUERY" || true)"
  cart="$(prometheus_query "$CART_QUERY" || true)"
  checkout="$(prometheus_query "$CHECKOUT_QUERY" || true)"

  if [[ -n "$request_rate" && -n "$browse" && -n "$cart" && -n "$checkout" ]]; then
    gate_pass metrics_available \
      "request_rate=$request_rate browse=$browse cart=$cart checkout=$checkout"
  else
    gate_fail metrics_available \
      "request_rate=${request_rate:-missing} browse=${browse:-missing} cart=${cart:-missing} checkout=${checkout:-missing}" \
      "Restore_Prometheus_span_metrics"
    return
  fi

  if float_ge "$request_rate" "$MIN_REQUEST_RATE"; then
    gate_pass request_volume "rate=$request_rate minimum=$MIN_REQUEST_RATE"
  else
    gate_fail request_volume "rate=$request_rate minimum=$MIN_REQUEST_RATE" \
      "Restore_real_load_before_drill"
  fi
  if [[ "$check_mode" == observe ]]; then
    observe_slo_state browse "$browse" "$BROWSE_SLO_MIN" BROWSE_DIP_ACTIVE
    observe_slo_state cart "$cart" "$CART_SLO_MIN" CART_DIP_ACTIVE
    observe_slo_state checkout "$checkout" "$CHECKOUT_SLO_MIN" CHECKOUT_DIP_ACTIVE
    return
  fi

  float_ge "$browse" "$BROWSE_SLO_MIN" \
    && gate_pass browse_slo "actual=$browse minimum=$BROWSE_SLO_MIN" \
    || gate_fail browse_slo "actual=$browse minimum=$BROWSE_SLO_MIN" \
      "Recover_browse_baseline"
  float_ge "$cart" "$CART_SLO_MIN" \
    && gate_pass cart_slo "actual=$cart minimum=$CART_SLO_MIN" \
    || gate_fail cart_slo "actual=$cart minimum=$CART_SLO_MIN" \
      "Recover_cart_baseline"
  float_ge "$checkout" "$CHECKOUT_SLO_MIN" \
    && gate_pass checkout_slo "actual=$checkout minimum=$CHECKOUT_SLO_MIN" \
    || gate_fail checkout_slo "actual=$checkout minimum=$CHECKOUT_SLO_MIN" \
      "Recover_checkout_baseline"
}

check_dashboards() {
  local grafana_ready prometheus_ready
  grafana_ready="$(kubectl get endpointslice -n "$OBSERVABILITY_NAMESPACE" \
    -l kubernetes.io/service-name=grafana \
    -o jsonpath='{range .items[*].endpoints[?(@.conditions.ready==true)]}{.addresses[0]}{" "}{end}' \
    2>/dev/null || true)"
  prometheus_ready="$(kubectl get endpointslice -n "$OBSERVABILITY_NAMESPACE" \
    -l kubernetes.io/service-name=prometheus \
    -o jsonpath='{range .items[*].endpoints[?(@.conditions.ready==true)]}{.addresses[0]}{" "}{end}' \
    2>/dev/null || true)"
  if [[ -n "$grafana_ready" && -n "$prometheus_ready" ]]; then
    gate_pass dashboards_accessible \
      "grafana_endpoints=$grafana_ready prometheus_endpoints=$prometheus_ready"
  else
    gate_fail dashboards_accessible \
      "grafana=${grafana_ready:-missing} prometheus=${prometheus_ready:-missing}" \
      "Restore_Grafana_and_Prometheus_endpoints"
  fi
}

resolve_msk_arn() {
  MSK_CLUSTER_ARN="$(aws_cli kafka list-clusters-v2 \
    --cluster-name-filter "$MSK_CLUSTER_NAME" \
    --query 'ClusterInfoList[0].ClusterArn' --output text 2>/dev/null || true)"
  [[ "$MSK_CLUSTER_ARN" == arn:aws:kafka:* ]] || MSK_CLUSTER_ARN=""
}

check_managed_stores() {
  local rds valkey msk
  rds="$(aws_cli rds describe-db-instances \
    --db-instance-identifier "$RDS_IDENTIFIER" \
    --query 'DBInstances[0].[DBInstanceStatus,MultiAZ]' \
    --output text 2>/dev/null || true)"
  valkey="$(aws_cli elasticache describe-replication-groups \
    --replication-group-id "$VALKEY_REPLICATION_GROUP_ID" \
    --query 'ReplicationGroups[0].[Status,MultiAZ,AutomaticFailover]' \
    --output text 2>/dev/null || true)"
  [[ -n "$MSK_CLUSTER_ARN" ]] || resolve_msk_arn
  msk="$(aws_cli kafka describe-cluster-v2 --cluster-arn "$MSK_CLUSTER_ARN" \
    --query 'ClusterInfo.State' --output text 2>/dev/null || true)"
  emit "managed_store=RDS identifier=$RDS_IDENTIFIER state=$rds"
  emit "managed_store=Valkey identifier=$VALKEY_REPLICATION_GROUP_ID state=$valkey"
  emit "managed_store=MSK name=$MSK_CLUSTER_NAME state=$msk"

  [[ "$rds" == available$'\t'True ]] \
    && gate_pass rds_health "status=available multi_az=true" \
    || gate_fail rds_health "actual=${rds:-missing}" "Escalate_RDS_unhealthy"
  [[ "$valkey" == available$'\t'enabled$'\t'enabled ]] \
    && gate_pass valkey_health "status=available multi_az=enabled failover=enabled" \
    || gate_fail valkey_health "actual=${valkey:-missing}" "Escalate_Valkey_unhealthy"
  [[ "$msk" == ACTIVE ]] \
    && gate_pass msk_health "status=ACTIVE" \
    || gate_fail msk_health "actual=${msk:-missing}" "Escalate_MSK_unhealthy"
}

pod_placement_by_az() {
  local name phase ready pod_node restarts pod_zone node_zone_map
  node_zone_map="$(kubectl get nodes \
    -o jsonpath='{range .items[*]}{.metadata.name}{"|"}{.metadata.labels.topology\.kubernetes\.io/zone}{"\n"}{end}' \
    2>/dev/null || true)"

  printf '%-48s %-10s %-12s %-36s %-14s %s\n' \
    NAME PHASE READY NODE AZ RESTARTS
  while IFS='|' read -r name phase ready pod_node restarts; do
    [[ -z "$name" ]] && continue
    if [[ -n "$pod_node" ]]; then
      pod_zone="$(printf '%s\n' "$node_zone_map" | awk -F'|' -v node="$pod_node" '$1 == node { print $2; found=1; exit } END { if (!found) print "<unknown>" }')"
    else
      pod_zone="<unscheduled>"
      pod_node="<none>"
    fi
    printf '%-48s %-10s %-12s %-36s %-14s %s\n' \
      "$name" "$phase" "$ready" "$pod_node" "$pod_zone" "$restarts"
  done < <(kubectl get pods -n "$KUBE_NAMESPACE" \
    -o jsonpath='{range .items[*]}{.metadata.name}{"|"}{.status.phase}{"|"}{.status.containerStatuses[*].ready}{"|"}{.spec.nodeName}{"|"}{.status.containerStatuses[*].restartCount}{"\n"}{end}' \
    2>/dev/null)
}

collect_snapshot() {
  section nodes_by_az
  kubectl get nodes \
    -L topology.kubernetes.io/zone,karpenter.sh/capacity-type \
    -o wide 2>&1 | tee -a "$OUTPUT_FILE"

  section pods_by_az
  pod_placement_by_az | tee -a "$OUTPUT_FILE"

  section hpa
  kubectl get hpa -n "$KUBE_NAMESPACE" -o wide 2>&1 | tee -a "$OUTPUT_FILE"
  section pdb
  kubectl get pdb -n "$KUBE_NAMESPACE" -o wide 2>&1 | tee -a "$OUTPUT_FILE"
  section resource_quota
  kubectl describe resourcequota -n "$KUBE_NAMESPACE" 2>&1 | tee -a "$OUTPUT_FILE"
  section warning_events
  kubectl get events -n "$KUBE_NAMESPACE" \
    --field-selector type=Warning --sort-by=.lastTimestamp 2>&1 | tail -40 | tee -a "$OUTPUT_FILE"
  section managed_stores
  check_managed_stores
}

run_preflight() {
  PREFLIGHT_FAILURES=0
  section preflight_start
  check_identity
  check_pods
  check_required_deployments
  check_az_spread
  check_hpa
  check_pdb
  check_quota
  check_load_generator
  check_dashboards
  check_metrics_and_slo preflight
  check_managed_stores
  collect_snapshot
  if (( PREFLIGHT_FAILURES == 0 )); then
    emit "preflight_result=GO failures=0 timestamp=$(timestamp)"
    return 0
  fi
  emit "preflight_result=NO-GO failures=$PREFLIGHT_FAILURES timestamp=$(timestamp)"
  return 2
}

observer_hard_stop_check() {
  local before_failures rows bad desired ready available
  before_failures="$PREFLIGHT_FAILURES"
  PREFLIGHT_FAILURES=0

  rows="$(pod_health_rows)"
  bad="$(printf '%s\n' "$rows" | awk -F'|' '
    $2 == "Pending" {print; next}
    $2 != "Succeeded" && $3 ~ /(CrashLoopBackOff|CreateContainerConfigError|ImagePullBackOff|ErrImagePull|OOMKilled)/ {print}
  ')"
  [[ -z "$bad" ]] || hard_stop pod_runtime \
    "$(printf '%s' "$bad" | tr '\n' ',')" "Pause_drill_and_restore_workload"

  read -r desired ready available <<<"$(kubectl get deployment "$LOAD_GENERATOR_DEPLOYMENT" \
    -n "$KUBE_NAMESPACE" \
    -o jsonpath='{.spec.replicas}{" "}{.status.readyReplicas}{" "}{.status.availableReplicas}' \
    2>/dev/null || true)"
  [[ "${ready:-0}" == "${desired:-missing}" && "${available:-0}" == "${desired:-missing}" ]] \
    || hard_stop load_generator \
      "desired=${desired:-missing} ready=${ready:-0}" "Restore_load_or_stop_RTO_measurement"

  check_metrics_and_slo observe
  check_managed_stores
  if (( PREFLIGHT_FAILURES > 0 )); then
    hard_stop gates "runtime_gate_failures=$PREFLIGHT_FAILURES" \
      "Pause_drill_and_follow_escalation_path"
  fi
  PREFLIGHT_FAILURES="$before_failures"
}

run_observer() {
  local started now_elapsed iteration=0
  started="$(date +%s)"
  section observer_start
  emit "observer_started mode=observe interval_seconds=$INTERVAL_SECONDS duration_seconds=$DURATION_SECONDS"
  PREFLIGHT_FAILURES=0
  check_identity
  if (( PREFLIGHT_FAILURES > 0 )); then
    hard_stop identity "account_or_context_mismatch" "Switch_to_expected_identity"
    emit "observer_result=HARD-STOP failures=$HARD_STOP_FAILURES timestamp=$(timestamp)"
    return 3
  fi
  while true; do
    if [[ "$STOP_REQUESTED" == true ]]; then
      emit "observer_result=INTERRUPTED hard_stops=$HARD_STOP_FAILURES timestamp=$(timestamp)"
      return 0
    fi
    iteration=$((iteration + 1))
    section "observer_iteration_$iteration"
    collect_snapshot
    observer_hard_stop_check
    if (( HARD_STOP_FAILURES > 0 )); then
      emit "observer_result=HARD-STOP failures=$HARD_STOP_FAILURES timestamp=$(timestamp)"
      return 3
    fi
    now_elapsed=$(( $(date +%s) - started ))
    emit "observer_iteration=$iteration status=CONTINUE elapsed_seconds=$now_elapsed"
    if (( DURATION_SECONDS > 0 && now_elapsed >= DURATION_SECONDS )); then
      emit "observer_result=COMPLETE hard_stops=0 elapsed_seconds=$now_elapsed timestamp=$(timestamp)"
      return 0
    fi
    sleep "$INTERVAL_SECONDS"
  done
}

trap 'STOP_REQUESTED=true; emit "observer_signal=INTERRUPTED timestamp=$(timestamp)"' INT TERM
require_commands
emit "rel33_observer_version=1 mode=$MODE output=$OUTPUT_FILE started_at=$(timestamp)"

if [[ "$MODE" == preflight ]]; then
  run_preflight
  exit $?
fi

run_observer
exit $?
