#!/usr/bin/env bash
# CDO08-REL-16 - VALKEY-MIGRATION-PLAN.md BƯỚC 3.2: freeze writes on the old
# EKS valkey-cart so the pre-cutover parity check (§5.1) compares a stable
# snapshot. CLIENT PAUSE blocks writes only (reads still served) for 5 minutes;
# rollback-02-unlock-source.sh (or 06-promote-rollout.sh) releases it.
set -euo pipefail

NAMESPACE="techx-tf4"
PAUSE_MS="${PAUSE_MS:-300000}"

echo "Pausing writes on valkey-cart for ${PAUSE_MS}ms ..."
kubectl exec -n "$NAMESPACE" deploy/valkey-cart -- \
  redis-cli CLIENT PAUSE "$PAUSE_MS" WRITE

echo "Writes paused. Proceed to pre-cutover parity check (§5.1), then 05-complete-migration.sh."
