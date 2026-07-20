#!/usr/bin/env bash
# CDO08-REL-16 - VALKEY-MIGRATION-PLAN.md BƯỚC 2.2: poll CloudWatch ReplicationLag
# until the online migration link has fully caught up (0 seconds), holding steady.
# Blocks until caught up or TIMEOUT_SECONDS is reached.
set -euo pipefail

RG_ID="techx-tf4-valkey-cart"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-15}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-3600}"
STABLE_READS_REQUIRED=3

elapsed=0
stable_count=0

while [ "$elapsed" -lt "$TIMEOUT_SECONDS" ]; do
  LAG=$(aws cloudwatch get-metric-statistics \
    --namespace AWS/ElastiCache \
    --metric-name ReplicationLag \
    --dimensions Name=ReplicationGroupId,Value="$RG_ID" \
    --start-time "$(date -u -d '-5 minutes' +%Y-%m-%dT%H:%M:%S)" \
    --end-time "$(date -u +%Y-%m-%dT%H:%M:%S)" \
    --period 60 --statistics Average \
    --query 'Datapoints | sort_by(@, &Timestamp) | [-1].Average' --output text)

  echo "[$(date -u +%H:%M:%S)] ReplicationLag=${LAG:-N/A}s"

  if [ "${LAG:-999}" = "0.0" ] || [ "${LAG:-999}" = "0" ]; then
    stable_count=$((stable_count + 1))
    if [ "$stable_count" -ge "$STABLE_READS_REQUIRED" ]; then
      echo "Replication lag stable at 0 for $STABLE_READS_REQUIRED consecutive reads. Ready for cutover."
      exit 0
    fi
  else
    stable_count=0
  fi

  sleep "$POLL_INTERVAL_SECONDS"
  elapsed=$((elapsed + POLL_INTERVAL_SECONDS))
done

echo "TIMEOUT: replication lag did not stabilize at 0 within ${TIMEOUT_SECONDS}s." >&2
exit 1
