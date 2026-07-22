#!/usr/bin/env bash
set -uo pipefail

# Xac nhan traffic that su dang chay qua MSK sau cutover:
#   1. checkout/accounting/fraud-detection da tro sang MSK (co KAFKA_SECURITY_PROTOCOL)
#   2. Khong co loi ket noi/SASL trong log 5 phut gan nhat
#   3. Consumer group accounting/fraud-detection tren MSK co ACTIVE MEMBER that
#      (khong chi LAG=0 - MM2 tu sync checkpoint offset ngay ca khi chua ai consume that,
#      nen LAG=0 khong du, phai co CONSUMER-ID/HOST that thi moi la dang chay that)
#
# Usage:
#   docs/cdo08/week2/mandate8/scripts/kafka/11-verify-event-flow.sh

NAMESPACE="${NAMESPACE:-techx-tf4}"
MM2_POD="${MM2_POD:-orders-mirrormaker2-mirrormaker2-0}"
MSK_BOOTSTRAP="${MSK_BOOTSTRAP:-b-2.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096,b-1.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096}"
SINCE="${SINCE:-5m}"

FAIL=0

check_msk_config() {
  local svc="$1"
  local env
  env="$(kubectl get deploy "$svc" -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].env}' 2>/dev/null || \
         kubectl get rollout "$svc" -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].env}' 2>/dev/null)"
  if printf '%s' "$env" | grep -q '"name":"KAFKA_SECURITY_PROTOCOL"'; then
    echo "  [OK] $svc dang tro MSK (KAFKA_SECURITY_PROTOCOL da set)"
  else
    echo "  [FAIL] $svc CHUA tro MSK (khong thay KAFKA_SECURITY_PROTOCOL)"
    FAIL=1
  fi
}

check_errors() {
  local svc="$1"
  local container_flag=()
  [ "$svc" = "checkout" ] && container_flag=(-c checkout)
  local errors
  errors="$(kubectl logs -n "$NAMESPACE" -l "opentelemetry.io/name=$svc" "${container_flag[@]}" --since="$SINCE" --tail=500 2>/dev/null | \
    grep -iE "connection setup timed out|brokers are down|sasl authentication failed|connection refused" || true)"
  if [ -z "$errors" ]; then
    echo "  [OK] $svc log ${SINCE} gan nhat khong co loi ket noi/SASL"
  else
    echo "  [FAIL] $svc co loi trong log:"
    echo "$errors" | sed 's/^/      /'
    FAIL=1
  fi
}

check_consumer_active() {
  local group="$1"
  local out
  out="$(kubectl exec -n "$NAMESPACE" "$MM2_POD" -- sh -c \
    "timeout 60 /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server $MSK_BOOTSTRAP --command-config /tmp/strimzi-connect.properties --describe --group $group" 2>&1)"
  echo "$out" | sed 's/^/  /'
  if echo "$out" | grep -q "no active members"; then
    echo "  [FAIL] group '$group' KHONG co active member that tren MSK"
    FAIL=1
  elif echo "$out" | grep -qE "^$group\s"; then
    echo "  [OK] group '$group' co active member that tren MSK"
  else
    echo "  [FAIL] khong lay duoc thong tin group '$group' (kiem tra loi ben tren)"
    FAIL=1
  fi
}

echo ">> 1. Kiem config MSK cho ca 3 service"
check_msk_config checkout
check_msk_config accounting
check_msk_config fraud-detection

echo ""
echo ">> 2. Kiem loi trong log ${SINCE} gan nhat"
check_errors checkout
check_errors accounting
check_errors fraud-detection

echo ""
echo ">> 3. Kiem consumer group active tren MSK"
check_consumer_active accounting
echo ""
check_consumer_active fraud-detection

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "XONG — ca 3 service da tro MSK, khong loi, consumer dang active that. Event parity PASS."
  exit 0
else
  echo "CHUA XONG — xem cac dong [FAIL] o tren."
  exit 1
fi
