#!/usr/bin/env bash
# CDO08-REL-16 - VALKEY-MIGRATION-PLAN.md BƯỚC 3.4: promote ElastiCache to
# primary read/write and tear down the replication link back to the source.
# Run only AFTER the pre-cutover parity check (§5.1) has passed while writes
# are frozen (04-freeze-writes.sh).
set -euo pipefail

RG_ID="techx-tf4-valkey-cart"

echo "Completing migration for $RG_ID (promoting ElastiCache to primary) ..."
aws elasticache complete-migration \
  --replication-group-id "$RG_ID" \
  --force false

aws elasticache describe-replication-groups --replication-group-id "$RG_ID" \
  --query 'ReplicationGroups[0].Status' --output text

echo "Migration complete. Proceed to 06-promote-rollout.sh."
