#!/usr/bin/env bash
# Task-4: 200 concurrent users, 15 min steady-state
set -euo pipefail

NAMESPACE="${NAMESPACE:-techx-tf4}"
MODE="${1:-dry-run}"
RAMP_UP="1m"
STEADY_STATE="15m"
RAMP_DOWN="20s"
TOTAL_RUNTIME="16m20s"

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

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "ERROR: Python is required to validate Locust results. Install python3 or python."
  exit 1
fi

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
    RUN_TIME="${TOTAL_RUNTIME}"
    echo "=== FULL TEST: ${USERS} users | ramp-up ${RAMP_UP} | steady-state ${STEADY_STATE} | ramp-down ${RAMP_DOWN} | total ${RUN_TIME} ==="
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
  -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="LOCUST_AUTOSTART")].value}' 2>/dev/null || true)
if [[ -z "$AUTOSTART" ]]; then
  echo "ERROR: LOCUST_AUTOSTART is not configured on load-generator deployment. Set LOCUST_AUTOSTART=false to enforce load shape execution."
  exit 1
fi
if [[ "$AUTOSTART" != "false" ]]; then
  echo "ERROR: LOCUST_AUTOSTART=$AUTOSTART (expected false). Fix the deployment environment."
  exit 1
fi

if ! "$KUBECTL_BIN" auth can-i create pods/exec -n "$NAMESPACE" >/dev/null 2>&1; then
  echo "ERROR: current user cannot exec into pods in namespace $NAMESPACE."
  echo "  Request pods/exec permission or run from an account with exec rights."
  echo "  For example: kubectl auth can-i create pods/exec -n $NAMESPACE"
  exit 1
fi

LOAD_SHAPE=$("$KUBECTL_BIN" get deploy load-generator -n "$NAMESPACE" \
  -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="LOCUST_LOAD_SHAPE")].value}' 2>/dev/null || true)
if [[ -z "$LOAD_SHAPE" ]]; then
  echo "WARN: LOCUST_LOAD_SHAPE is not configured on load-generator deployment. Overriding with task4 for this run."
elif [[ "$LOAD_SHAPE" != "task4" ]]; then
  echo "WARN: LOCUST_LOAD_SHAPE=$LOAD_SHAPE on deployment; overriding with task4 for this run."
else
  echo "INFO: LOCUST_LOAD_SHAPE=task4 on deployment."
fi

echo "[2/7] Scaling load-generator..."
if "$KUBECTL_BIN" scale deployment/load-generator --replicas=1 -n "$NAMESPACE" 2>/dev/null; then
  "$KUBECTL_BIN" rollout status deployment/load-generator -n "$NAMESPACE" --timeout=120s
else
  echo "WARN: Current identity cannot scale deployment/load-generator. Continuing in read-only mode."
fi

EVIDENCE_DIR="docs/evidence/epic-03-performance-efficiency/runtime"
mkdir -p "$EVIDENCE_DIR"
MONITOR_LOG="$EVIDENCE_DIR/load-test-monitor-${MODE}-$(date -u +%Y%m%dT%H%M%SZ).log"
echo "[3/7] Starting monitor... (log: $MONITOR_LOG)"
MONITOR_LOG_PATH="$MONITOR_LOG" bash scripts/monitor-load-test.sh &
MONITOR_PID=$!
trap 'kill $MONITOR_PID 2>/dev/null; "$KUBECTL_BIN" scale deployment/load-generator --replicas=0 -n "$NAMESPACE" 2>/dev/null || true' EXIT

T0=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "T0 (test start): $T0" | tee "docs/evidence/epic-03-performance-efficiency/runtime/task4-${MODE}-T0.txt"
echo "Timeline: ramp-up ${RAMP_UP} -> steady-state ${STEADY_STATE} -> ramp-down ${RAMP_DOWN} (total ${RUN_TIME})"

