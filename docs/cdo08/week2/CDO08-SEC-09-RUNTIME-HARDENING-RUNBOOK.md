# CDO08-SEC-09 Runtime Hardening Evidence

**Task:** `[CDO08-SEC-09][P0][Runtime] Remove root and privilege gaps from running workloads`  
**Owner chính:** Nhân  
**Ngày thực hiện:** 2026-07-16  
**AWS account:** `511825856493`  
**Cluster:** `techx-tf4-cluster`  
**Namespaces:** `techx-tf4`, `techx-observability`

## 1. Tóm tắt kết quả

Đã cập nhật Dockerfile và Helm values để thêm container-level runtime hardening cho các workload có evidence non-root hoặc image đã được chuyển sang non-root trong PR này. Không bật `readOnlyRootFilesystem` đại trà.

Baseline đã thêm cho workload phù hợp:

```yaml
runAsNonRoot: true
allowPrivilegeEscalation: false
capabilities:
  drop: [ALL]
seccompProfile:
  type: RuntimeDefault
```

Các workload đã patch trong `techx-corp-chart/values.yaml`:

| Namespace dự kiến | Workload | UID/GID | Lý do patch |
| --- | --- | --- | --- |
| `techx-tf4` | `accounting` | `1654:1654` | Runtime `id` trả về user `app`, non-root |
| `techx-tf4` | `accounting` init `wait-for-kafka` | `65534:65534` | Busybox init chỉ chạy `nc` wait TCP, không cần root |
| `techx-tf4` | `ad` | `10001:10001` | Dockerfile được bổ sung user `app`; chart áp baseline |
| `techx-tf4` | `cart` | `10001:10001` | Dockerfile được bổ sung user `app`; chart áp baseline |
| `techx-tf4` | `checkout` | `65532:65532` | Dockerfile dùng `gcr.io/distroless/static-debian12:nonroot` |
| `techx-tf4` | `checkout` init `wait-for-kafka` | `65534:65534` | Busybox init chỉ chạy `nc` wait TCP, không cần root |
| `techx-tf4` | `currency` | `10001:10001` | Dockerfile được bổ sung user `app`; chart áp baseline |
| `techx-tf4` | `email` | `10001:10001` | Dockerfile được bổ sung user `app`; chart áp baseline |
| `techx-tf4` | `fraud-detection` | `65532:65532` | Dockerfile dùng `gcr.io/distroless/java17-debian12:nonroot` |
| `techx-tf4` | `fraud-detection` init `wait-for-kafka` | `65534:65534` | Busybox init chỉ chạy `nc` wait TCP, không cần root |
| `techx-tf4` | `cart` init `wait-for-valkey-cart` | `65534:65534` | Busybox init chỉ chạy `nc` wait TCP, không cần root |
| `techx-tf4` | `frontend` | `1001:1001` | Đã có UID non-root, bổ sung missing controls |
| `techx-tf4` | `frontend-proxy` | `101:101` | Dockerfile `USER envoy`, đã có UID non-root, bổ sung missing controls |
| `techx-tf4` | `image-provider` | `101:101` | Dockerfile `USER 101`; runtime `id` là nginx |
| `techx-tf4` | `llm` | `10001:10001` | Dockerfile được bổ sung user `app`; chart áp baseline |
| `techx-tf4` | `load-generator` | `10001:10001` | Dockerfile được bổ sung user `app`, `HOME=/tmp`, ownership cho app/browser paths; chart áp baseline |
| `techx-tf4` | `payment` | `1000:1000` | Đã chạy non-root theo chart, bổ sung missing controls |
| `techx-tf4` | `product-catalog` | `65532:65532` | Dockerfile dùng distroless nonroot |
| `techx-tf4` | `product-reviews` | `10001` | Đã harden gần đủ, bổ sung `seccompProfile` |
| `techx-tf4` | `quote` | `33:33` | Đã chạy `www-data`, bổ sung missing controls |
| `techx-tf4` | `recommendation` | `10001:10001` | Dockerfile được bổ sung user `app`; chart áp baseline |
| `techx-tf4` | `shipping` | `65532:65532` | Dockerfile dùng `gcr.io/distroless/cc-debian13:nonroot` |
| `techx-tf4` | `kafka` | `1000:1000` | Đã chạy appuser với `fsGroup`, bổ sung missing controls |
| `techx-tf4` | `valkey-cart` | `999:1000` | Đã chạy non-root với PVC/fsGroup, bổ sung missing controls |
| `techx-observability` | `jaeger` | `10001:10001` | Jaeger chart default pod UID là `10001`, container `securityContext` đang `{}` |
| `techx-observability` | `prometheus-server` | `65534:65534` | Prometheus chart default pod UID là `65534`, container securityContext đang trống |
| `techx-observability` | `prometheus-server-configmap-reload` | `65534:65534` | Container config reload đang trống securityContext |

