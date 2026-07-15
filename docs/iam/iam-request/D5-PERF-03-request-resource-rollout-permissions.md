# [D5-PERF-03] Yêu cầu quyền resource remediation rollout và runtime verification

**Trạng thái**: TO DO  
**Người yêu cầu (Reporter)**: Owner D5-PERF-03 — CDO04 Performance & Cost  
**Người thực hiện (Assignee)**: CDO08 Security/SSO/IAM và Platform/EKS owner  
**Độ ưu tiên (Priority)**: P0 — Blocker cho production rollout  
**Epic**: EPIC-07 / Directive #5 — Resource Governance & Safe Admission Enforcement  
**Phạm vi cluster**: `techx-tf4-cluster`, account `511825856493`, region `us-east-1`  
**Namespace**: `techx-tf4`, `techx-observability` và namespace admission-test được phê duyệt

---

## 1. Bối cảnh

D5-PERF-03 yêu cầu triển khai CPU/memory requests và limits theo từng wave,
không rollout toàn cluster cùng lúc:

1. Low-risk stateless services.
2. Revenue-critical stateless services.
3. Stateful/messaging workloads.
4. Observability workloads.
5. Remaining exceptions.

Owner phải tự thực hiện Helm rollout, theo dõi Pending/CrashLoop/OOM, đánh giá
CPU throttling và Browse/Cart/Checkout SLO, kiểm chứng rollback và lưu evidence
tại:

```text
docs/evidence/directive-05/official-<RUN_ID>/resource-rollout/
```

Quyền hiện tại là `TF4-CostPerfReadOnlyAlerting`. Role đọc được một phần trạng
thái workload nhưng không đủ quyền để hoàn thành task.

## 2. Evidence thiếu quyền và runtime blocker hiện tại

Kết quả Kubernetes authorization đã xác minh trên cluster:

```text
kubectl auth can-i get deployments -n techx-tf4
yes

kubectl auth can-i patch deployments -n techx-tf4
no

kubectl auth can-i create pods -n techx-tf4
no
```

Metrics và node inventory cũng bị từ chối:

```text
pods.metrics.k8s.io: forbidden
nodes.metrics.k8s.io: forbidden
nodes: forbidden
```

Tại thời điểm preflight ngày 14/07/2026, scheduler ghi nhận nhiều pod Pending:

```text
0/2 nodes are available: 2 Insufficient cpu
```

Frontend và checkout HPA đồng thời báo `cpu: <unknown>/70%`. Vì vậy owner cần
quyền đọc node/metrics để đo capacity, và cần quyền controlled-change để
pre-scale/rollout/rollback sau khi cluster trở lại trạng thái ổn định.

## 3. Quyền Kubernetes yêu cầu

### 3.1 Cluster-scoped read-only

| API group | Resource | Verbs | Mục đích |
|---|---|---|---|
| core | `nodes` | `get`, `list`, `watch` | Kiểm tra allocatable, node readiness và placement capacity |
| `metrics.k8s.io` | `pods` | `get`, `list` | Thu CPU/memory runtime evidence cho D5-02 và before/after |
| `metrics.k8s.io` | `nodes` | `get`, `list` | Kiểm tra node utilization và headroom |

Không yêu cầu quyền sửa hoặc xóa Node.

### 3.2 Read/observe trong `techx-tf4` và `techx-observability`

| API group | Resource | Verbs | Mục đích |
|---|---|---|---|
| core | `pods` | `get`, `list`, `watch` | Pending, phase, placement, restart và OOM state |
| core | `pods/log` | `get` | Điều tra CrashLoop/OOM hoặc regression |
| core | `pods/portforward` | `create` | Mở tunnel cục bộ có kiểm soát tới Prometheus/Grafana để thu before/after evidence |
| core | `services/proxy` | `get` | Đường query read-only thay thế tới Prometheus nếu port-forward không được duyệt |
| core | `events` | `get`, `list`, `watch` | Scheduler, admission, probe và rollout events |
| core | `services`, `endpoints` | `get`, `list`, `watch` | Xác minh service còn endpoint sau rollout |
| apps | `deployments`, `replicasets`, `statefulsets` | `get`, `list`, `watch` | Rollout status và revision inventory |
| autoscaling | `horizontalpodautoscalers` | `get`, `list`, `watch` | Xác minh HPA có CPU request/metrics hợp lệ |
| policy | `poddisruptionbudgets` | `get`, `list`, `watch` | Phát hiện rollout/maintenance availability constraint |
| core | `resourcequotas`, `limitranges` | `get`, `list`, `watch` | Xác minh namespace admission/capacity constraint |
| core | `persistentvolumeclaims` | `get`, `list`, `watch` | Quan sát stateful rollout, không sửa/xóa dữ liệu |

