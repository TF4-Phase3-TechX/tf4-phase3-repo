#!/usr/bin/env bash

set -euo pipefail

OBS_NAMESPACE="${OBS_NAMESPACE:-techx-observability}"
EXPECTED_RULE_COUNT="${EXPECTED_RULE_COUNT:-15}"

PROMETHEUS_RULES_PATH="/api/v1/namespaces/${OBS_NAMESPACE}/services/http:prometheus:9090/proxy/api/v1/rules"

echo "Checking mounted flash-sale rule ConfigMap..."
kubectl -n "$OBS_NAMESPACE" get configmap prometheus-flash-sale-alerts >/dev/null

echo "Checking Prometheus rule load state..."
rules_json="$(kubectl get --raw "$PROMETHEUS_RULES_PATH")"
loaded_count="$(
  jq '[
    .data.groups[]
    | select(.name | startswith("flash-sale-"))
    | .rules[]
    | select(.type == "alerting")
  ] | length' <<<"$rules_json"
)"

if [[ "$loaded_count" -ne "$EXPECTED_RULE_COUNT" ]]; then
  echo "Expected ${EXPECTED_RULE_COUNT} flash-sale alert rules, found ${loaded_count}." >&2
  exit 1
fi

jq -e '
  [
    .data.groups[]
    | select(.name | startswith("flash-sale-"))
    | .rules[]
    | select(.type == "alerting")
    | select((.health // "unknown") != "ok")
  ] | length == 0
' <<<"$rules_json" >/dev/null

echo "Checking required owner, severity and wait duration fields..."
jq -e '
  [
    .data.groups[]
    | select(.name | startswith("flash-sale-"))
    | .rules[]
    | select(.type == "alerting")
    | select(
        (.labels.owner // "") == ""
        or (.labels.severity // "") == ""
        or (.duration // 0) <= 0
      )
  ] | length == 0
' <<<"$rules_json" >/dev/null

echo "Flash-sale alert verification passed: ${loaded_count} healthy rules."
echo "NOTE: Alertmanager is currently disabled. Alert visibility is via Prometheus /alerts and the Grafana Flash Sale Alert State dashboard."
