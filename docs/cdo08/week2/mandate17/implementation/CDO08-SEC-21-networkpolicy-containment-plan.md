# CDO08-SEC-21 NetworkPolicy Containment Plan

Date: 2026-07-21

Scope:
- Cluster: `techx-tf4-cluster`
- First enforcement namespace: `techx-tf4`
- Explicitly out of scope for first rollout: system/operator/observability namespaces listed below.

Execution rule for this task:
- The assistant must not run `kubectl apply`, `helm upgrade`, `terraform apply`, or any equivalent live mutating apply command.
- Any required apply/sync step is documented for PM execution with a reason and rollback command.

## NetworkPolicy Support Check

Read-only checks performed:

```bash
kubectl config current-context
aws eks describe-addon --region us-east-1 --cluster-name techx-tf4-cluster --addon-name vpc-cni --profile TF4-SecurityIAMSSOManager-511825856493
kubectl get ds aws-node -n kube-system -o yaml
kubectl get networkpolicy -A -o wide
kubectl get ns
```

Observed:

```text
context: arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster
vpc-cni addon: v1.21.2-eksbuild.2
vpc-cni status: ACTIVE
configurationValues: {"enableNetworkPolicy":"true"}
aws-eks-nodeagent arg: --enable-network-policy=true
NETWORK_POLICY_ENFORCING_MODE=standard
```

Current NetworkPolicy inventory after rollback:

```text
NAMESPACE   NAME                               POD-SELECTOR
techx-tf4   orders-mirrormaker2-mirrormaker2   strimzi.io/cluster=orders-mirrormaker2,strimzi.io/kind=KafkaMirrorMaker2,strimzi.io/name=orders-mirrormaker2-mirrormaker2
```

Conclusion:
- The cluster/CNI is configured to enforce NetworkPolicy.
- No SEC-21 policy is live at the time this document is written.
- Terraform now codifies `vpc-cni.configuration_values.enableNetworkPolicy = "true"` to prevent future drift. This is source code only; no Terraform apply was run by the assistant.

## Namespaces

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

`cloudflare-access` was requested for inventory if present. It is not present in the namespace list captured on 2026-07-21.

## Namespace Exclude List

Do not enforce default deny immediately on these namespaces:

| Namespace | Reason |
|---|---|
| `kube-system` | CNI, CoreDNS, AWS Load Balancer Controller, Karpenter, EKS Pod Identity and cluster networking dependencies. |
| `kube-node-lease` | Kubernetes lease namespace; no app containment value for this task. |
| `kube-public` | Kubernetes public/system namespace; no app containment value for this task. |
| `argocd` | GitOps control plane. Needs a separate map for repo-server, Redis, API server, Dex, webhooks. |
| `argo-rollouts` | Rollouts controller path. Needs controller/API mapping before enforcement. |
| `external-secrets` | Needs Kubernetes API, AWS Secrets Manager and STS access. Keep excluded until AWS egress strategy is agreed. |
| `kafka-operator` | Strimzi operator. Enforce only after operator-to-Kafka, webhook, and API server paths are mapped. |
| `kyverno` | Admission controller. Enforce only after webhook/API server paths are mapped. |
| `techx-observability` | Contains OTel Collector, Prometheus, Grafana, Jaeger, OpenSearch and alerting; first step only allows app egress into collector/admin paths where needed. |
| `techx-admission-test` | Test namespace; not part of production revenue path. |
| `techx-sec17-admission-test` | Test namespace; not part of production revenue path. |

First production scope:
- `techx-tf4` app workloads only.
- Default deny selector is limited to pods with `app.kubernetes.io/component` so Strimzi MirrorMaker2 is not selected by SEC-21 default deny.

## Service Inventory

Key services and ClusterIPs:

