#!/usr/bin/env bash
# CDO08-REL-16 - VALKEY-MIGRATION-PLAN.md BƯỚC 3.5: promote the paused
# Blue-Green Rollout (Green pods already point at ElastiCache, per the
# managedData.valkey.enabled cutover in Git) so cart traffic actually switches,
# then unpause writes on the old source.
set -euo pipefail

NAMESPACE="techx-tf4"

echo "Current rollout status:"
kubectl argo rollouts get rollout cart -n "$NAMESPACE"

echo "Promoting cart rollout ..."
kubectl argo rollouts promote cart -n "$NAMESPACE"

echo "Unpausing writes on the old valkey-cart source ..."
kubectl exec -n "$NAMESPACE" deploy/valkey-cart -- redis-cli CLIENT UNPAUSE

echo "Promoted. Proceed to post-cutover parity check (§5.2), then smoke test."