Không rollout được bằng SSO hiện tại vì role `TF4-SecReliabilityReadOnlyAudit` không có quyền patch/update deployment. Cần Nam hoặc role `TF4-DeployOperator` rollout.

## 2. Thay đổi code/chart

File thay đổi:

- `techx-corp-chart/values.yaml`
- `techx-corp-platform/src/ad/Dockerfile`
- `techx-corp-platform/src/cart/src/Dockerfile`
- `techx-corp-platform/src/currency/Dockerfile`
- `techx-corp-platform/src/email/Dockerfile`
- `techx-corp-platform/src/llm/Dockerfile`
- `techx-corp-platform/src/load-generator/Dockerfile`
- `techx-corp-platform/src/recommendation/Dockerfile`

Thay đổi chính:

- Thêm `securityContext` cho workload app non-root ready.
- Thêm user/group `app` UID/GID `10001:10001` trong Dockerfile cho các app trước đó đang chạy root: `ad`, `cart`, `currency`, `email`, `llm`, `load-generator`, `recommendation`.
- Thêm `securityContext` UID/GID `10001:10001` cho các workload trên trong chart.
- Thêm `HOME=/tmp` và `PYTHONDONTWRITEBYTECODE=1` cho Python workloads `llm`, `load-generator`, `recommendation` để tránh ghi cache vào path root-owned khi chạy non-root.
- Thêm `securityContext` cho init containers `wait-for-kafka` và `wait-for-valkey-cart`.
- Bổ sung `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, `seccompProfile: RuntimeDefault` cho workload đã có `runAsUser/runAsNonRoot`.
- Thêm `jaeger.jaeger.securityContext`.
- Thêm `prometheus.server.containerSecurityContext`.
- Thêm `prometheus.configmapReload.prometheus.containerSecurityContext`.
- Giữ `default.securityContext: {}` để tránh áp global vào các workload còn đang root hoặc chưa audit UID/GID.
- Không thêm admission policy.
- Không đổi business logic app.

Lý do không đặt global `default.securityContext`:

Một số workload stateful/third-party vẫn cần audit riêng (`postgresql`, `flagd`, một số observability stateful/init). Nếu set global `runAsNonRoot` sẽ làm rollout chết trước khi image được rebuild hoặc UID/GID/PVC ownership được xác nhận.

Lý do bổ sung Dockerfile cho các app root:

Các image `ad`, `cart`, `currency`, `email`, `llm`, `load-generator`, `recommendation` là app image do repo kiểm soát và không cần bind privileged port. Vì vậy PR này tạo user non-root `app` với UID/GID `10001:10001`, `chown` các thư mục runtime cần đọc/ghi, rồi cấu hình chart chạy đúng UID đó với baseline hardening. Riêng các Python workload được set thêm `HOME=/tmp` và `PYTHONDONTWRITEBYTECODE=1`; `load-generator` có thêm ownership cho `/opt/pw-browsers` để tránh lỗi cache/browser path khi chạy non-root.

Lý do harden các init `wait-for-*` bằng `65534:65534`:

Các init này dùng `busybox` chỉ để chạy `nc` kiểm tra TCP readiness của dependency (`kafka` hoặc `valkey-cart`) rồi thoát. Chúng không ghi vào volume, không bind port thấp và không cần Linux capability đặc biệt, nên có thể chạy non-root với user `nobody` (`65534`) cùng baseline `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, `seccompProfile: RuntimeDefault`.

