#!/usr/bin/env bash
# CDO08-REL-16 - VALKEY-MIGRATION-PLAN.md BƯỚC 1.4: spin up a short-lived debug pod
# and confirm the migration bridge NLB is actually reachable on 6379 from inside
# the VPC, before calling the real AWS start-migration API. Read-only network test.
set -euo pipefail

NAMESPACE="techx-tf4"

BRIDGE_HOST=$(kubectl get svc valkey-migration-bridge -n "$NAMESPACE" \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

echo "Testing TCP reachability to $BRIDGE_HOST:6379 ..."

# VAP-compliant debug pod: non-root, pinned tag, resource limits, drop ALL capabilities.
kubectl run valkey-migration-net-test --rm -i --restart=Never \
  --namespace "$NAMESPACE" \
  --image=busybox:1.36.1 \
  --overrides='{
    "spec": {
      "securityContext": {"runAsNonRoot": true, "runAsUser": 65534, "seccompProfile": {"type": "RuntimeDefault"}},
      "containers": [{
        "name": "valkey-migration-net-test",
        "image": "busybox:1.36.1",
        "securityContext": {"allowPrivilegeEscalation": false, "capabilities": {"drop": ["ALL"]}},
        "resources": {"requests": {"cpu": "5m", "memory": "8Mi"}, "limits": {"cpu": "25m", "memory": "32Mi"}}
      }]
    }
  }' \
  -- sh -c "nc -z -v -w10 $BRIDGE_HOST 6379 && echo '[OK] Port 6379 on internal NLB is reachable from VPC subnets.'"
