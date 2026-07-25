#!/usr/bin/env bash
# CDO08-REL-16 - VALKEY-MIGRATION-PLAN.md BƯỚC 1.4: spin up a short-lived debug pod
# and confirm the migration bridge NLB is actually reachable on 6379 from inside
# the VPC, before calling the real AWS start-migration API. Read-only network test.
set -euo pipefail

NAMESPACE="techx-tf4"

BRIDGE_HOST=$(kubectl get svc valkey-migration-bridge -n "$NAMESPACE" \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

echo "Testing TCP reachability to $BRIDGE_HOST:6379 ..."

POD_NAME="valkey-migration-net-test"
POD_MANIFEST="$(mktemp)"
trap 'kubectl delete pod "$POD_NAME" -n "$NAMESPACE" --ignore-not-found >/dev/null; rm -f "$POD_MANIFEST"' EXIT

# VAP-compliant debug pod: non-root, pinned tag, resource limits, drop ALL capabilities.
# Applied as a manifest (not `kubectl run --rm -i`) — the latter races between attach and
# pod completion on fast-exiting containers and can silently drop the output.
cat > "$POD_MANIFEST" <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: $POD_NAME
  namespace: $NAMESPACE
spec:
  restartPolicy: Never
  securityContext:
    runAsNonRoot: true
    runAsUser: 65534
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: $POD_NAME
      image: busybox:1.36.1
      command: ["sh", "-c", "nc -z -v -w10 $BRIDGE_HOST 6379 && echo '[OK] Port 6379 on internal NLB is reachable from VPC subnets.'"]
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
      resources:
        requests:
          cpu: 5m
          memory: 8Mi
        limits:
          cpu: 25m
          memory: 32Mi
EOF

kubectl apply -f "$POD_MANIFEST" >/dev/null
kubectl wait --for=jsonpath='{.status.phase}'=Succeeded --timeout=30s -n "$NAMESPACE" "pod/$POD_NAME" \
  || { echo "::error::Pod did not reach Succeeded within 30s"; kubectl logs "$POD_NAME" -n "$NAMESPACE" || true; exit 1; }
kubectl logs "$POD_NAME" -n "$NAMESPACE"