## 3. Lệnh đã chạy và output

### 3.1. Xác minh AWS identity

Command:

```bash
aws sts get-caller-identity --profile tf4-cdo08-readonly
```

Output:

```json
{
    "UserId": "AROAXOKZSY7WV4ZNBQ7VZ:nhan",
    "Account": "511825856493",
    "Arn": "arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155/nhan"
}
```

Giải thích:

Xác nhận đang thao tác đúng account TF4 và đúng role của Nhân/CDO08 trước khi scan cluster.

### 3.2. Xác minh Kubernetes context

Command:

```bash
kubectl config current-context
```

Output:

```text
arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster
```

Command:

```bash
kubectl get ns
```

Output chính:

```text
NAME                   STATUS   AGE
techx-observability    Active   7d17h
techx-tf4              Active   8d
```

Giải thích:

Xác nhận kubeconfig đang trỏ đúng EKS cluster và cả hai namespace trong scope đều tồn tại.

### 3.3. Before scan securityContext `techx-tf4`

Command:

```bash
kubectl -n techx-tf4 get deploy,sts -o jsonpath='{range .items[*]}{.kind}/{.metadata.name}{"\t"}{range .spec.template.spec.containers[*]}{.name}{":"}{.securityContext}{" | "}{end}{"\n"}{end}'
```

Output:

```text
Deployment/accounting	accounting: | 
Deployment/ad	ad: | 
Deployment/cart	cart: | 
Deployment/checkout	checkout: | 
Deployment/currency	currency: | 
Deployment/email	email: | 
Deployment/flagd	flagd: | 
Deployment/fraud-detection	fraud-detection: | 
Deployment/frontend	frontend:{"runAsGroup":1001,"runAsNonRoot":true,"runAsUser":1001} | 
Deployment/frontend-proxy	frontend-proxy:{"runAsGroup":101,"runAsNonRoot":true,"runAsUser":101} | 
Deployment/image-provider	image-provider: | 
Deployment/kafka	kafka:{"runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000} | 
Deployment/llm	llm: | 
Deployment/load-generator	load-generator: | 
Deployment/payment	payment:{"runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000} | 
Deployment/postgresql	postgresql: | 
Deployment/product-catalog	product-catalog: | 
Deployment/product-reviews	product-reviews:{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true,"runAsNonRoot":true,"runAsUser":10001} | 
Deployment/quote	quote:{"runAsGroup":33,"runAsNonRoot":true,"runAsUser":33} | 
Deployment/recommendation	recommendation: | 
Deployment/shipping	shipping: | 
Deployment/valkey-cart	valkey-cart:{"runAsGroup":1000,"runAsNonRoot":true,"runAsUser":999} | 
```

Giải thích:

Đây là evidence trước sửa. Nhiều workload container-level securityContext đang trống. Một số workload có `runAsNonRoot` nhưng thiếu `allowPrivilegeEscalation`, `capabilities.drop` và `seccompProfile`.

### 3.4. Before scan securityContext `techx-observability`

Command:

```bash
kubectl -n techx-observability get deploy,sts -o jsonpath='{range .items[*]}{.kind}/{.metadata.name}{"\t"}{range .spec.template.spec.containers[*]}{.name}{":"}{.securityContext}{" | "}{end}{"\n"}{end}'
```

Output:

