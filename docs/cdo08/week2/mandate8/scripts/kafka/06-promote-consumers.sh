#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-techx-tf4}"
ROLLOUTS="${ROLLOUTS:-accounting fraud-detection}"

for rollout in $ROLLOUTS; do
  echo "Promoting consumer rollout ${rollout} in namespace ${NAMESPACE}"
  kubectl argo rollouts promote "$rollout" -n "$NAMESPACE"
  kubectl argo rollouts get rollout "$rollout" -n "$NAMESPACE"
done
