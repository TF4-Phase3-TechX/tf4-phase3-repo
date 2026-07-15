#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-techx-tf4}"
DEPLOYMENT="${DEPLOYMENT:-valkey-cart}"
PVC="${PVC:-valkey-cart-pvc}"
EXPECTED_CONTEXT_PATTERN="${EXPECTED_CONTEXT_PATTERN:-techx-tf4-cluster}"
EXPECTED_STORAGE_CLASS="${EXPECTED_STORAGE_CLASS:-gp3}"
TEST_USER="${TEST_USER:-rel03b-$(date -u +%Y%m%dT%H%M%SZ)}"
TEST_PRODUCT="${TEST_PRODUCT:-OLJCESPC7Z}"
TEST_QUANTITY="${TEST_QUANTITY:-3}"

require_target() {
  local context status storage_class
  context="$(kubectl config current-context)"
  [[ "$context" == *"$EXPECTED_CONTEXT_PATTERN"* ]] || {
    echo "Refusing context: $context" >&2
    exit 1
  }

  status="$(kubectl -n "$NAMESPACE" get pvc "$PVC" -o jsonpath='{.status.phase}')"
  storage_class="$(kubectl -n "$NAMESPACE" get pvc "$PVC" -o jsonpath='{.spec.storageClassName}')"
  [[ "$status" == "Bound" ]] || { echo "$PVC is not Bound" >&2; exit 1; }
  if [[ "$storage_class" != "$EXPECTED_STORAGE_CLASS" ]]; then
    [[ "${ALLOW_CURRENT_STORAGE_CLASS:-}" == "$storage_class" ]] || {
      echo "StorageClass is '$storage_class', expected '$EXPECTED_STORAGE_CLASS'." >&2
      echo "Do not mutate an existing PVC; rerun with ALLOW_CURRENT_STORAGE_CLASS=$storage_class to verify it as an explicit deviation." >&2
      exit 1
    }
    echo "WARNING: verifying approved deviation StorageClass=$storage_class; gp3 requires a separate PVC migration."
  fi

  kubectl -n "$NAMESPACE" rollout status "deployment/$DEPLOYMENT" --timeout=120s
  echo "Context: $context"
  echo "PVC: $PVC status=$status storageClass=$storage_class"
}

verify_aof() {
  local appendonly directory aof_enabled aof_status
  appendonly="$(kubectl -n "$NAMESPACE" exec "deployment/$DEPLOYMENT" -- valkey-cli --raw CONFIG GET appendonly | tail -n 1 | tr -d '\r')"
  directory="$(kubectl -n "$NAMESPACE" exec "deployment/$DEPLOYMENT" -- valkey-cli --raw CONFIG GET dir | tail -n 1 | tr -d '\r')"
  aof_enabled="$(kubectl -n "$NAMESPACE" exec "deployment/$DEPLOYMENT" -- valkey-cli --raw INFO persistence | tr -d '\r' | sed -n 's/^aof_enabled://p')"
  aof_status="$(kubectl -n "$NAMESPACE" exec "deployment/$DEPLOYMENT" -- valkey-cli --raw INFO persistence | tr -d '\r' | sed -n 's/^aof_last_write_status://p')"

  [[ "$appendonly" == "yes" ]]
  [[ "$directory" == "/data" ]]
  [[ "$aof_enabled" == "1" ]]
  [[ "$aof_status" == "ok" ]]
  echo "AOF: appendonly=$appendonly dir=$directory enabled=$aof_enabled lastWrite=$aof_status"
}

cart_request() {
  local method="$1"
  kubectl -n "$NAMESPACE" exec deployment/load-generator -- env \
    REL03_METHOD="$method" REL03_USER="$TEST_USER" REL03_PRODUCT="$TEST_PRODUCT" REL03_QUANTITY="$TEST_QUANTITY" \
    python -c 'import os,requests; u=os.environ["REL03_USER"]; p=os.environ["REL03_PRODUCT"]; q=int(os.environ["REL03_QUANTITY"]); url="http://frontend:8080/api/cart"; r=requests.post(url,json={"userId":u,"item":{"productId":p,"quantity":q}},timeout=15) if os.environ["REL03_METHOD"]=="POST" else requests.get(url,params={"sessionId":u,"currencyCode":"USD"},timeout=15); r.raise_for_status(); data=r.json(); items=data.get("items",[]); assert any(i.get("productId")==p and i.get("quantity")==q for i in items), data; print(data)'
}

smoke() {
  cart_request POST
  cart_request GET
  echo "Cart smoke passed: user=$TEST_USER product=$TEST_PRODUCT quantity=$TEST_QUANTITY"
}

recreate_proof() {
  [[ "${CONFIRM_RECREATE:-}" == "${NAMESPACE}/${DEPLOYMENT}" ]] || {
    echo "Rerun with CONFIRM_RECREATE=${NAMESPACE}/${DEPLOYMENT}" >&2
    exit 1
  }
  local before_uid after_uid
  before_uid="$(kubectl -n "$NAMESPACE" get pod -l app.kubernetes.io/component=valkey-cart -o jsonpath='{.items[0].metadata.uid}')"
  cart_request POST
  kubectl -n "$NAMESPACE" delete pod -l app.kubernetes.io/component=valkey-cart --wait=true
  kubectl -n "$NAMESPACE" rollout status "deployment/$DEPLOYMENT" --timeout=300s
  after_uid="$(kubectl -n "$NAMESPACE" get pod -l app.kubernetes.io/component=valkey-cart -o jsonpath='{.items[0].metadata.uid}')"
  [[ "$before_uid" != "$after_uid" ]]
  verify_aof
  cart_request GET
  echo "Old pod UID: $before_uid"
  echo "New pod UID: $after_uid"
  echo "Valkey recreation proof passed: cart persisted through pod replacement."
}

require_target
case "${1:-}" in
  verify) verify_aof; smoke ;;
  recreate-proof) verify_aof; recreate_proof ;;
  *) echo "Usage: $0 verify|recreate-proof" >&2; exit 2 ;;
esac
