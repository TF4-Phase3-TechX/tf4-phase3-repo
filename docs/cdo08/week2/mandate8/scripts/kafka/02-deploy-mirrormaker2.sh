#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-techx-tf4}"
RELEASE="${RELEASE:-techx-corp}"
CHART_PATH="${CHART_PATH:-./techx-corp-chart}"
VALUES_ARGS="${VALUES_ARGS:-}"
TARGET_BOOTSTRAP="${TARGET_BOOTSTRAP:-}"

if [[ -z "$TARGET_BOOTSTRAP" ]]; then
  TARGET_BOOTSTRAP="$(kubectl get secret msk-kafka-secret -n "$NAMESPACE" -o jsonpath='{.data.kafka-address}' | base64 -d)"
fi

echo "Rendering MirrorMaker2 manifest"
helm template "$RELEASE" "$CHART_PATH" \
  $VALUES_ARGS \
  --set mirrormaker2.enabled=true \
  --set-string mirrormaker2.targetCluster.bootstrapServers="$TARGET_BOOTSTRAP" \
  --show-only templates/mirrormaker2.yaml

echo "Apply this change through GitOps. Direct kubectl apply is intentionally not performed by this script."
