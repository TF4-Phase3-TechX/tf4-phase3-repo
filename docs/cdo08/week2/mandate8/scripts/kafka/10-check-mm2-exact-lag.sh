#!/usr/bin/env bash
set -euo pipefail

# Do lag CHINH XAC: offset MM2 da doc/commit tu self-hosted (qua Kafka Connect
# REST API /connectors/<name>/offsets, KIP-875, Kafka 3.6+) so voi end-offset
# that su cua self-hosted. Khac voi 09-check-mm2-catchup.sh (chi so toc do tang
# giua 2 moc, khong phai con so lag that).
#
# Usage:
#   docs/cdo08/week2/mandate8/scripts/kafka/10-check-mm2-exact-lag.sh
#
# Exit 0 neu lag <= LAG_THRESHOLD (mac dinh 5) -> du an toan de Promote.
# Exit 1 neu lag > threshold -> cho them roi chay lai.

NAMESPACE="${NAMESPACE:-techx-tf4}"
MM2_POD="${MM2_POD:-orders-mirrormaker2-mirrormaker2-0}"
CONNECTOR="${CONNECTOR:-self-hosted->msk.MirrorSourceConnector}"
TOPIC="${TOPIC:-orders}"
PARTITION="${PARTITION:-0}"
SELFHOSTED_BOOTSTRAP="${SELFHOSTED_BOOTSTRAP:-kafka:9092}"
LAG_THRESHOLD="${LAG_THRESHOLD:-5}"

CONNECTOR_URLENC="$(printf '%s' "$CONNECTOR" | sed 's/->/-%3E/')"

echo ">> End-offset that su tren self-hosted ($TOPIC:$PARTITION)"
SELFHOSTED_OFFSET="$(kubectl exec -n "$NAMESPACE" "$MM2_POD" -- sh -c \
  "/opt/kafka/bin/kafka-get-offsets.sh --bootstrap-server $SELFHOSTED_BOOTSTRAP --topic $TOPIC --time -1" \
  | grep "^${TOPIC}:${PARTITION}:" | cut -d: -f3)"
echo "self-hosted end-offset = $SELFHOSTED_OFFSET"

echo ""
echo ">> Offset MM2 da commit doc xong (Connect REST API /connectors/.../offsets)"
OFFSETS_JSON="$(kubectl exec -n "$NAMESPACE" "$MM2_POD" -- sh -c \
  "curl -s 'localhost:8083/connectors/${CONNECTOR_URLENC}/offsets'")"
echo "$OFFSETS_JSON"

# Khong dung jq (khong co san trong Git Bash) - parse bang grep/sed.
# JSON dang: {"offsets":[{"partition":{...,"partition":0,"topic":"orders"},"offset":{"offset":235293}}]}
# Lay so cuoi cung trong pattern "offset":{"offset":<N>}
MM2_COMMITTED_OFFSET="$(printf '%s' "$OFFSETS_JSON" | grep -oE '"offset":\{"offset":[0-9]+' | grep -oE '[0-9]+$' | head -1 || true)"

if [ -z "${MM2_COMMITTED_OFFSET:-}" ]; then
  echo ""
  echo "!! Khong tim duoc offset trong JSON (co the field name khac ban Kafka Connect nay)." >&2
  echo "!! Doc JSON o tren bang mat, sua jq filter trong script cho khop cau truc that." >&2
  exit 2
fi

LAG=$((SELFHOSTED_OFFSET - MM2_COMMITTED_OFFSET))
echo ""
echo "MM2 da doc toi offset = $MM2_COMMITTED_OFFSET"
echo "LAG chinh xac = $LAG"

if [ "$LAG" -le "$LAG_THRESHOLD" ]; then
  echo "OK — lag <= $LAG_THRESHOLD, du an toan de Promote."
  exit 0
else
  echo "CHUA OK — lag > $LAG_THRESHOLD, doi them roi chay lai."
  exit 1
fi
