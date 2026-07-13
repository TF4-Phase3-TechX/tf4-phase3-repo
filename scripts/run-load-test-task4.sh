#!/usr/bin/env bash
# Task-4: 200 concurrent users, 15 min steady-state
set -euo pipefail

NAMESPACE="${NAMESPACE:-techx-tf4}"
MODE="${1:-dry-run}"

if command -v kubectl >/dev/null 2>&1; then
  KUBECTL_BIN="$(command -v kubectl)"
elif command -v kubectl.exe >/dev/null 2>&1; then
  KUBECTL_BIN="$(command -v kubectl.exe)"
else
  echo "ERROR: kubectl not found. Install kubectl or add it to PATH before running this script."
  exit 1
fi

"$KUBECTL_BIN" cluster-info >/dev/null 2>&1 || {
  echo "ERROR: kubectl is installed but cannot reach the Kubernetes API. Configure kubeconfig or connect to the target cluster first."
  exit 1
}

case "$MODE" in
  dry-run)
    USERS=5
    SPAWN=1
    RUN_TIME="2m"
    echo "=== DRY-RUN: ${USERS} users, ${RUN_TIME} ==="
    ;;
  full)
    USERS=200
    SPAWN=5
    RUN_TIME="16m20s"
    echo "=== FULL TEST: ${USERS} users, 15 min steady ==="
    ;;
  *)
    echo "Usage: $0 [dry-run|full]"
    exit 1
    ;;
esac

echo "[1/7] Pre-flight checks..."
if "$KUBECTL_BIN" get pods -n "$NAMESPACE" --no-headers 2>/dev/null | awk '{print $3}' | grep -E '^(Error|CrashLoopBackOff|ImagePullBackOff|Pending|CreateContainerConfigError|CreateContainerError|Terminating)$' >/dev/null; then
  echo "ERROR: Some pods are in failed or pending states"
  "$KUBECTL_BIN" get pods -n "$NAMESPACE"
  exit 1
fi

"$KUBECTL_BIN" get pod -n "$NAMESPACE" -l app.kubernetes.io/name=flagd -o name | grep -q . || {
  echo "ERROR: flagd not running — DO NOT disable, fix deployment"
  exit 1
}

AUTOSTART=$("$KUBECTL_BIN" get deploy load-generator -n "$NAMESPACE" \
  -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="LOCUST_AUTOSTART")].value}')
[[ "$AUTOSTART" == "false" ]] || echo "WARN: LOCUST_AUTOSTART=$AUTOSTART (expected false)"

echo "[2/7] Scaling load-generator..."
if "$KUBECTL_BIN" scale deployment/load-generator --replicas=1 -n "$NAMESPACE" 2>/dev/null; then
  "$KUBECTL_BIN" rollout status deployment/load-generator -n "$NAMESPACE" --timeout=120s
else
  echo "WARN: Current identity cannot scale deployment/load-generator. Continuing in read-only mode."
fi

echo "[3/7] Starting monitor..."
./scripts/monitor-load-test.sh &
MONITOR_PID=$!
trap 'kill $MONITOR_PID 2>/dev/null; "$KUBECTL_BIN" scale deployment/load-generator --replicas=0 -n "$NAMESPACE"' EXIT

T0=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "T0 (test start): $T0" | tee "docs/evidence/epic-03-performance-efficiency/runtime/task4-${MODE}-T0.txt"

if [[ "$MODE" == "full" ]]; then
  echo "[4/7] Starting Locust headless (LoadTestShape task4)..."
  "$KUBECTL_BIN" exec -n "$NAMESPACE" deploy/load-generator -- \
    locust --headless \
      --users "$USERS" \
      --spawn-rate "$SPAWN" \
      --run-time "$RUN_TIME" \
      --host http://frontend-proxy:8080 \
      --csv /tmp/task4-results \
      --html /tmp/task4-report.html \
      --skip-log-setup \
      -f locustfile.py
else
  echo "[4/7] DRY-RUN via Locust Web UI"
  echo "  → kubectl port-forward svc/load-generator 8089:8089 -n $NAMESPACE"
  echo "  → http://localhost:8089"
  echo "  → Users: $USERS | Spawn: $SPAWN/s | Run: $RUN_TIME"
  echo "  → Click 'Start swarming', wait ${RUN_TIME}, then Stop"
  read -p "Press Enter after dry-run completes..."
fi

T1=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "T1 (test end): $T1" | tee "docs/evidence/epic-03-performance-efficiency/runtime/task4-${MODE}-T1.txt"

echo "[5/7] Capturing evidence..."
"$KUBECTL_BIN" cp "$NAMESPACE/$("$KUBECTL_BIN" get pod -n "$NAMESPACE" -l app=load-generator -o jsonpath='{.items[0].metadata.name}')":/tmp/task4-results_stats.csv \
  "docs/evidence/epic-03-performance-efficiency/runtime/task4-${MODE}-stats.csv" 2>/dev/null || true

echo "[6/7] Scale down load-generator..."
"$KUBECTL_BIN" scale deployment/load-generator --replicas=0 -n "$NAMESPACE"

echo "[7/7] Done. Review:"
echo "  - Locust stats: runtime/task4-${MODE}-stats.csv"
echo "  - Monitor log: load-test-monitor-*.log"
echo "  - Grafana: /grafana/ → namespace techx-tf4"
echo "  - Jaeger: /jaeger/ → filter synthetic_request=true"
