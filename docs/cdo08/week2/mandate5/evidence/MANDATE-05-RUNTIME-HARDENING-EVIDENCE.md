# Mandate 5 Runtime Hardening Evidence

**Thời điểm kiểm tra:** `2026-07-19T02:45Z`
**AWS account:** `511825856493`
**Cluster:** `arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster`

## Kết Luận

Mandate 5 hiện **PASS** cho phần runtime hardening admission enforcement.

Hệ thống đang enforce các policy sau trên toàn cluster, ngoại trừ namespace hệ thống `kube-system`, `kube-node-lease`, `kube-public`:

- Không cho tạo workload dùng image `latest` hoặc image không pin tag/digest.
- Không cho tạo container thiếu CPU/memory requests và limits.
- Không cho tạo container chạy root.
- Không cho tạo container không drop Linux capabilities.

Storefront vẫn hoạt động qua public ALB HTTP và không có pod runtime đang ở trạng thái lỗi.

## 1. Policy Scope

### Command

```bash
kubectl get validatingadmissionpolicybinding -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.validationActions}{"\t"}{.spec.matchResources.namespaceSelector.matchExpressions}{"\n"}{end}'
```

### Evidence

```text
disallow-mutable-image-tag-binding      ["Deny"]  [{"key":"kubernetes.io/metadata.name","operator":"NotIn","values":["kube-system","kube-node-lease","kube-public"]}]
require-drop-all-capabilities-binding   ["Deny"]  [{"key":"kubernetes.io/metadata.name","operator":"NotIn","values":["kube-system","kube-node-lease","kube-public"]}]
require-resource-limits-binding         ["Deny"]  [{"key":"kubernetes.io/metadata.name","operator":"NotIn","values":["kube-system","kube-node-lease","kube-public"]}]
require-run-as-nonroot-binding          ["Deny"]  [{"key":"kubernetes.io/metadata.name","operator":"NotIn","values":["kube-system","kube-node-lease","kube-public"]}]
```

### Kết Luận

Policy đang ở chế độ `Deny` và áp dụng toàn cluster, chỉ loại trừ 3 namespace hệ thống.

## 2. Admission Rejection Tests

Các lệnh bên dưới dùng `--dry-run=server`, nghĩa là request đi qua API server/admission thật nhưng không tạo pod thật.

### 2.1. Reject Image `latest`

```bash
kubectl run mandate5-bad-image \
  --image=nginx:latest \
  -n default \
  --restart=Never \
  --dry-run=server \
  --overrides='{"spec":{"securityContext":{"runAsNonRoot":true},"containers":[{"name":"mandate5-bad-image","image":"nginx:latest","resources":{"requests":{"cpu":"10m","memory":"16Mi"},"limits":{"cpu":"20m","memory":"32Mi"}},"securityContext":{"runAsNonRoot":true,"capabilities":{"drop":["ALL"]}}}]}}'
```

```text
The pods "mandate5-bad-image" is invalid: : ValidatingAdmissionPolicy 'disallow-mutable-image-tag' with binding 'disallow-mutable-image-tag-binding' denied request: Image must pin a fixed tag or digest (repo:tag, repo@sha256:<digest>, or repo:tag@sha256:<digest>); ':latest', untagged images, and untagged images behind a registry:port are not allowed.
```

### 2.2. Reject Thiếu Requests/Limits

```bash
kubectl run mandate5-bad-resources \
  --image=busybox:1.36.1 \
  -n default \
  --restart=Never \
  --dry-run=server \
  --overrides='{"spec":{"securityContext":{"runAsNonRoot":true},"containers":[{"name":"mandate5-bad-resources","image":"busybox:1.36.1","command":["sh","-c","sleep 10"],"securityContext":{"runAsNonRoot":true,"capabilities":{"drop":["ALL"]}}}]}}'
```

```text
The pods "mandate5-bad-resources" is invalid: : ValidatingAdmissionPolicy 'require-resource-limits' with binding 'require-resource-limits-binding' denied request: Container/initContainer must define both requests and limits for cpu and memory.
```

### 2.3. Reject Chạy Root

```bash
kubectl run mandate5-bad-root \
  --image=busybox:1.36.1 \
  -n default \
  --restart=Never \
  --dry-run=server \
  --overrides='{"spec":{"containers":[{"name":"mandate5-bad-root","image":"busybox:1.36.1","command":["sh","-c","sleep 10"],"resources":{"requests":{"cpu":"10m","memory":"16Mi"},"limits":{"cpu":"20m","memory":"32Mi"}},"securityContext":{"runAsNonRoot":false,"capabilities":{"drop":["ALL"]}}}]}}'
```

```text
The pods "mandate5-bad-root" is invalid: : ValidatingAdmissionPolicy 'require-run-as-nonroot' with binding 'require-run-as-nonroot-binding' denied request: Container/initContainer must run as non-root: set runAsNonRoot=true at pod or container level.
```

### 2.4. Reject Không Drop Capabilities

```bash
kubectl run mandate5-bad-capabilities \
  --image=busybox:1.36.1 \
  -n default \
  --restart=Never \
  --dry-run=server \
  --overrides='{"spec":{"securityContext":{"runAsNonRoot":true},"containers":[{"name":"mandate5-bad-capabilities","image":"busybox:1.36.1","command":["sh","-c","sleep 10"],"resources":{"requests":{"cpu":"10m","memory":"16Mi"},"limits":{"cpu":"20m","memory":"32Mi"}},"securityContext":{"runAsNonRoot":true}}]}}'
```

```text
The pods "mandate5-bad-capabilities" is invalid: : ValidatingAdmissionPolicy 'require-drop-all-capabilities' with binding 'require-drop-all-capabilities-binding' denied request: Container/initContainer must drop all capabilities: set securityContext.capabilities.drop: ["ALL"] (add back only what is required).
```

### Kết Luận

Admission control đã reject đúng 4 nhóm vi phạm bắt buộc của Mandate 5.

## 3. Runtime Health

### Command

```bash
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
```

### Evidence

```text
No resources found
```

### Kết Luận

Không có pod đang ở trạng thái `Pending`, `Failed`, `Unknown` hoặc trạng thái lỗi khác.

## 4. Storefront Không Bị Ảnh Hưởng

### Command

```bash
kubectl -n techx-tf4 get ingress techx-alb-ingress -o wide
curl -I --max-time 15 http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/
```

### Evidence

```text
$ kubectl -n techx-tf4 get ingress techx-alb-ingress -o wide
NAME                CLASS    HOSTS   ADDRESS                                                                  PORTS   AGE
techx-alb-ingress   <none>   *       k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com   80      11d

$ curl -I --max-time 15 http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/
HTTP/1.1 200 OK
Date: Sun, 19 Jul 2026 02:45:10 GMT
Content-Type: text/html; charset=utf-8
Content-Length: 11347
Connection: keep-alive
x-envoy-upstream-service-time: 18
server: envoy
```

### Kết Luận

Storefront vẫn truy cập được qua public ALB HTTP. ALB hiện expose port `80`; không dùng URL `https://...` nếu chưa có HTTPS listener/certificate.

## Acceptance Criteria

| Requirement | Status |
|---|---|
| Policy áp dụng toàn cluster, trừ namespace hệ thống | PASS |
| Workload mới dùng image `latest`/untagged bị reject | PASS |
| Workload mới thiếu CPU/memory requests hoặc limits bị reject | PASS |
| Workload mới chạy root bị reject | PASS |
| Workload mới không drop capabilities bị reject | PASS |
| Không có pod runtime đang lỗi | PASS |
| Storefront public path vẫn hoạt động | PASS |