```text
Deployment/grafana	grafana-sc-alerts:{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"seccompProfile":{"type":"RuntimeDefault"}} | grafana-sc-dashboard:{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"seccompProfile":{"type":"RuntimeDefault"}} | grafana-sc-datasources:{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"seccompProfile":{"type":"RuntimeDefault"}} | grafana:{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"privileged":false,"seccompProfile":{"type":"RuntimeDefault"}} | 
Deployment/jaeger	jaeger:{} | 
Deployment/metrics-server	metrics-server:{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true,"runAsNonRoot":true,"runAsUser":1000,"seccompProfile":{"type":"RuntimeDefault"}} | 
Deployment/prometheus	prometheus-server-configmap-reload: | prometheus-server: | 
StatefulSet/opensearch	opensearch:{"capabilities":{"drop":["ALL"]},"runAsNonRoot":true,"runAsUser":1000} | 
StatefulSet/techx-observability-alertmanager	alertmanager:{"runAsGroup":65534,"runAsNonRoot":true,"runAsUser":65534} | 
```

Giải thích:

Xác nhận gap đúng như task: Jaeger container securityContext `{}`; Prometheus server và configmap reload chưa có container-level securityContext.

### 3.5. Scan image đang chạy

Command:

```bash
kubectl -n techx-tf4 get deploy,sts -o jsonpath='{range .items[*]}{.kind}/{.metadata.name}{"\t"}{range .spec.template.spec.containers[*]}{.name}{":"}{.image}{" | "}{end}{"\n"}{end}'
kubectl -n techx-observability get deploy,sts -o jsonpath='{range .items[*]}{.kind}/{.metadata.name}{"\t"}{range .spec.template.spec.containers[*]}{.name}{":"}{.image}{" | "}{end}{"\n"}{end}'
```

Output chính:

```text
Deployment/checkout	checkout:511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-checkout |
Deployment/fraud-detection	fraud-detection:511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-fraud-detection |
Deployment/image-provider	image-provider:511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-image-provider |
Deployment/postgresql	postgresql:postgres:17.6 |
Deployment/jaeger	jaeger:jaegertracing/jaeger:2.17.0 |
Deployment/prometheus	prometheus-server-configmap-reload:quay.io/prometheus-operator/prometheus-config-reloader:v0.91.0 | prometheus-server:quay.io/prometheus/prometheus:v3.11.3 |
```

Giải thích:

Image list dùng để map workload với Dockerfile/chart upstream và quyết định workload nào có thể harden ngay.

### 3.6. Kiểm tra runtime UID bằng `id`

Commands đã chạy:

```bash
kubectl -n techx-tf4 exec deploy/accounting -- id
kubectl -n techx-tf4 exec deploy/ad -- id
kubectl -n techx-tf4 exec deploy/cart -- id
kubectl -n techx-tf4 exec deploy/currency -- id
kubectl -n techx-tf4 exec deploy/email -- id
kubectl -n techx-tf4 exec deploy/image-provider -- id
kubectl -n techx-tf4 exec deploy/llm -- id
```

Output chính:

```text
accounting: uid=1654(app) gid=1654(app) groups=1654(app)
ad: uid=0(root) gid=0(root) groups=0(root)
cart: uid=0(root) gid=0(root) groups=0(root),...
currency: uid=0(root) gid=0(root) groups=0(root),...
email: uid=0(root) gid=0(root) groups=0(root),...
image-provider: uid=101(nginx) gid=101(nginx) groups=101(nginx)
llm: uid=0(root) gid=0(root) groups=0(root),...
```

Một số distroless image không có binary `id`:

```text
checkout: exec: "id": executable file not found in $PATH
fraud-detection: exec: "id": executable file not found in $PATH
product-catalog: exec: "id": executable file not found in $PATH
shipping: exec: "id": executable file not found in $PATH
flagd: exec: "id": executable file not found in $PATH
```

Giải thích:

