#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-techx-tf4}"
MM2_NAME="${MM2_NAME:-orders-mirrormaker2}"

echo "MirrorMaker2 resource status"
kubectl get kafkamirrormaker2 "$MM2_NAME" -n "$NAMESPACE" -o wide

echo "MirrorMaker2 pods"
kubectl get pods -n "$NAMESPACE" -l "strimzi.io/cluster=$MM2_NAME"

echo "Recent MirrorMaker2 logs"
kubectl logs -n "$NAMESPACE" -l "strimzi.io/cluster=$MM2_NAME" --tail=120
