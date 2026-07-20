#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-techx-tf4}"
SECRET_NAME="${SECRET_NAME:-msk-kafka-secret}"

bootstrap="$(kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" -o jsonpath='{.data.kafka-address}' | base64 -d)"

echo "Verifying TCP connectivity from namespace ${NAMESPACE} to MSK brokers"
IFS=',' read -ra brokers <<< "$bootstrap"
for broker in "${brokers[@]}"; do
  host="${broker%:*}"
  port="${broker##*:}"
  echo "Checking ${host}:${port}"
  kubectl run "msk-connectivity-$RANDOM" \
    -n "$NAMESPACE" \
    --rm \
    --restart=Never \
    --image=busybox:1.36.1 \
    --command -- sh -c "nc -z -w 10 '$host' '$port'"
done

echo "MSK TCP connectivity check completed"