Với image có shell/coreutils, `id` cho biết container đang root hay non-root thật. Với distroless, không có `id`, nên dùng Dockerfile evidence. `checkout`, `fraud-detection`, `product-catalog`, `shipping` đều dùng image distroless `:nonroot`, nên patch được với UID `65532`. `flagd` không có `id` và đang có init copy config vào emptyDir nên để exception cho tới khi audit UID/GID và write path.

### 3.7. Dockerfile evidence

Commands đã chạy:

```bash
rg -n "^USER|useradd|adduser|runAsUser|runAsGroup|securityContext|podSecurityContext" techx-corp-platform\src techx-corp-chart\values.yaml deploy\values-observability.yaml deploy\values-app-stamp.yaml
Get-Content -Raw techx-corp-platform\src\accounting\Dockerfile
Get-Content -Raw techx-corp-platform\src\checkout\Dockerfile
Get-Content -Raw techx-corp-platform\src\fraud-detection\Dockerfile
Get-Content -Raw techx-corp-platform\src\image-provider\Dockerfile
Get-Content -Raw techx-corp-platform\src\product-catalog\Dockerfile
Get-Content -Raw techx-corp-platform\src\shipping\Dockerfile
```

Output chính:

```text
techx-corp-platform\src\accounting\Dockerfile:25:USER app
techx-corp-platform\src\accounting\Dockerfile:33:USER app
techx-corp-platform\src\image-provider\Dockerfile:6:USER 101
checkout Dockerfile final image: gcr.io/distroless/static-debian12:nonroot
fraud-detection Dockerfile final image: gcr.io/distroless/java17-debian12:nonroot
product-catalog Dockerfile final image: gcr.io/distroless/static-debian12:nonroot
shipping Dockerfile final image: gcr.io/distroless/cc-debian13:nonroot
```

Giải thích:

Dockerfile evidence xác nhận nhóm có thể harden ngay không cần rebuild image.

### 3.8. Kiểm tra Helm subchart keys

Commands:

```bash
helm show values techx-corp-chart\charts\prometheus-29.6.0.tgz
helm show values techx-corp-chart\charts\jaeger-4.7.0.tgz
```

Output chính:

```yaml
prometheus:
  server:
    securityContext:
      runAsUser: 65534
      runAsNonRoot: true
      runAsGroup: 65534
      fsGroup: 65534
    containerSecurityContext: {}
  configmapReload:
    prometheus:
      containerSecurityContext: {}

jaeger:
  jaeger:
    podSecurityContext:
      runAsUser: 10001
      runAsGroup: 10001
      fsGroup: 10001
    securityContext: {}
```

Giải thích:

Các key này là nơi đúng để set container-level securityContext cho Prometheus và Jaeger. Không dùng `default.securityContext` của app chart vì dependency chart không nhận key đó.

### 3.9. Helm lint

Command:

```bash
helm lint techx-corp-chart
```

Output:

```text
==> Linting techx-corp-chart
[INFO] Chart.yaml: icon is recommended

1 chart(s) linted, 0 chart(s) failed
```

Giải thích:

Chart hợp lệ sau patch.

### 3.10. Helm render verification

Commands:

```bash
helm template techx techx-corp-chart -n techx-tf4 --show-only templates/component.yaml
helm template techx techx-corp-chart -n techx-observability
```

Output chính từ render:

