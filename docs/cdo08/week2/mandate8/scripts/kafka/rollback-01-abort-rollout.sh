#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-techx-tf4}"
ROLLOUTS="${ROLLOUTS:-checkout accounting fraud-detection}"

for rollout in $ROLLOUTS; do
  echo "Aborting rollout ${rollout} in namespace ${NAMESPACE}"
  kubectl argo rollouts abort "$rollout" -n "$NAMESPACE" || true
  kubectl argo rollouts get rollout "$rollout" -n "$NAMESPACE" || true
done
