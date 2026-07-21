#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-techx-tf4}"
MM2_NAME="${MM2_NAME:-orders-mirrormaker2}"

echo "Checking MirrorMaker2 catch-up indicators for ${MM2_NAME}"
kubectl get kafkamirrormaker2 "$MM2_NAME" -n "$NAMESPACE" -o yaml
kubectl logs -n "$NAMESPACE" -l "strimzi.io/cluster=$MM2_NAME" --tail=200 | grep -Ei "lag|checkpoint|sync|error|warn" || true

echo "Confirm offsets/lag with Kafka CLI before consumer cutover."
