#!/usr/bin/env bash
# D19-PERF-02: deterministic stepped breakpoint run and raw evidence capture.
set -euo pipefail

NAMESPACE="${NAMESPACE:-techx-tf4}"
RUN_TYPE="${1:-}"
HOST="${HOST:-http://frontend-proxy:8080}"
EVIDENCE_ROOT="${EVIDENCE_ROOT:-docs/evidence/mandate-19-Determine and raise the throughput/runtime}"
PROFILE_NAME="d19-breakpoint-v1"
TOTAL_RUNTIME="75m"
MIN_SUCCESS_SAMPLES_BROWSE=100
MIN_SUCCESS_SAMPLES_CART=100
MIN_SUCCESS_SAMPLES_CHECKOUT=100

if [[ "$RUN_TYPE" != "baseline" && "$RUN_TYPE" != "post-tuning" ]]; then
  echo "Usage: $0 baseline|post-tuning"
  exit 2
fi

for command_name in kubectl git python sha256sum; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "ERROR: required command not found: $command_name"
    exit 1
  }
done

kubectl cluster-info >/dev/null 2>&1 || {
  echo "ERROR: Kubernetes API is unreachable"
  exit 1
}

RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_DIR="$EVIDENCE_ROOT/${RUN_TYPE}-${RUN_ID}"
LOAD_DIR="$RUN_DIR/load"
KUBE_DIR="$RUN_DIR/kubernetes"
LOADGEN_DIR="$RUN_DIR/load-generator"
mkdir -p "$LOAD_DIR" "$KUBE_DIR" "$LOADGEN_DIR"

write_result() {
  case "$1" in
    PASS|FAIL|INVALID|HARD_STOP|INSUFFICIENT_DATA|NO_BREAKPOINT_FOUND_WITHIN_PROFILE) ;;
    *) echo "ERROR: unsupported RESULT verdict: $1"; exit 2 ;;
  esac
  printf '%s\n' "$1" >"$RUN_DIR/RESULT"
}
write_result INSUFFICIENT_DATA

LOADGEN_POD="$(kubectl get pod -n "$NAMESPACE" -l app.kubernetes.io/name=load-generator -o jsonpath='{.items[0].metadata.name}')"
[[ -n "$LOADGEN_POD" ]] || { echo "ERROR: load-generator pod not found"; exit 1; }

NODE_COUNT="$(kubectl get nodes --no-headers | wc -l | tr -d ' ')"
IMAGE="$(kubectl get pod -n "$NAMESPACE" "$LOADGEN_POD" -o jsonpath='{.spec.containers[0].image}')"
IMAGE_ID="$(kubectl get pod -n "$NAMESPACE" "$LOADGEN_POD" -o jsonpath='{.status.containerStatuses[0].imageID}')"
PROFILE_SHA256="$(python -c 'import hashlib; value=open("techx-corp-platform/src/load-generator/locustfile.py", "rb").read().replace(b"\r\n", b"\n"); print(hashlib.sha256(value).hexdigest())')"
PEOPLE_SHA256="$(python -c 'import hashlib,json; value=json.load(open("techx-corp-platform/src/load-generator/people.json")); print(hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",", ":")).encode()).hexdigest())')"
PRODUCT_FIXTURE_SHA256="$(python -c 'import ast,hashlib,json; tree=ast.parse(open("techx-corp-platform/src/load-generator/locustfile.py", encoding="utf-8").read()); value=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="products" for t in n.targets)); print(hashlib.sha256(json.dumps(value,separators=(",", ":")).encode()).hexdigest())')"
DEPLOYED_PROFILE_SHA256="$(kubectl exec -n "$NAMESPACE" "$LOADGEN_POD" -- python -c \
  'import hashlib; value=open("locustfile.py", "rb").read().replace(b"\r\n", b"\n"); print(hashlib.sha256(value).hexdigest())')"
DEPLOYED_PEOPLE_SHA256="$(kubectl exec -n "$NAMESPACE" "$LOADGEN_POD" -- python -c \
  'import hashlib,json; value=json.load(open("people.json")); print(hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",", ":")).encode()).hexdigest())')"
DEPLOYED_PRODUCT_FIXTURE_SHA256="$(kubectl exec -n "$NAMESPACE" "$LOADGEN_POD" -- python -c \
  'import ast,hashlib,json; tree=ast.parse(open("locustfile.py", encoding="utf-8").read()); value=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="products" for t in n.targets)); print(hashlib.sha256(json.dumps(value,separators=(",", ":")).encode()).hexdigest())')"
