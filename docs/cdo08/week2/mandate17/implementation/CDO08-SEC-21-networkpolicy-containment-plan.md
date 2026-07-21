# CDO08-SEC-21 NetworkPolicy Support Check And Traffic Map

Date: 2026-07-21

Scope: Subtask "Verify NetworkPolicy support and current traffic map".

## Summary

Current cluster check shows EKS is using AWS VPC CNI `v1.21.2-eksbuild.2`. The addon schema supports `enableNetworkPolicy`, and the `aws-node` DaemonSet runs the `aws-eks-nodeagent` sidecar.

Initial finding: the sidecar was started with `--enable-network-policy=false`, so NetworkPolicy objects were not enforceable at the start of this task.

Final finding after approved addon update: `aws-node` rolled out successfully and `aws-eks-nodeagent` is now started with `--enable-network-policy=true`; a test namespace egress deny blocked both internal ClusterIP traffic and internet egress. NetworkPolicy enforcement is verified.

This branch codifies the required Terraform addon configuration:

```hcl
vpc-cni = {
  configuration_values = jsonencode({
    enableNetworkPolicy = "true"
  })
}
```

The live addon update was applied after explicit approval and must remain represented in Terraform to prevent drift.

## Support Check Evidence

Commands run:

```bash
kubectl config current-context
kubectl get pods -n kube-system -o wide
kubectl get ns
kubectl get networkpolicy -A
kubectl get ds aws-node -n kube-system -o yaml
aws eks describe-addon --region us-east-1 --cluster-name techx-tf4-cluster --addon-name vpc-cni --profile TF4-SecurityIAMSSOManager-511825856493
aws eks describe-addon-configuration --region us-east-1 --addon-name vpc-cni --addon-version v1.21.2-eksbuild.2 --profile TF4-SecurityIAMSSOManager-511825856493
aws eks update-addon --region us-east-1 --cluster-name techx-tf4-cluster --addon-name vpc-cni --configuration-values file://infra/terraform/vpc-cni-networkpolicy-config.json --resolve-conflicts OVERWRITE --profile TF4-SecurityIAMSSOManager-511825856493
aws eks wait addon-active --region us-east-1 --cluster-name techx-tf4-cluster --addon-name vpc-cni --profile TF4-SecurityIAMSSOManager-511825856493
kubectl rollout status daemonset/aws-node -n kube-system --timeout=180s
```

Observed:

- Current context: `arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster`.
- `aws-node` pods are `2/2 Running`, which includes `aws-node` and `aws-eks-nodeagent`.
- EKS addon `vpc-cni` is `ACTIVE`, version `v1.21.2-eksbuild.2`.
- Addon configuration schema includes `enableNetworkPolicy`.
- Before update, `aws-eks-nodeagent` was configured with `--enable-network-policy=false`.
- After update, `aws-eks-nodeagent` is configured with `--enable-network-policy=true`; `NETWORK_POLICY_ENFORCING_MODE=standard`.
- Existing NetworkPolicy inventory has one Strimzi-managed policy: `techx-tf4/orders-mirrormaker2-mirrormaker2`.

Conclusion: the cluster has the right plugin family, schema support, and live NetworkPolicy enforcement.

## Enforcement Test Evidence

Test namespace: `cdo08-sec21-np-test`.

Setup:

- `echo` pod + Service on `5678/TCP`.
- `attacker` pod using `curlimages/curl:8.10.1`.
- Both pods used non-root runtime hardening and explicit CPU/memory resources to satisfy current admission policies.

Baseline before policy:

```text
kubectl exec -n cdo08-sec21-np-test attacker -- curl -sS --connect-timeout 3 http://echo:5678
sec21-ok

kubectl exec -n cdo08-sec21-np-test attacker -- curl -sS --connect-timeout 3 https://example.com
<!doctype html><html lang="en"><head><title>Example Domain</title>...
```

Policy applied:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-attacker-egress
  namespace: cdo08-sec21-np-test
spec:
  podSelector:
    matchLabels:
      app: attacker
  policyTypes:
    - Egress
  egress: []
```

After policy:

```text
kubectl exec -n cdo08-sec21-np-test attacker -- curl -sS --connect-timeout 3 --max-time 5 http://echo:5678
curl: (28) Resolving timed out after 5002 milliseconds
command terminated with exit code 28

kubectl exec -n cdo08-sec21-np-test attacker -- curl -sS --connect-timeout 3 --max-time 5 https://example.com
curl: (28) Resolving timed out after 5001 milliseconds
command terminated with exit code 28

