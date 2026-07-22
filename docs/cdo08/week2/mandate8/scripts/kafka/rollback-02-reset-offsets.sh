#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-techx-tf4}"
KAFKA_POD="${KAFKA_POD:-$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/component=kafka -o jsonpath='{.items[0].metadata.name}')}"
GROUPS="${GROUPS:-accounting fraud-detection}"
TOPIC="${TOPIC:-orders}"

for group in $GROUPS; do
  echo "Dry-run offset reset for group ${group} on topic ${TOPIC}"
  kubectl exec -n "$NAMESPACE" "$KAFKA_POD" -- sh -c \
    "/opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --group '$group' --topic '$TOPIC' --reset-offsets --to-latest --dry-run"
done

echo "This script is dry-run only. Remove --dry-run manually during an approved rollback window."