| Namespace | Service | ClusterIP | Ports |
|---|---|---:|---|
| `kube-system` | `kube-dns` | `172.20.0.10` | `53/UDP`, `53/TCP`, `9153/TCP` |
| `techx-tf4` | `frontend-proxy` | `172.20.74.72` | `8080/TCP` |
| `techx-tf4` | `frontend` | `172.20.39.20` | `8080/TCP` |
| `techx-tf4` | `ad` | `172.20.226.181` | `8080/TCP` |
| `techx-tf4` | `cart` | `172.20.148.103` | `8080/TCP` |
| `techx-tf4` | `checkout` | `172.20.60.78` | `8080/TCP` |
| `techx-tf4` | `currency` | `172.20.138.94` | `8080/TCP` |
| `techx-tf4` | `email` | `172.20.152.217` | `8080/TCP` |
| `techx-tf4` | `flagd` | `172.20.53.96` | `8013/TCP`, `8016/TCP` |
| `techx-tf4` | `image-provider` | `172.20.214.139` | `8081/TCP` |
| `techx-tf4` | `kafka` | `172.20.180.83` | `9092/TCP`, `9093/TCP` |
| `techx-tf4` | `load-generator` | `172.20.219.77` | `8089/TCP` |
| `techx-tf4` | `llm` | `172.20.163.157` | `8000/TCP` |
| `techx-tf4` | `payment` | `172.20.95.167` | `8080/TCP` |
| `techx-tf4` | `postgresql` | `172.20.87.154` | `5432/TCP` |
| `techx-tf4` | `product-catalog` | `172.20.14.135` | `8080/TCP` |
| `techx-tf4` | `product-reviews` | `172.20.99.48` | `3551/TCP` |
| `techx-tf4` | `quote` | `172.20.114.244` | `8080/TCP` |
| `techx-tf4` | `recommendation` | `172.20.173.151` | `8080/TCP` |
| `techx-tf4` | `shipping` | `172.20.221.24` | `8080/TCP` |
| `techx-tf4` | `valkey-cart` | `172.20.4.115` | `6379/TCP` |
| `techx-tf4` | `orders-mirrormaker2-mirrormaker2-api` | `172.20.246.182` | `8083/TCP` |
| `techx-observability` | `otel-collector` | `172.20.75.235` | `4317/TCP`, `4318/TCP`, others |
| `techx-observability` | `grafana` | `172.20.108.200` | `80/TCP` |
| `techx-observability` | `jaeger` | `172.20.88.27` | `16686/TCP`, others |
| `techx-observability` | `prometheus` | `172.20.132.28` | `9090/TCP` |
| `techx-observability` | `opensearch` | `172.20.152.38` | `9200/TCP`, `9300/TCP`, `9600/TCP` |

Migration bridge LoadBalancer services are operational paths and are not included in broad app allowlists:

- `techx-tf4/postgresql-migration-bridge:5432`
- `techx-tf4/valkey-migration-bridge:6379`
- `techx-observability/postgresql-migration-bridge:5432`

## Current Pod Selectors

Application pods use:

```text
app.kubernetes.io/component=<component>
opentelemetry.io/name=<component>
```

MirrorMaker2 uses Strimzi labels and does not have `app.kubernetes.io/component`:

```text
strimzi.io/cluster=orders-mirrormaker2
strimzi.io/kind=KafkaMirrorMaker2
strimzi.io/name=orders-mirrormaker2-mirrormaker2
```

Important lesson from rollback:
- Any Kafka ingress policy must include `orders-mirrormaker2-mirrormaker2 -> kafka:9092`.
- Kafka also needs self traffic on `9093/TCP` for KRaft controller path.

## Traffic Map

Required ingress:

| Source | Destination | Port | Reason |
|---|---|---:|---|
| ALB/VPC target traffic | `frontend-proxy` | 8080 | Public storefront ingress. Source pod selector is not available for ALB target traffic. |
| `load-generator` | `frontend-proxy` | 8080 | Synthetic/smoke traffic. |

Required app-to-app traffic:

