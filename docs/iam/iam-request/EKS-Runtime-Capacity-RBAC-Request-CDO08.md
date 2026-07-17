# Yêu cầu bổ sung RBAC runtime capacity evidence cho CDO08 Role

## Vấn đề

CDO08 đang cần bổ sung runtime/capacity evidence cho backlog `CDO08-REL-01` trước khi triển khai tăng replicas cho các critical services.

CDO04 đã **conditional approve** hướng tăng từ `1` lên `2` replicas cho 7 stateless critical services, nhưng yêu cầu thêm bằng chứng runtime để xác nhận capacity/cost risk trước khi approve rollout chính thức.

Hiện CDO08 đã lấy được một phần evidence trong namespace `techx-tf4`, nhưng chưa lấy được node headroom và actual CPU/memory usage vì thiếu quyền hoặc thiếu Metrics API.

## Thông tin liên quan

| Mục                            | Giá trị                                                                                    |
| ------------------------------ | ------------------------------------------------------------------------------------------ |
| AWS Role (IAM Identity Center) | `AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155`                          |
| Cluster                        | `techx-tf4-cluster`                                                                        |
| Namespace                      | `techx-tf4`                                                                                |
| Region                         | `us-east-1`                                                                                |
| Account                        | `511825856493`                                                                             |
| Backlog liên quan              | `CDO08-REL-01`                                                                             |
| Scope service                  | `frontend-proxy`, `frontend`, `checkout`, `cart`, `payment`, `shipping`, `product-catalog` |

## Evidence đã lấy được

CDO08 đã chạy được các lệnh namespace-scope để xác nhận baseline hiện tại:

- Pods trong namespace `techx-tf4` đang `Running`.
- Không thấy `Pending` / `FailedScheduling` trong events gần nhất.
- 7 critical services hiện có memory limits nhưng chưa có CPU/memory requests.
- Rollout gần nhất chỉ có event type `Normal`.

Command đã chạy được:

```bash
kubectl -n techx-tf4 get pods -o wide
kubectl -n techx-tf4 get events --sort-by=.lastTimestamp
kubectl -n techx-tf4 get deploy frontend-proxy frontend checkout cart payment shipping product-catalog -o jsonpath='...'
```

## Evidence đang bị block

### 1. Không lấy được actual CPU/memory usage

Command:

```bash
kubectl top nodes
```

Error:

```text
error: Metrics API not available
```

Ý nghĩa:

- Cluster hiện chưa expose được Metrics API cho `kubectl top`.
- Có thể do metrics-server chưa được cài/chưa hoạt động, hoặc role hiện tại chưa được cấp quyền đọc metrics.
- Cần team deploy/admin kiểm tra `metrics-server` và quyền đọc `metrics.k8s.io`.

### 2. Không list được node capacity/allocatable

Command:

```bash
kubectl get nodes -o custom-columns=NAME:.metadata.name,CPU:.status.capacity.cpu,CPU_ALLOC:.status.allocatable.cpu,MEM:.status.capacity.memory,MEM_ALLOC:.status.allocatable.memory
```

Error:

```text
Error from server (Forbidden): nodes is forbidden: User "arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155/nam" cannot list resource "nodes" in API group "" at the cluster scope
```

Ý nghĩa:

- Role hiện tại chưa có quyền read-only với resource `nodes` ở cluster-scope.
- Vì vậy CDO08 chưa tự xác minh được node capacity/allocatable/headroom.

## Yêu cầu xử lý

Cần bổ sung quyền read-only để CDO08 lấy runtime capacity evidence cho replica rollout review.

### Quyền tối thiểu cần bổ sung

Cluster-scope:

- `get`, `list`, `watch` trên resource `nodes`
- `get`, `list`, `watch` trên resource `nodes.metrics.k8s.io` nếu Metrics API đã sẵn sàng

Namespace `techx-tf4`:

- `get`, `list`, `watch` trên resource `pods`
- `get`, `list`, `watch` trên resource `deployments`
- `get`, `list`, `watch` trên resource `replicasets`
- `get`, `list`, `watch` trên resource `events`
- `get`, `list`, `watch` trên resource `pods.metrics.k8s.io` nếu Metrics API đã sẵn sàng

Nếu Metrics API chưa sẵn sàng, cần deploy/fix `metrics-server` hoặc cung cấp output tương đương từ CloudWatch/Container Insights cho CDO08/CDO04 review.

## Cấu hình RBAC gợi ý

> Tên group cần khớp với group đã map cho CDO08 role trong EKS Access Entry/aws-auth hiện tại.

### ClusterRole cho node capacity và node metrics

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
    name: cdo08-runtime-capacity-readonly
rules:
    - apiGroups: [""]
      resources: ["nodes"]
      verbs: ["get", "list", "watch"]
    - apiGroups: ["metrics.k8s.io"]
      resources: ["nodes"]
      verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
    name: cdo08-runtime-capacity-readonly
subjects:
    - kind: Group
      name: tf4-cdo08-readonly
      apiGroup: rbac.authorization.k8s.io
roleRef:
    kind: ClusterRole
    name: cdo08-runtime-capacity-readonly
    apiGroup: rbac.authorization.k8s.io
```

### Role cho namespace runtime evidence

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
    name: cdo08-runtime-namespace-readonly
    namespace: techx-tf4
rules:
    - apiGroups: [""]
      resources: ["pods", "events"]
      verbs: ["get", "list", "watch"]
    - apiGroups: ["apps"]
      resources: ["deployments", "replicasets"]
      verbs: ["get", "list", "watch"]
    - apiGroups: ["metrics.k8s.io"]
      resources: ["pods"]
      verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
    name: cdo08-runtime-namespace-readonly
    namespace: techx-tf4
subjects:
    - kind: Group
      name: tf4-cdo08-readonly
      apiGroup: rbac.authorization.k8s.io
roleRef:
    kind: Role
    name: cdo08-runtime-namespace-readonly
    apiGroup: rbac.authorization.k8s.io
```

## Sau khi Admin hoàn tất

Bên mình sẽ chạy lại để kiểm tra:

```bash
kubectl top nodes
kubectl -n techx-tf4 top pods
kubectl get nodes -o custom-columns=NAME:.metadata.name,CPU:.status.capacity.cpu,CPU_ALLOC:.status.allocatable.cpu,MEM:.status.capacity.memory,MEM_ALLOC:.status.allocatable.memory
kubectl -n techx-tf4 get pods -o wide
kubectl -n techx-tf4 get events --sort-by=.lastTimestamp
```

Các lệnh này chỉ dùng để lấy runtime/capacity evidence cho `CDO08-REL-01`, không thay đổi replica hoặc production resource.

Nếu được approve test scale tạm thời, CDO08 sẽ tạo request riêng trước khi chạy các lệnh có thay đổi runtime như `kubectl scale`.

## Trạng thái hiện tại

```text
PARTIALLY BLOCKED: namespace-scope runtime evidence đã lấy được, nhưng node headroom và actual CPU/memory usage đang bị block vì Metrics API chưa khả dụng và CDO08 role chưa có quyền read-only với nodes ở cluster-scope.
```
