#!/usr/bin/env bash
# Local-only C0G-17 runtime evidence capture through the public ALB.
set -euo pipefail

ALB_URL="${ALB_URL:-http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com}"
SETTLING_SECONDS="${SETTLING_SECONDS:-660}"
WINDOW_SECONDS="${WINDOW_SECONDS:-600}"
PROM_API="$ALB_URL/grafana/api/datasources/uid/webstore-metrics/resources/api/v1/query"
RATE_QUERY='sum(rate(traces_span_metrics_calls_total{service_name="load-generator"}[5m])) or vector(0)'
INCREASE_QUERY='sum(increase(traces_span_metrics_calls_total{service_name="load-generator"}[10m])) or vector(0)'

stamp() {
  py -3 -c 'import time; from datetime import datetime, timezone; now = time.time(); print(datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), int(now * 1_000_000))'
}

prometheus_query() {
  curl -fsSGL --max-time 20 "$PROM_API" --data-urlencode "query=$1"
}

locust_state() {
  curl -fsSL --max-time 20 "$ALB_URL/loadgen/" |
    py -3 -c 'import json,re,sys; match = re.search(r"window\.templateArgs\s*=\s*(\{.*?\})\s*(?:;)?\s*</script>", sys.stdin.read(), re.S); assert match, "Locust template arguments not found"; data = json.loads(match.group(1)); print(json.dumps({key: data[key] for key in ("state", "user_count", "host", "num_users", "spawn_rate")}, separators=(",", ":")))'
}

printf 'locust_pre_window='; locust_state
printf '\nSettling for %s seconds so UI checks do not enter the evidence window...\n' "$SETTLING_SECONDS"
sleep "$SETTLING_SECONDS"
read -r start_utc start_us <<EOF
$(stamp)
EOF
printf 'window_start_utc=%s\nwindow_start_us=%s\n' "$start_utc" "$start_us"
printf 'rate_start='; prometheus_query "$RATE_QUERY"
printf '\nincrease_start='; prometheus_query "$INCREASE_QUERY"
printf '\nSleeping %s seconds for bounded idle observation...\n' "$WINDOW_SECONDS"
sleep "$WINDOW_SECONDS"
read -r end_utc end_us <<EOF
$(stamp)
EOF
printf 'window_end_utc=%s\nwindow_end_us=%s\n' "$end_utc" "$end_us"
printf 'rate_end='; prometheus_query "$RATE_QUERY"
printf '\nincrease_end='; prometheus_query "$INCREASE_QUERY"
printf '\njaeger='; curl -fsSGL --max-time 20 "$ALB_URL/jaeger/ui/api/traces" --data-urlencode 'service=load-generator' --data-urlencode "start=$start_us" --data-urlencode "end=$end_us" --data-urlencode 'limit=1000'
printf '\nlocust_post_window='; locust_state