if [[ "$DEPLOYED_PROFILE_SHA256" != "$PROFILE_SHA256" ]]; then
  echo "ERROR: deployed locustfile SHA does not match the reviewed workspace profile"
  echo "  workspace: $PROFILE_SHA256"
  echo "  deployed:  $DEPLOYED_PROFILE_SHA256"
  write_result INVALID
  exit 1
fi
if [[ "$DEPLOYED_PEOPLE_SHA256" != "$PEOPLE_SHA256" || "$DEPLOYED_PRODUCT_FIXTURE_SHA256" != "$PRODUCT_FIXTURE_SHA256" ]]; then
  echo "ERROR: deployed user/product fixtures do not match reviewed sources"
  write_result INVALID
  exit 1
fi

kubectl get deployment load-generator -n "$NAMESPACE" \
  -o jsonpath='{.spec.template.spec.containers[0].env}{"\n"}{.spec.template.spec.containers[0].args}{"\n"}{.spec.template.spec.containers[0].resources}{"\n"}' \
  >"$LOADGEN_DIR/runtime-config.txt"
RUNTIME_CONFIG_SHA256="$(sha256sum "$LOADGEN_DIR/runtime-config.txt" | awk '{print $1}')"
NODE_FINGERPRINT_COLUMNS='NAME:.metadata.name,UID:.metadata.uid,PROVIDER_ID:.spec.providerID,INSTANCE_TYPE:.metadata.labels.node\.kubernetes\.io/instance-type'

cat >"$RUN_DIR/run-metadata.env" <<EOF
RUN_ID=$RUN_ID
RUN_TYPE=$RUN_TYPE
PROFILE_NAME=$PROFILE_NAME
PROFILE_SHA256=$PROFILE_SHA256
DEPLOYED_PROFILE_SHA256=$DEPLOYED_PROFILE_SHA256
PEOPLE_SHA256=$PEOPLE_SHA256
DEPLOYED_PEOPLE_SHA256=$DEPLOYED_PEOPLE_SHA256
PRODUCT_FIXTURE_SHA256=$PRODUCT_FIXTURE_SHA256
DEPLOYED_PRODUCT_FIXTURE_SHA256=$DEPLOYED_PRODUCT_FIXTURE_SHA256
RUNTIME_CONFIG_SHA256=$RUNTIME_CONFIG_SHA256
REVIEWED_GIT_SHA=$(git rev-parse HEAD)
NAMESPACE=$NAMESPACE
KUBERNETES_CONTEXT=$(kubectl config current-context)
LOAD_GENERATOR_IMAGE=$IMAGE
LOAD_GENERATOR_IMAGE_DIGEST=$IMAGE_ID
WORKER_NODE_COUNT=$NODE_COUNT
LOCUST_HOST=$HOST
PLANNED_RUNTIME=$TOTAL_RUNTIME
MIN_SUCCESS_SAMPLES_BROWSE=$MIN_SUCCESS_SAMPLES_BROWSE
MIN_SUCCESS_SAMPLES_CART=$MIN_SUCCESS_SAMPLES_CART
MIN_SUCCESS_SAMPLES_CHECKOUT=$MIN_SUCCESS_SAMPLES_CHECKOUT
RUN_START_UTC=
RUN_END_UTC=
EOF

kubectl get nodes -o wide --show-labels >"$KUBE_DIR/nodes-before.txt"
kubectl get nodes --no-headers -o "custom-columns=$NODE_FINGERPRINT_COLUMNS" | sort >"$KUBE_DIR/node-fingerprint-before.txt"
kubectl get hpa -n "$NAMESPACE" -o yaml >"$KUBE_DIR/hpa-before.yaml"
kubectl get resourcequota,limitrange -n "$NAMESPACE" -o yaml >"$KUBE_DIR/capacity-guards-before.yaml"
kubectl get pods -n "$NAMESPACE" -o wide >"$KUBE_DIR/pods-before.txt"

(
  while true; do
    printf 'TIMESTAMP_UTC=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    kubectl get nodes --no-headers -o "custom-columns=$NODE_FINGERPRINT_COLUMNS"
    sleep 60
  done
) >"$KUBE_DIR/node-timeline.log" 2>&1 &
NODE_MONITOR_PID=$!
(
  while true; do
    printf 'TIMESTAMP_UTC=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    kubectl top pod -n "$NAMESPACE" "$LOADGEN_POD" --containers 2>&1 || true
    printf 'RESTART_COUNT='
    kubectl get pod -n "$NAMESPACE" "$LOADGEN_POD" -o jsonpath='{.status.containerStatuses[0].restartCount}' 2>&1 || true
    printf '\nCGROUP_CPU_STAT\n'
    kubectl exec -n "$NAMESPACE" "$LOADGEN_POD" -- sh -c 'cat /sys/fs/cgroup/cpu.stat 2>/dev/null || true'
    printf 'CGROUP_MEMORY_CURRENT='
    kubectl exec -n "$NAMESPACE" "$LOADGEN_POD" -- sh -c 'cat /sys/fs/cgroup/memory.current 2>/dev/null || true'
    printf '\n'
    sleep 60
  done
) >"$LOADGEN_DIR/resource-timeline.log" 2>&1 &
LOADGEN_MONITOR_PID=$!
cleanup() { kill "$NODE_MONITOR_PID" "$LOADGEN_MONITOR_PID" 2>/dev/null || true; }
hard_stop() { write_result HARD_STOP; cleanup; exit 130; }
trap cleanup EXIT
trap hard_stop INT TERM

