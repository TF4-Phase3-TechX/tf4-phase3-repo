# CDO08-SEC-21 Network Containment Evidence

Date: 2026-07-21

Status: pending PM execution.

Reason:
- The assistant is explicitly prohibited from running `kubectl apply` or other live rollout commands for this task.
- SEC-21 NetworkPolicies are not live at the time this document is written.
- This document records the evidence procedure, expected results, and capture template for PM to execute after applying the GitOps manifests.

## Preconditions

PM must apply the GitOps manifests using:

- GitOps runbook: `environments/production/runbooks/mandate17/CDO08-SEC-21-pm-apply-runbook.md`
- NetworkPolicy manifest: `environments/production/raw/networkpolicies-techx-tf4.yaml`

Before evidence collection:

```powershell
kubectl get networkpolicy -n techx-tf4 -l app.kubernetes.io/part-of=cdo08-sec21
kubectl get networkpolicy -n techx-tf4 orders-mirrormaker2-mirrormaker2
kubectl get deploy -n techx-tf4 -o custom-columns=NAME:.metadata.name,READY:.status.readyReplicas,DESIRED:.status.replicas --no-headers
kubectl get rollout -n techx-tf4 cart
kubectl logs -n techx-tf4 orders-mirrormaker2-mirrormaker2-0 --since=2m --tail=80
```

Required precondition:
- SEC-21 policies exist.
- Existing Strimzi policy `orders-mirrormaker2-mirrormaker2` still exists.
- All app deployments are Ready.
- Cart rollout is Available.
- MirrorMaker2 still reports health/connector `200` and offset commits.

## Attacker Pod

Create a temporary attacker pod in the enforced namespace. It uses the `load-generator` component label to prove that a compromised allowed workload can still reach only the storefront path and cannot pivot to internal services.

PM command:

```powershell
kubectl run sec21-attacker -n techx-tf4 --image=busybox:1.36.1 --restart=Never --labels='app.kubernetes.io/component=load-generator,cdo08.techx.io/test-role=attacker' --overrides='{"spec":{"automountServiceAccountToken":false,"securityContext":{"runAsNonRoot":true,"runAsUser":65534,"runAsGroup":65534,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"sec21-attacker","image":"busybox:1.36.1","command":["sh","-c","sleep 3600"],"resources":{"requests":{"cpu":"25m","memory":"32Mi"},"limits":{"cpu":"100m","memory":"64Mi"}},"securityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true}}]}}'
kubectl wait --for=condition=Ready pod/sec21-attacker -n techx-tf4 --timeout=90s
kubectl get pod -n techx-tf4 sec21-attacker -o wide
```

Expected:

```text
sec21-attacker   1/1   Running
```

## Allowed Tests

DNS should pass:

```powershell
kubectl exec -n techx-tf4 sec21-attacker -- nslookup frontend-proxy.techx-tf4.svc.cluster.local
```

Expected:

```text
Server:   172.20.0.10
Name:     frontend-proxy.techx-tf4.svc.cluster.local
Address:  172.20.74.72
```

Approved storefront path should pass:

```powershell
kubectl exec -n techx-tf4 sec21-attacker -- wget -S -O /dev/null -T 10 http://frontend-proxy.techx-tf4.svc.cluster.local:8080/
```

Expected:

```text
HTTP/1.1 200 OK
```

## Denied Tests

Direct checkout access should be denied:

```powershell
kubectl exec -n techx-tf4 sec21-attacker -- sh -c "if nc -zvw 3 checkout.techx-tf4.svc.cluster.local 8080; then echo UNEXPECTED_PASS_checkout; exit 1; else echo DENIED_EXPECTED_checkout; fi"
```

Expected:

```text
DENIED_EXPECTED_checkout
Connection timed out
```

PostgreSQL access should be denied:

```powershell
kubectl exec -n techx-tf4 sec21-attacker -- sh -c "if nc -zvw 3 postgresql.techx-tf4.svc.cluster.local 5432; then echo UNEXPECTED_PASS_postgresql; exit 1; else echo DENIED_EXPECTED_postgresql; fi"
```

Expected:

```text
DENIED_EXPECTED_postgresql
Connection timed out
```

Kafka access should be denied for this attacker role:

```powershell
kubectl exec -n techx-tf4 sec21-attacker -- sh -c "if nc -zvw 3 kafka.techx-tf4.svc.cluster.local 9092; then echo UNEXPECTED_PASS_kafka; exit 1; else echo DENIED_EXPECTED_kafka; fi"
```

Expected:

```text
DENIED_EXPECTED_kafka
Connection timed out
```

Observability/admin endpoint access should be denied:

```powershell
kubectl exec -n techx-tf4 sec21-attacker -- sh -c "if nc -zvw 3 grafana.techx-observability.svc.cluster.local 80; then echo UNEXPECTED_PASS_grafana; exit 1; else echo DENIED_EXPECTED_grafana; fi"
```

Expected:

```text
DENIED_EXPECTED_grafana
Connection timed out
```

Arbitrary internet egress should be denied:

```powershell
kubectl exec -n techx-tf4 sec21-attacker -- sh -c "if wget -q -O /dev/null -T 5 http://example.com; then echo UNEXPECTED_PASS_internet; exit 1; else echo DENIED_EXPECTED_internet; fi"
```

Expected:

```text
DENIED_EXPECTED_internet
wget: download timed out
```

## Revenue Path Smoke

PM should also run the checkout smoke from the PM apply runbook and paste output here.

Expected:

```text
products_http=200
product_http=200
cart_http=200
checkout_http=200
```

## MirrorMaker2 Guardrail

Because the prior rollback was caused by missing MirrorMaker2 allowlist, PM must capture this after apply:

```powershell
kubectl logs -n techx-tf4 orders-mirrormaker2-mirrormaker2-0 --since=3m --tail=120
```

Expected healthy signals:

```text
GET /health HTTP/1.1" 200
GET /connectors/.../status HTTP/1.1" 200
WorkerSourceTask{id=self-hosted->msk.MirrorSourceConnector-0} Committing offsets
```

Rollback trigger:
- Any new `Connection timed out` from MirrorMaker2 to `kafka:9092`.
- Kafka readiness regression.
- Checkout smoke failure.

Rollback command:

```powershell
kubectl delete networkpolicy -n techx-tf4 -l app.kubernetes.io/part-of=cdo08-sec21
```

## Cleanup

PM must delete temporary test pods:

```powershell
kubectl delete pod -n techx-tf4 sec21-attacker sec21-checkout-smoke --ignore-not-found=true
kubectl get pod -n techx-tf4 -l cdo08.techx.io/test-role -o name
```

Expected:

```text
<no output>
```

## Evidence Capture Template

After PM executes the commands, replace this section with the captured output:

```text
Applied by:
Applied at:
Commit/PR:

NetworkPolicy list:

Attacker pod status:

Allowed DNS output:

Allowed storefront output:

Denied checkout output:

Denied PostgreSQL output:

Denied Kafka output:

Denied Grafana output:

Denied internet output:

Checkout smoke output:

MirrorMaker2 health/log output:

Cleanup output:
```

Acceptance status after PM execution:
- At least one allowed connection passes.
- Multiple denied connections fail as expected.
- Internet egress is blocked for attacker pod.
- No production traffic impact is observed.
