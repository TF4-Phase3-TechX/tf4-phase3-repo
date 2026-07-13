# TF4AIO-36 — Verify Prometheus/OpenSearch Programmatic Query Access

**Jira:** TF4AIO-36  
**Sprint:** Week 2  
**Assignee:** Cái Xuân Hoà  
**Date:** 2026-07-13  
**Status:** ⚠️ Partially Blocked — RBAC gap found, documented

---

## 1. Mục tiêu task

Verify rằng AIOps agent có thể query Prometheus và OpenSearch **programmatically** (không qua UI), phục vụ AIOps engine tương lai.

**Acceptance criteria:**
- PromQL/OpenSearch query returns real data
- Code snippet hoặc screenshot được capture
- RBAC/network gaps được documented

---

## 2. Những gì đã thực hiện

### 2.1 Xác nhận Infrastructure

Đã chạy `kubectl get svc -n techx-observability` với role `TF4-AIReadOnlyOrLimitedInvoke`, kết quả:

| Service | Namespace | ClusterIP | Port | Status |
|---------|-----------|-----------|------|--------|
| `prometheus` | `techx-observability` | `172.20.132.28` | `9090/TCP` | Running 4d+ |
| `opensearch` | `techx-observability` | `172.20.152.38` | `9200/TCP, 9300/TCP, 9600/TCP` | Running 4d+ |
| `opensearch-headless` | `techx-observability` | `None` (Headless) | `9200/TCP` | Running 4d+ |
| `grafana` | `techx-observability` | `172.20.108.200` | `80/TCP` | Running 4d+ |
| `jaeger` | `techx-observability` | `172.20.88.27` | multi-port | Running 4d+ |
| `otel-collector` | `techx-observability` | `172.20.75.235` | multi-port | Running 4d+ |

**Pod status xác nhận:**
```
prometheus-7d98765f44-ln6t2   1/1     Running   0   4d1h
opensearch-0                  1/1     Running   0   4d1h
```

> ✅ Cả Prometheus và OpenSearch đều đang chạy ổn định trong namespace `techx-observability`.

### 2.2 Kiến trúc network

- ALB (`techx-alb-ingress`) trong namespace `techx-tf4` chỉ route đến `frontend-proxy:8080`
- Prometheus và OpenSearch **không được expose qua ALB** — đây là **thiết kế đúng** (internal-only)
- Cả hai services đều là `ClusterIP` → chỉ reachable từ trong cluster hoặc qua port-forward

### 2.3 Phương pháp verify đã thử

#### Attempt 1: `kubectl port-forward`

```
kubectl port-forward svc/prometheus 9090:9090 -n techx-observability
```

**Kết quả:**
```
error: error upgrading connection: pods "prometheus-7d98765f44-ln6t2" is forbidden:
User "arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_4536cac35e2c79b6/xuanhoa"
cannot create resource "pods/portforward" in API group "" in the namespace "techx-observability"
```

**→ ❌ BLOCKED**

#### Attempt 2: `kubectl proxy` + API server proxy

```
kubectl proxy --port=8001
curl "http://localhost:8001/api/v1/namespaces/techx-observability/services/prometheus:9090/proxy/api/v1/query?query=up"
```

**Kết quả:**
```json
{
  "kind": "Status",
  "status": "Failure",
  "message": "services \"prometheus:9090\" is forbidden: User \"...TF4-AIReadOnlyOrLimitedInvoke...\"
              cannot get resource \"services/proxy\" in API group \"\" in the namespace \"techx-observability\"",
  "reason": "Forbidden",
  "code": 403
}
```

**→ ❌ BLOCKED**

---

## 3. RBAC Gap Analysis

### Root Cause

Role `TF4-AIReadOnlyOrLimitedInvoke` được map với `AmazonEKSViewPolicy` trong Terraform (`eks-access-entries.tf`):