if [[ "$MODE" == "full" ]]; then
  echo "[4/7] Starting Locust headless (LoadTestShape task4)..."
  echo "  - enforced shape: task4"
  echo "  - enforced autostart: false"
  "$KUBECTL_BIN" exec -n "$NAMESPACE" deploy/load-generator -- \
    env LOCUST_LOAD_SHAPE=task4 LOCUST_AUTOSTART=false locust --headless \
      --users "$USERS" \
      --spawn-rate "$SPAWN" \
      --run-time "$RUN_TIME" \
      --host http://frontend-proxy:8080 \
      --csv /tmp/task4-results \
      --html /tmp/task4-report.html \
      --skip-log-setup \
      -f locustfile.py \
      --only-summary
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
LOADGEN_POD=$("$KUBECTL_BIN" get pod -n "$NAMESPACE" -l app.kubernetes.io/name=load-generator -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [[ -n "$LOADGEN_POD" ]]; then
  "$KUBECTL_BIN" cp "$NAMESPACE/$LOADGEN_POD":/tmp/task4-results_stats.csv \
    "docs/evidence/epic-03-performance-efficiency/runtime/task4-${MODE}-stats.csv" 2>/dev/null || true
  "$KUBECTL_BIN" cp "$NAMESPACE/$LOADGEN_POD":/tmp/task4-report.html \
    "docs/evidence/epic-03-performance-efficiency/runtime/task4-${MODE}-report.html" 2>/dev/null || true
else
  echo "WARN: No load-generator pod found to copy stats and HTML report from."
fi

if [[ "$MODE" == "full" ]]; then
  echo "[5.1/7] Validating full-run SLOs..."
  "$PYTHON_BIN" - <<'PY'
import csv, re, sys
from pathlib import Path
path = Path('docs/evidence/epic-03-performance-efficiency/runtime/task4-full-stats.csv')
if not path.exists():
    print('ERROR: CSV result file not found:', path)
    sys.exit(1)

rows = list(csv.DictReader(path.open()))
if not rows:
    print('ERROR: no rows in CSV file')
    sys.exit(1)

def parse_int(value):
    if value is None:
        return 0
    return int(float(re.sub(r'[^0-9.]','', value) or 0))

def parse_float(value):
    if value is None:
        return 0.0
    return float(re.sub(r'[^0-9.]','', value) or 0.0)

def match(name, pattern):
    return re.search(pattern, name, re.I)

checkout_rows = [r for r in rows if match(r.get('Name',''), r'checkout')]
browse_cart_rows = [r for r in rows if match(r.get('Name',''), r'(browse|cart|add_to_cart|view_cart|product|recommendations|reviews|ads|assistant)')]
total_row = next((r for r in rows if r.get('Name','').lower() == 'total'), None)

if checkout_rows:
    checkout_reqs = sum(parse_int(r.get('# requests') or r.get('Requests') or '0') for r in checkout_rows)
    checkout_fails = sum(parse_int(r.get('# failures') or r.get('# fails') or r.get('Failures') or '0') for r in checkout_rows)
    checkout_success = 100.0 * (checkout_reqs - checkout_fails) / checkout_reqs if checkout_reqs else 100.0
else:
    print('WARNING: checkout rows not found in CSV; falling back to Total for checkout success')
    checkout_success = 100.0 - parse_float(total_row.get('Error %') if total_row else '100') if total_row else 0.0

if browse_cart_rows:
    bc_reqs = sum(parse_int(r.get('# requests') or r.get('Requests') or '0') for r in browse_cart_rows)
    bc_fails = sum(parse_int(r.get('# failures') or r.get('# fails') or r.get('Failures') or '0') for r in browse_cart_rows)
    browse_cart_success = 100.0 * (bc_reqs - bc_fails) / bc_reqs if bc_reqs else 100.0
else:
    print('WARNING: browse/cart rows not found in CSV; falling back to Total for browse/cart success')
    browse_cart_success = 100.0 - parse_float(total_row.get('Error %') if total_row else '100') if total_row else 0.0

storefront_rows = [r for r in rows if match(r.get('Name',''), r'^(index|home|product|browse|recommendations|reviews|ads|cart|checkout)')]
if storefront_rows:
    storefront_p95 = max(parse_float(r.get('95 percentile') or r.get('95th percentile') or r.get('p95') or '0') for r in storefront_rows)
else:
    storefront_p95 = parse_float(total_row.get('95 percentile') if total_row else '0')

print(f'CHECKOUT_SUCCESS={checkout_success:.2f}%')
print(f'BROWSE_CART_SUCCESS={browse_cart_success:.2f}%')
print(f'STOREFRONT_P95={storefront_p95:.2f}ms')

failures = []
if checkout_success < 99.0:
    failures.append(f'checkout success {checkout_success:.2f}% < 99%')
if browse_cart_success < 99.5:
    failures.append(f'browse/cart success {browse_cart_success:.2f}% < 99.5%')
if storefront_p95 >= 1000.0:
    failures.append(f'storefront p95 {storefront_p95:.2f}ms >= 1000ms')
if failures:
    print('ERROR: SLO validation failed: ' + '; '.join(failures))
    sys.exit(1)
print('SLO validation passed')
PY
  if [[ $? -ne 0 ]]; then
    echo "ERROR: Full-run SLO validation failed"
    exit 1
  fi
fi

echo "[6/7] Scale down load-generator..."
"$KUBECTL_BIN" scale deployment/load-generator --replicas=0 -n "$NAMESPACE"

echo "[7/7] Done. Review:"
echo "  - Locust stats: runtime/task4-${MODE}-stats.csv"
echo "  - Monitor log: load-test-monitor-*.log"
echo "  - Grafana: /grafana/ → namespace techx-tf4"
echo "  - Jaeger: /jaeger/ → filter synthetic_request=true"