```yaml
name: accounting
securityContext:
  allowPrivilegeEscalation: false
  capabilities:
    drop:
    - ALL
  runAsGroup: 1654
  runAsNonRoot: true
  runAsUser: 1654
  seccompProfile:
    type: RuntimeDefault

name: wait-for-kafka
securityContext:
  allowPrivilegeEscalation: false
  capabilities:
    drop:
    - ALL
  runAsGroup: 65534
  runAsNonRoot: true
  runAsUser: 65534
  seccompProfile:
    type: RuntimeDefault

name: checkout
securityContext:
  allowPrivilegeEscalation: false
  capabilities:
    drop:
    - ALL
  runAsGroup: 65532
  runAsNonRoot: true
  runAsUser: 65532
  seccompProfile:
    type: RuntimeDefault

name: wait-for-valkey-cart
securityContext:
  allowPrivilegeEscalation: false
  capabilities:
    drop:
    - ALL
  runAsGroup: 65534
  runAsNonRoot: true
  runAsUser: 65534
  seccompProfile:
    type: RuntimeDefault

name: jaeger
securityContext:
  allowPrivilegeEscalation: false
  capabilities:
    drop:
    - ALL
  runAsGroup: 10001
  runAsNonRoot: true
  runAsUser: 10001
  seccompProfile:
    type: RuntimeDefault

name: prometheus-server-configmap-reload
securityContext:
  allowPrivilegeEscalation: false
  capabilities:
    drop:
    - ALL
  runAsGroup: 65534
  runAsNonRoot: true
  runAsUser: 65534
  seccompProfile:
    type: RuntimeDefault

name: prometheus-server
securityContext:
  allowPrivilegeEscalation: false
  capabilities:
    drop:
    - ALL
  runAsGroup: 65534
  runAsNonRoot: true
  runAsUser: 65534
  seccompProfile:
    type: RuntimeDefault
```

Giải thích:

Render xác nhận các key đã ra đúng manifest container-level.

### 3.11. Helm release status

Command:

```bash
helm list -A
```

Output liên quan:

```text
NAME                 NAMESPACE             REVISION   STATUS   CHART
techx-corp           techx-tf4             47         failed   techx-corp-0.40.9
techx-observability  techx-observability   37         failed   techx-corp-0.40.9
```

Giải thích:

Hai release đang `failed` từ trước khi rollout task này. Cần kiểm tra lịch sử Helm khi người có quyền deploy thực hiện rollout.

### 3.12. Kiểm tra quyền rollout

Commands:

```bash
kubectl auth can-i patch deployments -n techx-tf4
kubectl auth can-i patch deployments -n techx-observability
kubectl auth can-i update deployments -n techx-tf4
kubectl auth can-i create pods/exec -n techx-tf4
```

Output:

```text
no
no
no
no
```

Giải thích:

SSO hiện tại là read-only/audit. Vì vậy không rollout bằng role này để tránh tạo false evidence. Cần dùng role deploy operator hoặc Nam hỗ trợ rollout.

### 3.13. Baseline health hiện tại

Command:

```bash
kubectl -n techx-tf4 get deploy,sts,pods
```

Output chính:

```text
deployment.apps/accounting        1/1
deployment.apps/cart              2/2
deployment.apps/checkout          2/2
deployment.apps/frontend          2/2
deployment.apps/product-catalog   2/2
deployment.apps/shipping          2/2
deployment.apps/valkey-cart       1/1
all listed pods: Running, RESTARTS 0
```

Command:

```bash
kubectl -n techx-observability get deploy,sts,pods
```

Output chính:

```text
deployment.apps/grafana          1/1
deployment.apps/jaeger           1/1
deployment.apps/metrics-server   1/1
deployment.apps/prometheus       1/1
statefulset.apps/opensearch      1/1
pod/prometheus-...               2/2 Running
```

Command:

```bash
curl.exe -I http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com
```

Output:

```text
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
x-powered-by: Next.js
x-envoy-upstream-service-time: 8
server: envoy
```

Giải thích:

Baseline trước rollout đang healthy. Storefront GET qua ALB trả `200 OK`. Smoke checkout sau rollout vẫn cần chạy sau khi apply chart.

### 3.14. Bổ sung sau review missing workload

Commands đã chạy để kiểm tra phần còn thiếu:

