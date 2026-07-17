#!/usr/bin/env bash
set -euo pipefail
NAMESPACE="${NAMESPACE:-techx-tf4}"; RUN_ID="${RUN_ID:-maint-$(date -u +%Y%m%dT%H%M%SZ)}"
ROOT="${EVIDENCE_ROOT:-docs/evidence/directive-03/performance/runs/$RUN_ID}"; MODE="${1:-preflight}"
if command -v kubectl >/dev/null 2>&1; then KUBECTL_BIN=kubectl
elif command -v kubectl.exe >/dev/null 2>&1; then KUBECTL_BIN=kubectl.exe
else echo 'ERROR: kubectl not found' >&2; exit 1; fi
mkdir -p "$ROOT"/{preflight,runtime,dashboard,raw-locust}
printf 'timestamp_utc,event,detail\n' > "$ROOT/timeline.csv"
required=(CHANGE_TICKET APPROVER WINDOW_START_UTC WINDOW_END_UTC MAINTENANCE_ACTION MAINTENANCE_TARGET ROLLBACK_OWNER ROLLBACK_COMMAND)
missing=(); for name in "${required[@]}"; do [[ -n "${!name:-}" ]] || missing+=("$name"); done
{
 printf 'RUN_ID=%s\nCLUSTER=%s\nNAMESPACE=%s\nGIT_SHA=%s\n' "$RUN_ID" "$($KUBECTL_BIN config current-context)" "$NAMESPACE" "$(git rev-parse HEAD)"
 printf 'USERS=200\nSPAWN_RATE=3.34\nRAMP_UP=60s\nSTEADY_STATE=15m\nRAMP_DOWN=20s\nBROWSE_WEIGHT=10\nCART_WEIGHT=5\nCHECKOUT_WEIGHT=2\n'
 for name in "${required[@]}"; do printf '%s=%s\n' "$name" "${!name:-NOT_PROVIDED}"; done
} > "$ROOT/metadata.env"
printf '%s\n' "${MAINTENANCE_COMMAND:-NOT_PROVIDED}" > "$ROOT/maintenance-command.txt"
printf '%s\n' "${ROLLBACK_COMMAND:-NOT_PROVIDED}" > "$ROOT/rollback-command.txt"
$KUBECTL_BIN -n "$NAMESPACE" get deploy,hpa,pdb > "$ROOT/preflight/deploy-hpa-pdb.txt"
$KUBECTL_BIN -n "$NAMESPACE" get pods -o wide > "$ROOT/preflight/pods.txt"
$KUBECTL_BIN -n "$NAMESPACE" get endpointslice > "$ROOT/preflight/endpointslice.txt"
$KUBECTL_BIN get nodes -o wide > "$ROOT/preflight/nodes.txt"
$KUBECTL_BIN get nodes -o json > "$ROOT/preflight/node-conditions.json"
$KUBECTL_BIN top nodes > "$ROOT/preflight/node-usage.txt"; $KUBECTL_BIN -n "$NAMESPACE" top pods > "$ROOT/preflight/pod-usage.txt"
$KUBECTL_BIN -n "$NAMESPACE" get pods -o json > "$ROOT/preflight/restart-oom-baseline.json"
$KUBECTL_BIN -n "$NAMESPACE" get deploy load-generator -o yaml > "$ROOT/preflight/load-generator.yaml"
$KUBECTL_BIN auth can-i create pods/exec -n "$NAMESPACE" > "$ROOT/preflight/can-exec.txt" || true
gate=PASS; [[ ${#missing[@]} -eq 0 ]] || gate=FAIL; [[ "$(<"$ROOT/preflight/can-exec.txt")" == yes ]] || gate=FAIL
if [[ "$MODE" == preflight || "$gate" != PASS ]]; then
 { echo '# Maintenance load-test verdict'; echo; echo '**VERDICT: NOT RUN — EXECUTION GATED**'; echo; echo "Preflight UTC: $(date -u +%Y-%m-%dT%H:%M:%SZ)"; echo "Missing approval fields: ${missing[*]:-none}"; echo "pods/exec permission: $(<"$ROOT/preflight/can-exec.txt")"; echo 'No Locust swarm and no maintenance action were started.'; } > "$ROOT/verdict.md"
 [[ "$MODE" == preflight ]] && exit 0; exit 2
fi
printf '%s,TEST_T0,Locust start\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$ROOT/timeline.csv"
EVIDENCE_DIR="$ROOT/raw-locust" USERS=200 SPAWN=3.34 RAMP_UP=1m STEADY_STATE=15m RAMP_DOWN=20s TOTAL_RUNTIME=16m20s bash scripts/run-load-test-task4.sh full
python scripts/validate-maintenance-locust.py "$ROOT/raw-locust/task4-full-stats.csv" "$ROOT/raw-locust/task4-full-stats-history.csv" > "$ROOT/runtime/volume-guard.txt"
printf '%s,TEST_END,Locust complete\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$ROOT/timeline.csv"