```hcl
# infra/terraform/eks-access-entries.tf
sso_ai_readonly_limited_invoke = "arn:aws:iam::511825856493:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_4536cac35e2c79b6"
# policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy"
```

`AmazonEKSViewPolicy` map sang Kubernetes `view` ClusterRole — **không bao gồm** các verbs sau:

| Kubernetes Resource | Verb cần | Có trong view role? |
|--------------------|---------|---------------------|
| `pods/portforward` | `create` | ❌ Không |
| `services/proxy` | `get` | ❌ Không |
| `pods/exec` | `create` | ❌ Không |
| `pods/log` | `get` | ❌ Không |

### Gap cụ thể

```
Gap 1 — pods/portforward DENIED
  Namespace: techx-observability
  Required verb: create
  Current role: TF4-AIReadOnlyOrLimitedInvoke (AmazonEKSViewPolicy)
  Impact: Không thể port-forward Prometheus hoặc OpenSearch từ laptop

Gap 2 — services/proxy DENIED  
  Namespace: techx-observability
  Required verb: get
  Current role: TF4-AIReadOnlyOrLimitedInvoke (AmazonEKSViewPolicy)
  Impact: Không thể dùng kubectl proxy để access service endpoints
```

---

## 4. Blockers & Unblock Plan

### Những gì bị block

| Blocker | Mô tả | Owner để fix |
|---------|-------|-------------|
| `pods/portforward` denied | Không verify query từ laptop được | CDO (DevOps) |
| `services/proxy` denied | Kubectl proxy cũng không hoạt động | CDO (DevOps) |
| `eks:DescribeCluster` scoped | Role không thể `aws eks update-kubeconfig` lại | CDO (DevOps) |

### Unblock Option A — Grant portforward (Short-term)

CDO cần apply RoleBinding sau vào namespace `techx-observability`:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: ai-observability-reader
  namespace: techx-observability
rules:
  - apiGroups: [""]
    resources: ["pods/portforward"]
    verbs: ["create"]
  - apiGroups: [""]
    resources: ["services/proxy"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: ai-observability-reader-binding
  namespace: techx-observability
subjects:
  - kind: Group
    name: "arn:aws:iam::511825856493:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_4536cac35e2c79b6"
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: ai-observability-reader
  apiGroup: rbac.authorization.k8s.io
```

### Unblock Option B — In-cluster AI Engine (Long-term, Recommended)

AIOps engine deploy **trong cluster** → gọi trực tiếp internal DNS, không cần port-forward:

```python
# Trong AI engine pod chạy trong cluster
PROMETHEUS_URL = "http://prometheus.techx-observability.svc.cluster.local:9090"
OPENSEARCH_URL = "http://opensearch.techx-observability.svc.cluster.local:9200"
```

> **Đây là thiết kế đúng cho production AIOps.** Không nên expose Prometheus/OpenSearch ra ngoài cluster.

---

## 5. Kết luận

| Acceptance Criteria | Trạng thái |
|--------------------|-----------|
| Services exist & running | ✅ Confirmed — both Prometheus & OpenSearch running 4d+ |
| RBAC/network gaps documented | ✅ Documented — 2 gaps found (portforward + proxy) |
| PromQL query returns real data | ❌ Blocked — cần CDO grant portforward RBAC |
| OpenSearch query returns real data | ❌ Blocked — cùng lý do |
| Code snippet captured | ⚠️ Scripts được viết nhưng chưa chạy được |

**Đề xuất next step:**
1. CDO apply Option A RBAC fix → AIO re-run verification
2. Hoặc AIO team thực hiện query từ một admin pod có quyền → capture screenshot
3. Sau đó thiết kế AI engine theo Option B (in-cluster) cho W3

---

*Báo cáo bởi: Cái Xuân Hoà — TF4AIO team*  
*Liên quan: TF4AIO-5 (Epic AIOps), TF4AIO-13 (W1 Observability Access)*
