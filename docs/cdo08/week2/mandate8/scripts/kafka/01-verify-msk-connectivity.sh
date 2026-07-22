#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-techx-tf4}"
SECRET_NAME="${SECRET_NAME:-msk-kafka-secret}"
KUBECTL="${KUBECTL:-kubectl}"

bootstrap="$("$KUBECTL" get secret "$SECRET_NAME" -n "$NAMESPACE" -o jsonpath='{.data.kafka-address}' | base64 -d)"

echo "Verifying TCP connectivity from namespace ${NAMESPACE} to MSK brokers"
IFS=',' read -ra brokers <<< "$bootstrap"
for broker in "${brokers[@]}"; do
  host="${broker%:*}"
  port="${broker##*:}"
  pod_name="msk-connectivity-$RANDOM"
  echo "Checking ${host}:${port}"
  "$KUBECTL" run "$pod_name" \
    -n "$NAMESPACE" \
    -i \
    --rm \
    --restart=Never \
    --image=busybox:1.36.1 \
    --overrides='{
      "spec": {
        "securityContext": {
          "runAsNonRoot": true,
          "runAsUser": 65534,
          "runAsGroup": 65534,
          "seccompProfile": {"type": "RuntimeDefault"}
        },
        "containers": [{
          "name": "'"$pod_name"'",
          "image": "busybox:1.36.1",
          "securityContext": {
            "allowPrivilegeEscalation": false,
            "capabilities": {"drop": ["ALL"]},
            "runAsNonRoot": true,
            "runAsUser": 65534,
            "runAsGroup": 65534,
            "seccompProfile": {"type": "RuntimeDefault"}
          },
          "resources": {
            "requests": {"cpu": "5m", "memory": "8Mi"},
            "limits": {"cpu": "25m", "memory": "32Mi"}
          }
        }]
      }
    }' \
    --command -- sh -c "nc -z -w 10 '$host' '$port'"
done

echo "MSK TCP connectivity check completed"
