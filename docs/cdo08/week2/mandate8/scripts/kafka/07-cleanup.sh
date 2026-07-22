#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-techx-tf4}"
MM2_NAME="${MM2_NAME:-orders-mirrormaker2}"

echo "Cleanup is GitOps-controlled. Disable mirrormaker2.enabled in values and merge/sync before deleting any runtime resources."
echo "Current MirrorMaker2 status, if present:"
kubectl get kafkamirrormaker2 "$MM2_NAME" -n "$NAMESPACE" || true
echo "Do not delete Kafka self-hosted until REL-17 parity, rollback, and owner approval are complete."