```powershell
rg -n "securityContext:|initContainers:|name: (accounting|ad|cart|checkout|currency|email|flagd|fraud-detection|image-provider|llm|load-generator|postgresql|product-catalog|recommendation|shipping|jaeger|prometheus|server|configmap-reload)" techx-corp-chart docs
Get-Content -Raw techx-corp-chart\templates\_objects.tpl
Get-Content -Raw techx-corp-platform\src\ad\Dockerfile
Get-Content -Raw techx-corp-platform\src\cart\src\Dockerfile
Get-Content -Raw techx-corp-platform\src\currency\Dockerfile
Get-Content -Raw techx-corp-platform\src\email\Dockerfile
Get-Content -Raw techx-corp-platform\src\llm\Dockerfile
Get-Content -Raw techx-corp-platform\src\load-generator\Dockerfile
Get-Content -Raw techx-corp-platform\src\recommendation\Dockerfile
```

Output chính:

```text
techx-corp-chart/values.yaml vẫn giữ default.securityContext: {}
_objects.tpl render container securityContext từ .Values.components.<name>.securityContext
_objects.tpl render initContainers raw từ values, nên init container phải có securityContext riêng trong values
ad Dockerfile final image chưa có USER trước patch
cart Dockerfile final image chưa có USER trước patch
currency Dockerfile final image chưa có USER trước patch
email Dockerfile final image chưa có USER trước patch
llm Dockerfile final image chưa có USER trước patch
load-generator Dockerfile final image chưa có USER trước patch
recommendation Dockerfile final image chưa có USER trước patch
```

Giải thích:

Các workload trên không nên chỉ ép `runAsNonRoot` bằng chart khi image chưa có user/ownership phù hợp. Vì vậy phần bổ sung này sửa Dockerfile trước để image hỗ trợ non-root thật, sau đó mới thêm chart `securityContext` UID/GID `10001:10001`.

## 4. Exception log

Sau phần bổ sung Dockerfile + chart, các app image do repo kiểm soát trước đó chạy root (`ad`, `cart`, `currency`, `email`, `llm`, `load-generator`, `recommendation`) không còn là exception trong source. Chúng cần image rebuild/push và ArgoCD/Helm rollout để runtime nhận UID/GID `10001:10001`.

Exception còn lại:

| Namespace | Workload | Missing control | Lý do kỹ thuật | Risk | Owner | Kế hoạch xử lý |
| --- | --- | --- | --- | --- | --- | --- |
| `techx-tf4` | `flagd` main + init `init-config` | UID/GID chưa xác nhận rõ trong runtime | Image `ghcr.io/open-feature/flagd:v0.12.9` không có `id`; init container copy config vào mounted emptyDir `/etc/flagd`, cần kiểm tra ownership để main container đọc được file | Ép UID sai có thể làm flagd không đọc config, ảnh hưởng feature flags và checkout path | Nhân + Nam | Research official flagd UID/GID, test init copy ownership hoặc dùng `fsGroup`, rollout riêng rồi remove exception |
| `techx-tf4` | `postgresql` | `runAsNonRoot`, baseline | Official `postgres:17.6` cần audit UID, PVC ownership, `PGDATA`; hiện DB user là `POSTGRES_USER=root` và có PVC mounted tại `/var/lib/postgresql/data` | Ép sai UID/GID có thể crash DB hoặc mất quyền ghi PVC | Nhân + Nam + Nguyên review risk | Test staging với postgres UID/GID, `fsGroup`, PVC ownership; rollout riêng |
| `techx-observability` | `opensearch` init `fsgroup-volume` | init container `runAsUser: 0` | Subchart dùng root init để `chown` PVC data | Root init tăng bootstrap risk nhưng main container đã non-root | Nguyên + Nam | Đánh giá storage class/fsGroup có thể bỏ root chown init không; làm ở follow-up riêng |
| `techx-observability` | `alertmanager` | thiếu explicit `allowPrivilegeEscalation/drop/seccomp` ở container-level | Đã non-root nhưng chưa nằm trong gap chính của task; cần xác thực key chart con trước khi patch | Rủi ro thấp hơn root nhưng baseline chưa đồng nhất | Nhân | Validate chart key và patch follow-up nếu Mandate 5 admission yêu cầu toàn bộ observability container |

