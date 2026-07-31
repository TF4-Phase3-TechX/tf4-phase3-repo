#!/usr/bin/env bash
# D5-PERF-03 controlled, one-wave-at-a-time resource rollout.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHART="${CHART:-$ROOT/techx-corp-chart}"
WAVE_DIR="${WAVE_DIR:-$ROOT/deploy/resource-remediation}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVIDENCE_ROOT="${EVIDENCE_ROOT:-$ROOT/docs/evidence/directive-05/official-$RUN_ID/resource-rollout}"
VERIFY_SECONDS="${VERIFY_SECONDS:-600}"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-5m}"
PROM_URL="${PROM_URL:-}"
APP_BASE_VALUES="${APP_BASE_VALUES:-$ROOT/deploy/values-app-stamp.yaml}"
OBS_BASE_VALUES="${OBS_BASE_VALUES:-$ROOT/deploy/values-observability.yaml}"

declare -A FILE=( [low-risk-stateless]=01-low-risk-stateless.yaml [revenue-critical-stateless]=02-revenue-critical-stateless.yaml [stateful-messaging]=03-stateful-messaging.yaml [observability]=04-observability.yaml [remaining-exceptions]=05-remaining-exceptions.yaml )
declare -A NS=( [low-risk-stateless]=techx-tf4 [revenue-critical-stateless]=techx-tf4 [stateful-messaging]=techx-tf4 [observability]=techx-observability [remaining-exceptions]=techx-tf4 )
declare -A RELEASE=( [low-risk-stateless]=techx-corp [revenue-critical-stateless]=techx-corp [stateful-messaging]=techx-corp [observability]=techx-observability [remaining-exceptions]=techx-corp )
declare -A WORKLOADS=(
  [low-risk-stateless]="ad email image-provider recommendation product-reviews llm"
  [revenue-critical-stateless]="frontend-proxy frontend product-catalog cart checkout payment currency shipping quote"
  [stateful-messaging]="kafka postgresql valkey-cart accounting fraud-detection"
  [observability]=""
  [remaining-exceptions]="flagd load-generator"
)

usage() { echo "Usage: $0 <wave> [--execute] [--approve-window TICKET]"; echo "Waves: ${!FILE[*]}"; }
die() { echo "ERROR: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null || die "missing command: $1"; }

WAVE="${1:-}"; shift || true
[[ -n "${FILE[$WAVE]:-}" ]] || { usage; exit 2; }
EXECUTE=false; WINDOW=""
while (($#)); do
  case "$1" in
    --execute) EXECUTE=true ;;
    --approve-window) WINDOW="${2:-}"; shift ;;
    *) die "unknown argument: $1" ;;
  esac
  shift
done
[[ "$EXECUTE" == false || -n "$WINDOW" ]] || die "--execute requires --approve-window <ticket/window>"
NS_NAME="${NS[$WAVE]}"; RELEASE_NAME="${RELEASE[$WAVE]}"
OVERLAY="$WAVE_DIR/${FILE[$WAVE]}"; OUT="$EVIDENCE_ROOT/$WAVE"
mkdir -p "$OUT/raw"
[[ -s "$OVERLAY" ]] || die "reviewed D5-02 overlay missing: $OVERLAY"
for tool in kubectl helm jq curl; do need "$tool"; done
kubectl auth can-i get deployments -n "$NS_NAME" | grep -qx yes || die "no deployment read access in $NS_NAME"
helm status "$RELEASE_NAME" -n "$NS_NAME" >/dev/null || die "release $RELEASE_NAME not found in $NS_NAME"

capture() {
  local label="$1"
  kubectl get pods -n "$NS_NAME" -o wide >"$OUT/raw/$label-pods.txt"
  kubectl get events -n "$NS_NAME" --sort-by=.lastTimestamp >"$OUT/raw/$label-events.txt"
  kubectl get deployments -n "$NS_NAME" -o json >"$OUT/raw/$label-deployments.json"
  kubectl get hpa -n "$NS_NAME" -o yaml >"$OUT/raw/$label-hpa.yaml" 2>&1 || true
  kubectl top pods -n "$NS_NAME" --containers >"$OUT/raw/$label-top.txt" 2>&1 || true
  helm get values "$RELEASE_NAME" -n "$NS_NAME" -a -o yaml >"$OUT/raw/$label-helm-values.yaml"
}

bad_pods() {
  kubectl get pods -n "$NS_NAME" -o json | jq -e '[.items[] | select(.status.phase == "Pending" or any(.status.containerStatuses[]?; (.state.waiting.reason // "") | test("CrashLoopBackOff|CreateContainerError|RunContainerError")))] | length > 0' >/dev/null
}