kubectl get svc echo -n cdo08-sec21-np-test -o wide
echo   ClusterIP   172.20.245.145   <none>   5678/TCP

kubectl exec -n cdo08-sec21-np-test attacker -- curl -sS --connect-timeout 3 --max-time 5 http://172.20.245.145:5678
curl: (28) Failed to connect to 172.20.245.145 port 5678 after 3002 ms: Timeout was reached
command terminated with exit code 28
```

The namespace was deleted after evidence capture:

```text
kubectl delete namespace cdo08-sec21-np-test --wait=false
namespace "cdo08-sec21-np-test" deleted
```

## Current Namespaces

Observed namespaces:

```text
argo-rollouts
argocd
default
external-secrets
kafka-operator
kube-node-lease
kube-public
kube-system
kyverno
techx-admission-test
techx-observability
techx-sec17-admission-test
techx-tf4
```

## Namespace Exclude List

Do not enforce default deny immediately on these namespaces:

| Namespace | Reason |
|---|---|
| `kube-system` | Hosts CNI, CoreDNS, kube-proxy, EBS CSI, AWS Load Balancer Controller, Karpenter, and EKS Pod Identity agents. Enforcing before dedicated system policy can break cluster networking/control plane integrations. |
| `kube-node-lease` | Kubernetes system lease namespace; no app containment value for this task. |
| `kube-public` | Kubernetes system public namespace; no app containment value for this task. |
| `argocd` | GitOps controller path. Enforce only after mapping repo-server, API server, Redis, and webhook flows. |
| `argo-rollouts` | Rollout controller path. Enforce only after controller/API flows are mapped. |
| `external-secrets` | Needs AWS API and Kubernetes API access; enforce only after External Secrets webhook/controller egress is mapped. |
| `kafka-operator` | Strimzi controller/operator path; enforce only after operator-to-Kafka and API server flows are mapped. |
| `kyverno` | Admission controller path; enforce only after webhook/API server flows are mapped. |
| `techx-observability` | Contains OTel Collector, Prometheus, Grafana, Jaeger, OpenSearch, and alerting. Enforce after app telemetry and scrape/query flows are mapped. |

Primary enforcement target for the first production app rollout: `techx-tf4`.

`cloudflare-access` was requested for inventory if present. It was not present in the namespace list captured on 2026-07-21.

## Service Inventory

Observed relevant services:

| Namespace | Service | Ports |
|---|---|---|
| `kube-system` | `kube-dns` | `53/UDP`, `53/TCP`, `9153/TCP` |
| `techx-tf4` | `frontend-proxy` | `8080/TCP` |
| `techx-tf4` | `frontend` | `8080/TCP` |
| `techx-tf4` | `ad` | `8080/TCP` |
| `techx-tf4` | `cart` | `8080/TCP` |
| `techx-tf4` | `checkout` | `8080/TCP` |
| `techx-tf4` | `currency` | `8080/TCP` |
| `techx-tf4` | `email` | `8080/TCP` |
| `techx-tf4` | `flagd` | `8013/TCP`, `8016/TCP` |
| `techx-tf4` | `image-provider` | `8081/TCP` |
| `techx-tf4` | `kafka` | `9092/TCP`, `9093/TCP` |
| `techx-tf4` | `load-generator` | `8089/TCP` |
| `techx-tf4` | `payment` | `8080/TCP` |
| `techx-tf4` | `postgresql` | `5432/TCP` |
| `techx-tf4` | `product-catalog` | `8080/TCP` |
| `techx-tf4` | `product-reviews` | `3551/TCP` |
| `techx-tf4` | `quote` | `8080/TCP` |
| `techx-tf4` | `recommendation` | `8080/TCP` |
| `techx-tf4` | `shipping` | `8080/TCP` |
| `techx-tf4` | `valkey-cart` | `6379/TCP` |
| `techx-observability` | `otel-collector` | `4317/TCP`, `4318/TCP`, `8888/TCP`, `14250/TCP`, `14268/TCP`, `6831/UDP`, `9411/TCP` |
| `techx-observability` | `grafana` | `80/TCP` |
| `techx-observability` | `jaeger` | `16686/TCP`, `4317/TCP`, `4318/TCP`, others |
| `techx-observability` | `prometheus` | `9090/TCP` |
| `techx-observability` | `opensearch` | `9200/TCP`, `9300/TCP`, `9600/TCP` |

The migration bridge LoadBalancer services are temporary operational paths and should not be included in broad application allowlists:

- `techx-tf4/postgresql-migration-bridge:5432`
- `techx-tf4/valkey-migration-bridge:6379`
- `techx-observability/postgresql-migration-bridge:5432`

## Traffic Map For `techx-tf4`

Required application ingress:

| Source | Destination | Port | Reason |
|---|---|---:|---|
| ALB/VPC target traffic | `frontend-proxy` | 8080 | Public storefront ingress uses AWS ALB target-type `ip`. Source pod selector is not available; allow by approved VPC/load balancer CIDR after confirming exact ranges. |
| `load-generator` | `frontend-proxy` | 8080 | Controlled smoke/load test path. |

Required service-to-service traffic:

| Source | Destination | Port | Reason |
|---|---|---:|---|
| `frontend-proxy` | `frontend` | 8080 | Storefront proxy to app. |
| `frontend-proxy` | `image-provider` | 8081 | Image route through proxy. |
| `frontend-proxy` | `flagd` | 8013, 8016 | Feature flag and OFREP route through proxy. |
| `frontend-proxy` | `grafana.techx-observability` | 80 | Existing proxy ops route; do not open from all pods. |
| `frontend-proxy` | `jaeger.techx-observability` | 16686 | Existing proxy ops route; do not open from all pods. |
| `frontend` | `ad` | 8080 | Storefront ads path. |
| `frontend` | `cart` | 8080 | Cart API path. |
| `frontend` | `checkout` | 8080 | Checkout API path. |
| `frontend` | `currency` | 8080 | Currency conversion path. |
| `frontend` | `product-catalog` | 8080 | Product browse/detail path. |
| `frontend` | `product-reviews` | 3551 | Review/AI assistant gRPC path. |
| `frontend` | `recommendation` | 8080 | Recommendation path. |
| `frontend` | `shipping` | 8080 | Shipping quote path. |
| `checkout` | `cart` | 8080 | Checkout reads/clears cart. |
| `checkout` | `currency` | 8080 | Checkout currency conversion. |
| `checkout` | `email` | 8080 | Checkout confirmation email call. |
| `checkout` | `payment` | 8080 | Checkout payment call. |
| `checkout` | `product-catalog` | 8080 | Checkout product lookup. |
| `checkout` | `shipping` | 8080 | Checkout shipping quote call. |
| `checkout` | `kafka` | 9092 | Order event publish. |
| `accounting` | `kafka` | 9092 | Async order event consume. |
| `accounting` | `postgresql` | 5432 | Accounting database connection from `DB_CONNECTION_STRING`. |
| `fraud-detection` | `kafka` | 9092 | Async order event consume. |
| `cart` | `valkey-cart` | 6379 | Cart cache/store. |
| `product-catalog` | `postgresql` | 5432 | Catalog database. |
| `product-reviews` | `product-catalog` | 8080 | Review service product lookup. |
| `product-reviews` | `postgresql` | 5432 | Review database. |
| `recommendation` | `product-catalog` | 8080 | Recommendation product lookup. |
| `shipping` | `quote` | 8080 | Shipping quote backend. |

Shared required egress:

| Source | Destination | Port | Reason |
|---|---|---:|---|
| `techx-tf4` selected app pods | `kube-system/kube-dns` | 53 UDP/TCP | DNS resolution for Kubernetes services. |
| instrumented app pods | `otel-collector.techx-observability` | 4317, 4318 | OTLP telemetry. |
| feature-flag clients | `flagd` | 8013 | Feature flag evaluation. |
| `load-generator` | `flagd` | 8013, 8016 | Load-test flag checks. |

External egress exceptions:

| Source | Destination | Reason | Status |
|---|---|---|---|
| `product-reviews` | AWS Bedrock in `us-east-1` | AI review path uses EKS Pod Identity and Bedrock. Kubernetes NetworkPolicy cannot safely express AWS service FQDNs with the standard API; require VPC endpoint/CIDR or CNI-specific FQDN policy before enforcing default-deny egress on this pod. | Needs owner-approved egress design before enforcement. |
| `external-secrets` | AWS Secrets Manager / STS | Secret sync. | Excluded from first production enforce scope. |

## Rollout Gate For Next Subtask

Before applying default-deny policies in `techx-tf4`:

1. Use the traffic map above as the allowlist source.
2. Keep production rollout in GitOps/source manifests, not ad hoc `kubectl apply`.
3. Apply default-deny only with DNS, app, telemetry, and approved external exceptions present.
4. Smoke test storefront/checkout immediately after rollout.

Subtask 1 acceptance status: NetworkPolicy support and enforcement verified; traffic map and namespace exclude list are ready for allowlist implementation.
