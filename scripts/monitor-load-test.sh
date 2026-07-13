#!/usr/bin/env bash
# Monitor Task-4 load test and stop early on guardrails.
set -euo pipefail

NAMESPACE="${NAMESPACE:-techx-tf4}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-30}"

if command -v kubectl >/dev/null 2>&1; then
  KUBECTL_BIN="$(command -v kubectl)"
elif command -v kubectl.exe >/dev/null 2>&1; then
  KUBECTL_BIN="$(command -v kubectl.exe)"
else
  echo "ERROR: kubectl not found. Install kubectl or add it to PATH before running this monitor script."
  exit 1
fi
LOG_FILE="${LOG_FILE:-docs/evidence/epic-03-performance-efficiency/runtime/load-test-monitor-$(date -u +%Y%m%dT%H%M%SZ).log}"
mkdir -p "$(dirname "$LOG_FILE")"
: > "$LOG_FILE"

"$KUBECTL_BIN" cluster-info >/dev/null 2>&1 || {
  echo "ERROR: kubectl is installed but cannot reach the Kubernetes API. Configure kubeconfig or connect to the target cluster first."
  exit 1
}

while true; do
  timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  echo "[$timestamp] Checking load-test guardrails" | tee -a "$LOG_FILE"

  "$KUBECTL_BIN" get pods -n "$NAMESPACE" | tee -a "$LOG_FILE"

  loadgen_pod=$("$KUBECTL_BIN" get pod -n "$NAMESPACE" -l app=load-generator -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)

  if [[ -n "$loadgen_pod" ]]; then
    echo "[monitor] load-generator pod: $loadgen_pod" | tee -a "$LOG_FILE"
    if "$KUBECTL_BIN" logs -n "$NAMESPACE" "$loadgen_pod" --tail=100 2>/dev/null | grep -E -i 'error|exception' >/tmp/loadgen-errors.txt 2>/dev/null; then
      error_count=$(wc -l </tmp/loadgen-errors.txt | tr -d ' ')
      echo "[monitor] recent error count: $error_count" | tee -a "$LOG_FILE"
      if (( error_count > 5 )); then
        echo "[monitor] stop condition: checkout error logs exceeded threshold" | tee -a "$LOG_FILE"
        "$KUBECTL_BIN" scale deployment/load-generator --replicas=0 -n "$NAMESPACE"
        exit 0
      fi
    fi

    if "$KUBECTL_BIN" top pod -n "$NAMESPACE" "$loadgen_pod" 2>/dev/null | tee -a "$LOG_FILE"; then
      cpu=$("$KUBECTL_BIN" top pod -n "$NAMESPACE" "$loadgen_pod" 2>/dev/null | awk 'NR==2 {print $2}' || true)
      mem=$("$KUBECTL_BIN" top pod -n "$NAMESPACE" "$loadgen_pod" 2>/dev/null | awk 'NR==2 {print $3}' || true)
      echo "[monitor] load-generator cpu=$cpu mem=$mem" | tee -a "$LOG_FILE"
    else
      echo "[monitor] metrics unavailable; skipping CPU/memory threshold checks" | tee -a "$LOG_FILE"
    fi
  fi

  sleep "$INTERVAL_SECONDS"
done
