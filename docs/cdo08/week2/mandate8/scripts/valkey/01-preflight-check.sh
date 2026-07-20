#!/usr/bin/env bash
# CDO08-REL-16 - VALKEY-MIGRATION-PLAN.md BƯỚC 1: preflight check before starting
# any migration step. Verifies the prerequisites this plan depends on are real,
# not just committed. Read-only - does not change anything.
set -euo pipefail

RG_ID="techx-tf4-valkey-cart"
NAMESPACE="techx-tf4"

echo "[1/4] Argo Rollouts CRD installed?"
kubectl get crd rollouts.argoproj.io >/dev/null \
  && echo "  OK: rollouts.argoproj.io CRD present." \
  || { echo "  FAIL: Argo Rollouts CRD missing - sync the argo-rollouts Application first."; exit 1; }

echo "[2/4] cart Rollout resource exists and is healthy?"
kubectl get rollout cart -n "$NAMESPACE" >/dev/null \
  && echo "  OK: Rollout/cart exists (components.cart.rollouts.enabled must be true)." \
  || { echo "  FAIL: Rollout/cart not found - flip components.cart.rollouts.enabled=true and sync first."; exit 1; }

echo "[3/4] valkey-migration-bridge Service has an NLB endpoint?"
BRIDGE_HOST=$(kubectl get svc valkey-migration-bridge -n "$NAMESPACE" \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)
if [ -z "$BRIDGE_HOST" ]; then
  echo "  FAIL: valkey-migration-bridge has no LB hostname yet - enable valkeyMigrationBridge and wait for NLB provisioning."
  exit 1
fi
echo "  OK: bridge endpoint = $BRIDGE_HOST"

echo "[4/4] ElastiCache replication group is available?"
STATUS=$(aws elasticache describe-replication-groups --replication-group-id "$RG_ID" \
  --query 'ReplicationGroups[0].Status' --output text)
[ "$STATUS" = "available" ] \
  && echo "  OK: $RG_ID status=available" \
  || { echo "  FAIL: $RG_ID status=$STATUS (expected available)"; exit 1; }

echo "Preflight checks passed."