oom_total() {
  kubectl get pods -n "$NS_NAME" -o json | jq '[.items[].status.containerStatuses[]? | select(.lastState.terminated.reason == "OOMKilled" or .state.terminated.reason == "OOMKilled")] | length'
}

prom_query() {
  local query="$1" file="$2"
  if [[ -z "$PROM_URL" ]]; then
    printf '{"status":"skipped","reason":"PROM_URL not set"}\n' >"$file"
  else
    curl -fsSG "$PROM_URL/api/v1/query" --data-urlencode "query=$query" >"$file"
  fi
}

capture before
BASE_REV="$(helm history "$RELEASE_NAME" -n "$NS_NAME" -o json | jq -r 'map(select(.status=="deployed")) | last.revision')"
OOM_BEFORE="$(oom_total)"
printf 'run_id=%s\nwave=%s\nwindow=%s\nrelease=%s\nnamespace=%s\nrollback_revision=%s\n' "$RUN_ID" "$WAVE" "$WINDOW" "$RELEASE_NAME" "$NS_NAME" "$BASE_REV" >"$OUT/metadata.txt"
prom_query 'sum(rate(container_cpu_cfs_throttled_periods_total[5m])) / clamp_min(sum(rate(container_cpu_cfs_periods_total[5m])), 1)' "$OUT/raw/before-throttling.json"
prom_query 'histogram_quantile(0.95, sum by (le, service_name) (rate(traces_span_metrics_duration_milliseconds_bucket{service_name=~"frontend|cart|checkout"}[5m])))' "$OUT/raw/before-slo-p95.json"
bad_pods && die "preflight failed: Pending/CrashLoop pod exists"

BASE_VALUES="$APP_BASE_VALUES"; [[ "$WAVE" == observability ]] && BASE_VALUES="$OBS_BASE_VALUES"
CMD=(helm upgrade "$RELEASE_NAME" "$CHART" -n "$NS_NAME" --reuse-values -f "$BASE_VALUES" -f "$OVERLAY" --atomic --timeout "$ROLLOUT_TIMEOUT")
printf '%q ' "${CMD[@]}" >"$OUT/apply-command.txt"; echo >>"$OUT/apply-command.txt"
echo "helm rollback $RELEASE_NAME $BASE_REV -n $NS_NAME --wait --timeout $ROLLOUT_TIMEOUT" >"$OUT/rollback-command.txt"

if [[ "$EXECUTE" == false ]]; then
  "${CMD[@]}" --dry-run=server >"$OUT/raw/server-dry-run.txt"
  echo "DRY RUN PASS. Re-run with --execute --approve-window <ticket>. Evidence: $OUT"
  exit 0
fi

"${CMD[@]}" 2>&1 | tee "$OUT/raw/helm-upgrade.txt"
for deployment in ${WORKLOADS[$WAVE]}; do
  kubectl rollout status "deployment/$deployment" -n "$NS_NAME" --timeout="$ROLLOUT_TIMEOUT" | tee -a "$OUT/raw/rollout-status.txt"
done

deadline=$((SECONDS + VERIFY_SECONDS))
while ((SECONDS < deadline)); do
  if bad_pods || (( $(oom_total) > OOM_BEFORE )); then
    capture failed
    helm rollback "$RELEASE_NAME" "$BASE_REV" -n "$NS_NAME" --wait --timeout "$ROLLOUT_TIMEOUT"
    die "guardrail failed; release rolled back"
  fi
  sleep 30
done

capture after
prom_query 'sum(rate(container_cpu_cfs_throttled_periods_total[5m])) / clamp_min(sum(rate(container_cpu_cfs_periods_total[5m])), 1)' "$OUT/raw/after-throttling.json"
prom_query 'histogram_quantile(0.95, sum by (le, service_name) (rate(traces_span_metrics_duration_milliseconds_bucket{service_name=~"frontend|cart|checkout"}[5m])))' "$OUT/raw/after-slo-p95.json"
cat >"$OUT/verdict.md" <<EOF
# D5-PERF-03 wave verdict: $WAVE

- Change window: \`$WINDOW\`
- Helm rollback revision: \`$BASE_REV\`
- Verification duration: \`${VERIFY_SECONDS}s\`
- Pending/CrashLoop/new OOM guardrails: PASS
- CPU throttling and Browse/Cart/Checkout SLO: reviewer sign-off required from before/after JSON.
- Verdict: TECHNICAL GUARDRAILS PASS; PERFORMANCE REVIEW PENDING
EOF
echo "Guardrails passed. Wait for performance sign-off before the next wave: $OUT"
