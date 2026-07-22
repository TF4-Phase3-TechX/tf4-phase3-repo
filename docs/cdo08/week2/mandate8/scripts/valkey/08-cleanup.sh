#!/usr/bin/env bash
# CDO08-REL-16 - VALKEY-MIGRATION-PLAN.md BƯỚC 3.8: cleanup after cutover has
# baked stable. Removes ONLY the temporary migration bridge - it does NOT
# delete the old valkey-cart Deployment/PVC. That decommission is gated on
# REL-18 (24-48h stable bake, separate ticket), matching the retention
# discipline used throughout Mandate 8.
set -euo pipefail

echo "This script only disables the migration bridge. It does NOT delete valkey-cart"
echo "(that is REL-18's job, after a stable bake period). Manual steps:"
echo ""
echo "1. Set valkeyMigrationBridge.enabled=false in the production GitOps values"
echo "   (environments/production/app-values.yaml), commit, push, let ArgoCD sync."
echo "2. Confirm the bridge Service is gone:"
echo "     kubectl get svc valkey-migration-bridge -n techx-tf4"
echo "   (expect: not found)"
echo "3. Do NOT set components.valkey-cart.enabled=false or delete valkey-cart-pvc"
echo "   here - see REL-18 gate in CDO08-REL-16-valkey-cutover-plan.md §8."
