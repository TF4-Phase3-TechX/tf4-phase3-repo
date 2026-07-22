#!/usr/bin/env bash
# CDO08-REL-16 - VALKEY-MIGRATION-PLAN.md BƯỚC 3.7: 3-phase zero-downtime TLS
# enablement on ElastiCache, run AFTER cutover is stable (not before, unlike
# the earlier cold-cutover approach this plan supersedes). ElastiCache stays
# at transit_encryption_mode=preferred throughout phases 1-2 (accepts both
# plaintext and TLS clients), only moving to "required" in phase 3 once no
# client uses plaintext anymore.
#
# Usage: 07-enable-tls.sh <1|2|3>
set -euo pipefail

PHASE="${1:?Usage: 07-enable-tls.sh <1|2|3>}"
NAMESPACE="techx-tf4"

case "$PHASE" in
  1)
    echo "Phase 1: confirm ASM secret techx/tf4/elasticache-valkey has tls_enabled+password set."
    echo "(Load via 'aws secretsmanager put-secret-value', then verify ExternalSecret Ready=True:)"
    kubectl get externalsecret elasticache-valkey-secret -n "$NAMESPACE" \
      -o jsonpath='{.status.conditions}'
    ;;
  2)
    echo "Phase 2: cart already reads VALKEY_TLS/VALKEY_PASSWORD from the secret once"
    echo "managedData.valkey.enabled=true (see _pod.tpl). Roll cart so every replica is"
    echo "actually connecting over TLS before touching transit_encryption_mode:"
    kubectl rollout restart deployment/cart -n "$NAMESPACE" 2>/dev/null || \
      kubectl argo rollouts restart cart -n "$NAMESPACE"
    echo "Verify no plaintext connections remain (check cart logs for ssl=false) before phase 3."
    ;;
  3)
    echo "Phase 3: flip ElastiCache to transit_encryption_mode=required (Terraform)."
    echo "Requires TF_VALKEY_AUTH_TOKEN GitHub secret set; the workflow passes it as"
    echo "TF_VAR_valkey_auth_token. Set valkey_transit_encryption_mode=\"required\""
    echo "only after Cart is confirmed to connect through TLS."
    echo "Apply via the terraform-apply pipeline, not directly from this script."
    ;;
  *)
    echo "Unknown phase: $PHASE (expected 1, 2, or 3)" >&2
    exit 1
    ;;
esac
