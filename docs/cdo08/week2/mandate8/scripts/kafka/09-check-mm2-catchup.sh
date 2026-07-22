#!/usr/bin/env bash
set -euo pipefail

# So offset self-hosted vs MSK, 2 mốc cách nhau N giây, in kết quả + exit 0/1.
#
# Usage:
#   docs/cdo08/week2/mandate8/scripts/kafka/09-check-mm2-catchup.sh
#
# Env vars (đều có default đúng với cluster hiện tại):
#   NAMESPACE, MM2_POD, TOPIC, PARTITION, MSK_BOOTSTRAP, SELFHOSTED_BOOTSTRAP, WAIT_SECONDS

NAMESPACE="${NAMESPACE:-techx-tf4}"
MM2_POD="${MM2_POD:-orders-mirrormaker2-mirrormaker2-0}"
TOPIC="${TOPIC:-orders}"
PARTITION="${PARTITION:-0}"
MSK_BOOTSTRAP="${MSK_BOOTSTRAP:-b-2.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096,b-1.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096}"
SELFHOSTED_BOOTSTRAP="${SELFHOSTED_BOOTSTRAP:-kafka:9092}"
WAIT_SECONDS="${WAIT_SECONDS:-20}"

get_selfhosted_offset() {
  kubectl exec -n "$NAMESPACE" "$MM2_POD" -- sh -c \
    "/opt/kafka/bin/kafka-get-offsets.sh --bootstrap-server $SELFHOSTED_BOOTSTRAP --topic $TOPIC --time -1" \
    | grep "^${TOPIC}:${PARTITION}:" | cut -d: -f3
}

get_msk_offset() {
  kubectl exec -n "$NAMESPACE" "$MM2_POD" -- sh -c \
    "timeout 60 /opt/kafka/bin/kafka-get-offsets.sh --bootstrap-server $MSK_BOOTSTRAP --command-config /tmp/strimzi-connect.properties --topic $TOPIC --time -1" \
    | grep "^${TOPIC}:${PARTITION}:" | cut -d: -f3
}

echo ">> Moc 1"
S1="$(get_selfhosted_offset)"
T1="$(get_msk_offset)"
echo "self-hosted=$S1  msk=$T1  gap=$((S1-T1))"

echo ">> Doi ${WAIT_SECONDS}s..."
sleep "$WAIT_SECONDS"

echo ">> Moc 2"
S2="$(get_selfhosted_offset)"
T2="$(get_msk_offset)"
echo "self-hosted=$S2 (+$((S2-S1)))  msk=$T2 (+$((T2-T1)))  gap=$((S2-T2))"

echo ""
if [ "$((T2 - T1))" -ge "$((S2 - S1))" ]; then
  echo "OK — MSK tang >= self-hosted, catch-up that. Co the Promote."
  exit 0
else
  echo "CHUA OK — MSK tang cham hon self-hosted, dang bi lag them. KHONG Promote."
  exit 1
fi
