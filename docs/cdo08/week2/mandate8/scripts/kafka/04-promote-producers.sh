#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-techx-tf4}"
ROLLOUT="${ROLLOUT:-checkout}"

echo "Promoting producer rollout ${ROLLOUT} in namespace ${NAMESPACE}"
kubectl argo rollouts promote "$ROLLOUT" -n "$NAMESPACE"
kubectl argo rollouts get rollout "$ROLLOUT" -n "$NAMESPACE"