T0="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
sed -i "s/^RUN_START_UTC=.*/RUN_START_UTC=$T0/" "$RUN_DIR/run-metadata.env"

utc_at_offset() { date -u -d "$T0 + $1 seconds" +%Y-%m-%dT%H:%M:%SZ; }
{
  echo "phase,target_users,spawn_rate,start_offset_seconds,end_offset_seconds,start_utc,end_utc"
  while IFS=, read -r phase users spawn start_offset end_offset; do
    printf '%s,%s,%s,%s,%s,%s,%s\n' \
      "$phase" "$users" "$spawn" "$start_offset" "$end_offset" \
      "$(utc_at_offset "$start_offset")" "$(utc_at_offset "$end_offset")"
  done <<'PHASES'
warm-up,25,5,0,300
step-01,50,5,300,600
step-02,75,5,600,900
step-03,100,5,900,1200
step-04,125,5,1200,1500
step-05,150,5,1500,1800
step-06,175,5,1800,2100
step-07,200,5,2100,2400
fine-01,210,2,2400,2700
fine-02,220,2,2700,3000
fine-03,230,2,3000,3300
fine-04,240,2,3300,3600
fine-05,250,2,3600,3900
overload,275,2,3900,4500
PHASES
} >"$LOAD_DIR/phase-timeline.csv"

kubectl exec -n "$NAMESPACE" "$LOADGEN_POD" -- sh -c ': > /tmp/d19-phase-transitions.csv'
kubectl exec -n "$NAMESPACE" "$LOADGEN_POD" -- env \
  LOCUST_LOAD_SHAPE=d19-breakpoint LOCUST_AUTOSTART=false \
  D19_PHASE_TRANSITIONS_FILE=/tmp/d19-phase-transitions.csv \
  locust --headless --host "$HOST" --run-time "$TOTAL_RUNTIME" \
  --csv /tmp/d19-breakpoint --csv-full-history \
  --html /tmp/d19-breakpoint.html -f locustfile.py \
  2>&1 | tee "$LOAD_DIR/locust-console.log"

T1="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
sed -i "s/^RUN_END_UTC=.*/RUN_END_UTC=$T1/" "$RUN_DIR/run-metadata.env"

for artifact in stats.csv stats_history.csv failures.csv exceptions.csv; do
  if ! kubectl cp "$NAMESPACE/$LOADGEN_POD:/tmp/d19-breakpoint_$artifact" "$LOAD_DIR/$artifact"; then
    echo "WARN: $artifact was not emitted; preserving an empty artifact"
    : >"$LOAD_DIR/$artifact"
  fi
done
kubectl cp "$NAMESPACE/$LOADGEN_POD:/tmp/d19-breakpoint.html" "$LOAD_DIR/report.html"
kubectl cp "$NAMESPACE/$LOADGEN_POD:/tmp/d19-phase-transitions.csv" "$LOAD_DIR/actual-phase-transitions.csv"
kubectl logs -n "$NAMESPACE" "$LOADGEN_POD" --timestamps >"$LOAD_DIR/pod.log"
kubectl get nodes -o wide --show-labels >"$KUBE_DIR/nodes-after.txt"
kubectl get nodes --no-headers -o "custom-columns=$NODE_FINGERPRINT_COLUMNS" | sort >"$KUBE_DIR/node-fingerprint-after.txt"

FINAL_NODE_COUNT="$(kubectl get nodes --no-headers | wc -l | tr -d ' ')"
if [[ "$FINAL_NODE_COUNT" != "$NODE_COUNT" ]]; then
  echo "INVALID: node count changed from $NODE_COUNT to $FINAL_NODE_COUNT"
  write_result INVALID
  exit 1
fi
if ! cmp -s "$KUBE_DIR/node-fingerprint-before.txt" "$KUBE_DIR/node-fingerprint-after.txt"; then
  echo "INVALID: worker node identity/provider ID changed during the run"
  write_result INVALID
  exit 1
fi

echo "Evidence captured in $RUN_DIR"