### 3.3 Temporary controlled-change trong hai namespace

Chỉ cấp trong approved change window và thu hồi sau khi D5-PERF-03 hoàn tất.

| API group | Resource | Verbs | Mục đích |
|---|---|---|---|
| apps | `deployments`, `statefulsets` | `get`, `list`, `watch`, `patch`, `update` | Apply resource requests/limits và rollback workload |
| apps | `replicasets` | `get`, `list`, `watch` | Theo dõi revision; không yêu cầu sửa ReplicaSet trực tiếp |
| autoscaling | `horizontalpodautoscalers` | `get`, `list`, `watch`, `patch`, `update` | Chỉ sửa khi measured matrix/HPA review yêu cầu |
| core | `secrets` | `get`, `list`, `create`, `patch`, `update`, `delete` | Helm release storage cho upgrade/rollback |

Nếu Security không chấp thuận quyền Secret cho owner, Platform có thể chạy các
lệnh Helm đã review thay owner. Khi đó owner vẫn cần toàn bộ quyền read/observe
ở mục 3.1–3.2 và Platform phải trả lại stdout, revision và rollback evidence.

Không yêu cầu quyền sửa PVC/PV, RBAC, ServiceAccount, NetworkPolicy hoặc
security policy trong task này.

### 3.4 Admission-test namespace

Security cung cấp một namespace riêng, ví dụ `techx-admission-test`, không dùng
production namespace. Owner cần:

| API group | Resource | Verbs | Mục đích |
|---|---|---|---|
| core | `pods` | `get`, `list`, `create`, `delete` | Test manifest thiếu/đủ resources |
| apps | `deployments` | `get`, `list`, `create`, `delete` | Test admission với workload controller |
| core | `events` | `get`, `list` | Thu rejection reason làm evidence |

Không yêu cầu quyền sửa admission policy hoặc cài admission engine.

## 4. AWS IAM yêu cầu nếu owner tự pre-scale node group

| Action | Mục đích |
|---|---|
| `eks:DescribeCluster` | Xác minh đúng cluster và tạo kubeconfig |
| `eks:ListNodegroups` | Tìm managed node group của cluster |
| `eks:DescribeNodegroup` | Đọc min/desired/max, instance type và health |
| `eks:UpdateNodegroupConfig` | Tăng capacity trước rollout và trả về baseline sau validation |

`eks:UpdateNodegroupConfig` phải giới hạn vào đúng managed node-group ARN của
`techx-tf4-cluster`, không dùng wildcard toàn account. Ví dụ resource pattern:

```text
arn:aws:eks:us-east-1:511825856493:nodegroup/techx-tf4-cluster/<NODEGROUP_NAME>/<NODEGROUP_ID>
```

Nếu Platform sở hữu pre-scale/scale-down, không cần cấp
`eks:UpdateNodegroupConfig` cho owner; Platform thực hiện theo change ticket và
cung cấp before/after scaling evidence.

## 5. Observability access liên quan trực tiếp

| Hệ thống | Quyền |
|---|---|
| Grafana | Viewer, xem/export dashboard before/after |
| Prometheus | Query read-only qua UI/API |

Các metric tối thiểu cần query:

- CPU usage và CPU throttling theo container.
- Memory working set, memory limit utilization.
- Restart/OOM increase.
- Pending/Ready replica count.
- Browse/Cart/Checkout request rate, error rate và p95 latency.