| Source | Destination | Port | Reason |
|---|---|---:|---|
| `frontend-proxy` | `frontend` | 8080 | Storefront proxy to app. |
| `frontend-proxy` | `image-provider` | 8081 | Image proxy route. |
| `frontend-proxy` | `flagd` | 8013, 8016 | Feature flag and OFREP route. |
| `frontend-proxy` | `grafana.techx-observability` | 80 | Existing ops route only through proxy. |
| `frontend-proxy` | `jaeger.techx-observability` | 16686 | Existing tracing UI route only through proxy. |
| `frontend` | `ad` | 8080 | Ads path. |
| `frontend` | `cart` | 8080 | Cart API path. |
| `frontend` | `checkout` | 8080 | Checkout API path. |
| `frontend` | `currency` | 8080 | Currency conversion path. |
| `frontend` | `product-catalog` | 8080 | Browse/detail path. |
| `frontend` | `product-reviews` | 3551 | Reviews/AI assistant path. |
| `frontend` | `recommendation` | 8080 | Recommendation path. |
| `frontend` | `shipping` | 8080 | Shipping quote path. |
| `checkout` | `cart` | 8080 | Read and empty cart. |
| `checkout` | `currency` | 8080 | Convert order totals. |
| `checkout` | `email` | 8080 | Send order confirmation. |
| `checkout` | `payment` | 8080 | Charge request. |
| `checkout` | `product-catalog` | 8080 | Product lookup. |
| `checkout` | `shipping` | 8080 | Shipping quote/order. |
| `checkout` | `kafka` | 9092 | Publish order events. |
| `accounting` | `kafka` | 9092 | Consume order events. |
| `fraud-detection` | `kafka` | 9092 | Consume order events. |
| `orders-mirrormaker2-mirrormaker2` | `kafka` | 9092 | Mirror self-hosted Kafka topics to MSK; required to avoid CDO08-SEC-21 outage repeat. |
| `kafka` | `kafka` | 9093 | KRaft controller self path. |
| `cart` | `valkey-cart` or private ElastiCache subnets | 6379 | Cart store. |
| `accounting` | `postgresql` or private RDS subnets | 5432 | Accounting database. |
| `product-catalog` | `postgresql` or private RDS subnets | 5432 | Catalog database. |
| `product-reviews` | `postgresql` or private RDS subnets | 5432 | Reviews database. |
| `product-reviews` | `product-catalog` | 8080 | Product lookup. |
| `recommendation` | `product-catalog` | 8080 | Product lookup. |
| `shipping` | `quote` | 8080 | Quote backend. |

Shared egress:

| Source | Destination | Port | Reason |
|---|---|---:|---|
| selected app pods | `kube-system/kube-dns` and ClusterIP `172.20.0.10/32` | 53 UDP/TCP | DNS. |
| instrumented app pods | `otel-collector.techx-observability` and ClusterIP `172.20.75.235/32` | 4317, 4318 | OTLP traces/metrics/logs. |
| feature-flag clients | `flagd` and ClusterIP `172.20.53.96/32` | 8013, 8016 where needed | Feature flag evaluation. |

External/private exceptions:

| Source | Destination | Port | Reason |
|---|---|---:|---|
| `cart` | `10.0.10.0/24`, `10.0.11.0/24` | 6379 | Approved private ElastiCache Valkey endpoint. Not internet egress. |
| `accounting`, `product-catalog`, `product-reviews` | `10.0.10.0/24`, `10.0.11.0/24` | 5432 | Approved private RDS PostgreSQL endpoint. Not internet egress. |

Deferred:
- `product-reviews -> Bedrock`: standard Kubernetes NetworkPolicy cannot safely represent AWS service FQDN allowlists. Keep product-reviews AI egress out of enforced internet deny until a VPC endpoint/CIDR or CNI-specific FQDN policy is approved.

## Rollout Gate

Before PM applies the GitOps manifests:

1. Confirm GitOps branch diff contains only AppProject whitelist, NetworkPolicy manifests, and the PM runbook.
2. Confirm MirrorMaker2 traffic is explicitly included in Kafka allowlist.
3. Run PM dry-run commands from the GitOps runbook.
4. Apply through GitOps or PM-controlled `kubectl apply` only.
5. Run checkout smoke and attacker containment evidence from the evidence doc.
6. If MirrorMaker2, checkout, or Kafka logs show timeout, PM must rollback using the documented delete-by-label command.
