#!/usr/bin/env bash
# CDO08-REL-16 - VALKEY-MIGRATION-PLAN.md §4: release the write-pause placed on
# the old valkey-cart source by 04-freeze-writes.sh, restoring normal traffic.
# Run after rollback-01-abort-rollout.sh (TRƯỜNG HỢP 1), or after the
# riot-redis-backfill Job has finished (TRƯỜNG HỢP 2, see values.yaml
# riotRedisBackfill / templates/riot-redis-backfill-job.yaml).
set -euo pipefail

NAMESPACE="techx-tf4"

echo "Unpausing writes on valkey-cart ..."
kubectl exec -n "$NAMESPACE" deploy/valkey-cart -- redis-cli CLIENT UNPAUSE

echo "Source unlocked. Verify cart/checkout smoke test against valkey-cart before declaring rollback complete."