Không yêu cầu Editor/Admin Grafana và không yêu cầu sửa Prometheus rules.

## 6. Ranh giới và kiểm soát an toàn

- Quyền write chỉ có hiệu lực trong controlled change window.
- Chỉ rollout một wave tại một thời điểm.
- Không sửa securityContext, image policy, capabilities, seccomp hoặc admission
  policy thuộc ownership của Security.
- Không sửa/xóa PVC, PV hoặc dữ liệu stateful.
- Không cấp `cluster-admin`.
- Không cấp quyền IAM/SSO administration.
- Mỗi Helm apply phải ghi lại previous revision và rollback command.
- Dừng và rollback nếu xuất hiện Pending, CrashLoop hoặc OOM mới.
- Không bắt đầu rollout khi production namespace đã có Pending workload.

## 7. Lệnh verify sau khi cấp quyền

### 7.1 Xác minh identity và cluster

```bash
aws sts get-caller-identity --profile <APPROVED_PROFILE>
aws eks update-kubeconfig --name techx-tf4-cluster --region us-east-1 \
  --profile <APPROVED_PROFILE>
```

### 7.2 Xác minh cluster/node metrics read access

```bash
kubectl auth can-i list nodes
kubectl auth can-i list pods.metrics.k8s.io --all-namespaces
kubectl auth can-i list nodes.metrics.k8s.io
kubectl get nodes
kubectl top nodes
kubectl top pods -n techx-tf4 --containers
kubectl top pods -n techx-observability --containers
```

Expected: tất cả `can-i` trả về `yes`; các lệnh đọc trả dữ liệu và không
`Forbidden`.

### 7.3 Xác minh controlled-change access

```bash
kubectl auth can-i patch deployments.apps -n techx-tf4
kubectl auth can-i patch deployments.apps -n techx-observability
kubectl auth can-i patch statefulsets.apps -n techx-tf4
kubectl auth can-i create secrets -n techx-tf4
kubectl auth can-i delete secrets -n techx-observability
kubectl auth can-i create pods/portforward -n techx-observability
kubectl auth can-i get services/proxy -n techx-observability
```

Expected: `yes` trong change window.

Không patch workload chỉ để kiểm tra quyền. Sau khi RBAC check pass, dùng Helm
server-side dry-run của D5-PERF-03 trước khi apply.

### 7.4 Xác minh admission-test access

```bash
kubectl auth can-i create pods -n <ADMISSION_TEST_NAMESPACE>
kubectl auth can-i delete pods -n <ADMISSION_TEST_NAMESPACE>
kubectl auth can-i create deployments.apps -n <ADMISSION_TEST_NAMESPACE>
```

Expected: `yes` trong test namespace và không mở quyền tương đương ngoài scope
đã duyệt.

## 8. Acceptance Criteria của yêu cầu quyền

- [ ] Owner đọc được Nodes và Node allocatable/readiness.
- [ ] Owner đọc được Pod/Node Metrics API và chạy được `kubectl top`.
- [ ] Owner đọc được Pods, Events, Deployments, ReplicaSets, HPA và PDB ở hai namespace.
- [ ] Owner đọc được pod logs để điều tra regression.
- [ ] Owner dùng được một đường private read-only tới Prometheus/Grafana (`pods/portforward` hoặc `services/proxy`).
- [ ] Owner hoặc Platform operator được duyệt có thể Helm upgrade/rollback trong change window.
- [ ] Previous Helm revision và rollback command được lưu trong evidence.
- [ ] Owner tạo/xóa được test workload trong admission-test namespace.
- [ ] Owner không có quyền sửa admission policy, RBAC, Node, PVC/PV hoặc security controls.
- [ ] Nếu owner tự pre-scale, `eks:UpdateNodegroupConfig` chỉ scope vào đúng node group.
- [ ] Quyền temporary write được thu hồi sau khi task hoàn thành.

Sau khi cấp quyền, vui lòng tag owner D5-PERF-03 để chạy lại preflight. Chỉ bắt
đầu wave 1 khi namespace không còn Pending/CrashLoop/OOM mới và HPA metrics đã
hoạt động.