## 5. Rollout plan cho Nam/DeployOperator

Do current SSO không có quyền rollout, người có quyền deploy cần chạy:

```bash
helm upgrade techx-corp techx-corp-chart -n techx-tf4
kubectl -n techx-tf4 rollout status deploy/accounting --timeout=180s
kubectl -n techx-tf4 rollout status deploy/ad --timeout=180s
kubectl -n techx-tf4 rollout status deploy/cart --timeout=180s
kubectl -n techx-tf4 rollout status deploy/checkout --timeout=180s
kubectl -n techx-tf4 rollout status deploy/currency --timeout=180s
kubectl -n techx-tf4 rollout status deploy/email --timeout=180s
kubectl -n techx-tf4 rollout status deploy/fraud-detection --timeout=180s
kubectl -n techx-tf4 rollout status deploy/frontend --timeout=180s
kubectl -n techx-tf4 rollout status deploy/frontend-proxy --timeout=180s
kubectl -n techx-tf4 rollout status deploy/image-provider --timeout=180s
kubectl -n techx-tf4 rollout status deploy/llm --timeout=180s
kubectl -n techx-tf4 rollout status deploy/load-generator --timeout=180s
kubectl -n techx-tf4 rollout status deploy/payment --timeout=180s
kubectl -n techx-tf4 rollout status deploy/product-catalog --timeout=180s
kubectl -n techx-tf4 rollout status deploy/product-reviews --timeout=180s
kubectl -n techx-tf4 rollout status deploy/quote --timeout=180s
kubectl -n techx-tf4 rollout status deploy/recommendation --timeout=180s
kubectl -n techx-tf4 rollout status deploy/shipping --timeout=180s
kubectl -n techx-tf4 rollout status deploy/kafka --timeout=180s
kubectl -n techx-tf4 rollout status deploy/valkey-cart --timeout=180s
```

Sau đó:

```bash
helm upgrade techx-observability techx-corp-chart -n techx-observability
kubectl -n techx-observability rollout status deploy/jaeger --timeout=180s
kubectl -n techx-observability rollout status deploy/prometheus --timeout=180s
```

Nếu workload crash do UID/GID:

```bash
kubectl -n <namespace> rollout undo deploy/<workload>
```

## 6. Verification sau rollout cần attach vào Jira

Chạy lại lệnh acceptance criteria:

```bash
kubectl -n techx-tf4 get deploy,sts -o jsonpath='{range .items[*]}{.kind}/{.metadata.name}{"\t"}{range .spec.template.spec.containers[*]}{.name}{":"}{.securityContext}{" | "}{end}{"\n"}{end}'
kubectl -n techx-observability get deploy,sts -o jsonpath='{range .items[*]}{.kind}/{.metadata.name}{"\t"}{range .spec.template.spec.containers[*]}{.name}{":"}{.securityContext}{" | "}{end}{"\n"}{end}'
```

Smoke test:

```bash
curl -I http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com
kubectl -n techx-tf4 logs deploy/checkout --tail=100
kubectl -n techx-observability logs deploy/prometheus -c prometheus-server --tail=50
kubectl -n techx-observability logs deploy/jaeger --tail=50
```

Cần nộp vào Jira:

- Link PR/commit chứa `techx-corp-chart/values.yaml`.
- File evidence này.
- Output before scan.
- Output after scan sau rollout.
- Bảng exception ở mục 4.
- Log rollout status từng workload.
- Kết quả smoke storefront/checkout.
- Kết quả observability: Prometheus và Jaeger còn running/log không lỗi.
- Ghi rõ không thay đổi admission policy, không bật `readOnlyRootFilesystem` đại trà, không đổi business logic.
