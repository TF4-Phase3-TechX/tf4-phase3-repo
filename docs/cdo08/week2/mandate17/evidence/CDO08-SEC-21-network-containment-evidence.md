# CDO08-SEC-21 Network Containment Evidence

Date: 2026-07-21

Scope:
- Cluster: `techx-tf4-cluster`
- Namespace under enforcement: `techx-tf4`
- Policy source: GitOps repo branch `cdo08-sec-21-networkpolicy-containment`
- Attacker pod: temporary pod `sec21-attacker`, label `app.kubernetes.io/component=load-generator`

Safety notes:
- The attacker pod used `automountServiceAccountToken: false`, non-root UID/GID, dropped Linux capabilities, `RuntimeDefault` seccomp, and read-only root filesystem.
- No production pod was exec'd for attacker tests.
- No Kubernetes Secret values were read.
- The attacker pod was deleted after evidence collection.

## Baseline Policy State

Applied policies included:

```text
sec21-default-deny-app-workloads
sec21-allow-dns-egress
sec21-allow-load-generator-egress
sec21-allow-frontend-proxy-ingress
sec21-allow-checkout-egress
sec21-allow-kafka-ingress-egress
sec21-allow-postgresql-client-egress
...
```

Important implementation note:
- AWS VPC CNI NetworkPolicy enforcement required Service ClusterIP `/32` allowlist entries for Service-name traffic paths.
- During evidence, `load-generator -> frontend-proxy` initially timed out until `172.20.74.72/32` was added to `sec21-allow-load-generator-egress`.

## Attacker Pod

Manifest summary:

```yaml
metadata:
  name: sec21-attacker
  namespace: techx-tf4
  labels:
    app.kubernetes.io/component: load-generator
    cdo08.techx.io/test-role: attacker
spec:
  automountServiceAccountToken: false
```

Runtime:

```text
NAME             READY   STATUS    RESTARTS   IP
sec21-attacker   1/1     Running   0          10.0.10.68
```

## Allowed Tests

DNS remained allowed:

```text
$ kubectl exec -n techx-tf4 sec21-attacker -- nslookup frontend-proxy.techx-tf4.svc.cluster.local
Server:         172.20.0.10
Address:        172.20.0.10:53

Name:   frontend-proxy.techx-tf4.svc.cluster.local
Address: 172.20.74.72
```

Approved storefront path remained allowed:

```text
$ kubectl exec -n techx-tf4 sec21-attacker -- wget -S -O /dev/null -T 10 http://frontend-proxy.techx-tf4.svc.cluster.local:8080/
Connecting to frontend-proxy.techx-tf4.svc.cluster.local:8080 (172.20.74.72:8080)
  HTTP/1.1 200 OK
  content-type: text/html; charset=utf-8
  content-length: 11347
  x-envoy-upstream-service-time: 10
'/dev/null' saved
```

## Denied Tests

Direct checkout service access was denied:

```text
$ kubectl exec -n techx-tf4 sec21-attacker -- sh -c "if nc -zvw 3 checkout.techx-tf4.svc.cluster.local 8080; then echo UNEXPECTED_PASS_checkout; exit 1; else echo DENIED_EXPECTED_checkout; fi"
DENIED_EXPECTED_checkout
nc: checkout.techx-tf4.svc.cluster.local (172.20.60.78:8080): Connection timed out
```

PostgreSQL access was denied:

```text
$ kubectl exec -n techx-tf4 sec21-attacker -- sh -c "if nc -zvw 3 postgresql.techx-tf4.svc.cluster.local 5432; then echo UNEXPECTED_PASS_postgresql; exit 1; else echo DENIED_EXPECTED_postgresql; fi"
DENIED_EXPECTED_postgresql
nc: postgresql.techx-tf4.svc.cluster.local (172.20.87.154:5432): Connection timed out
```

Kafka access was denied:

```text
$ kubectl exec -n techx-tf4 sec21-attacker -- sh -c "if nc -zvw 3 kafka.techx-tf4.svc.cluster.local 9092; then echo UNEXPECTED_PASS_kafka; exit 1; else echo DENIED_EXPECTED_kafka; fi"
DENIED_EXPECTED_kafka
nc: kafka.techx-tf4.svc.cluster.local (172.20.180.83:9092): Connection timed out
```

Observability/admin endpoint access was denied:

```text
$ kubectl exec -n techx-tf4 sec21-attacker -- sh -c "if nc -zvw 3 grafana.techx-observability.svc.cluster.local 3000; then echo UNEXPECTED_PASS_grafana; exit 1; else echo DENIED_EXPECTED_grafana; fi"
DENIED_EXPECTED_grafana
nc: grafana.techx-observability.svc.cluster.local (172.20.108.200:3000): Connection timed out
```

Arbitrary internet egress was denied:

```text
$ kubectl exec -n techx-tf4 sec21-attacker -- sh -c "if wget -q -O /dev/null -T 5 http://example.com; then echo UNEXPECTED_PASS_internet; exit 1; else echo DENIED_EXPECTED_internet; fi"
DENIED_EXPECTED_internet
wget: download timed out
```

## Revenue Path Check

Checkout smoke after policy fixes:

```text
$ kubectl logs -n techx-tf4 sec21-checkout-smoke
products_http=200
product_http=200
cart_http=200
checkout_http=200
```

Workload readiness after tests:

```text
accounting        1/1
checkout          2/2
frontend          2/2
frontend-proxy    2/2
kafka             1/1
product-catalog   2/2
shipping          2/2
valkey-cart       1/1
```

## Cleanup

Temporary pod cleanup:

```text
$ kubectl delete pod -n techx-tf4 sec21-attacker --ignore-not-found=true
$ kubectl get pod -n techx-tf4 sec21-attacker --ignore-not-found=true
<no output>
```

Result:
- Allowed connection passed: DNS and `load-generator` role to storefront via `frontend-proxy:8080`.
- Denied connections failed as expected: checkout direct access, PostgreSQL, Kafka, Grafana, and arbitrary internet egress.
- Production workloads remained Ready after the test.
