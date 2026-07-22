#!/usr/bin/env bash
# CDO08-REL-16 - VALKEY-MIGRATION-PLAN.md BƯỚC 2.1: start the AWS ElastiCache
# Online Migration, replicating from the self-hosted valkey-cart (via the
# temporary NLB bridge) into the managed replication group.
set -euo pipefail

RG_ID="techx-tf4-valkey-cart"
NAMESPACE="techx-tf4"

BRIDGE_HOST=$(kubectl get svc valkey-migration-bridge -n "$NAMESPACE" \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

echo "Starting online migration: source=$BRIDGE_HOST:6379 -> target=$RG_ID"

aws elasticache start-migration \
  --replication-group-id "$RG_ID" \
  --customer-node-endpoint-list "Address=$BRIDGE_HOST,Port=6379"

aws elasticache describe-replication-groups --replication-group-id "$RG_ID" \
  --query 'ReplicationGroups[0].Status' --output text
