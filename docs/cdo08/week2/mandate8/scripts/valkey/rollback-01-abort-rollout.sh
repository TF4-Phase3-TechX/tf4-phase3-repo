#!/usr/bin/env bash
# CDO08-REL-16 - VALKEY-MIGRATION-PLAN.md §4 TRƯỜNG HỢP 1 (rollback BEFORE any
# new writes hit ElastiCache, RPO=0): abort the Blue-Green rollout so cart's
# active Service switches back to the stable (old, valkey-cart-pointing)
# ReplicaSet. Safe to run any time before 06-promote-rollout.sh has been run.
set -euo pipefail

NAMESPACE="techx-tf4"

echo "Aborting cart rollout (reverting to stable ReplicaSet, still pointing at valkey-cart) ..."
kubectl argo rollouts abort cart -n "$NAMESPACE"

echo "Current status:"
kubectl argo rollouts get rollout cart -n "$NAMESPACE"

echo "Next: rollback-02-unlock-source.sh to release the write-pause on valkey-cart."
