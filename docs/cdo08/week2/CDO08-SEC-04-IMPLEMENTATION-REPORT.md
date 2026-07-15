# Báo cáo triển khai và nhật ký lệnh CDO08-SEC-04

## 1. Trạng thái báo cáo

- Ngày thực hiện: 15/07/2026, múi giờ Asia/Bangkok.
- Owner: Nhân.
- Reviewer: Nguyên — đang chờ review.
- Triển khai trong source code: đã hoàn thành và kiểm tra local.
- Rollout workload lên runtime: chưa thực hiện vì đang chờ technical approval và service owner smoke test.
- Rollout admission policy: chưa thực hiện vì role hiện tại không có quyền quản lý ValidatingAdmissionPolicy ở cluster scope.
- Attach evidence vào Jira và cập nhật trạng thái PM: đang chờ thao tác bên ngoài repository.

Báo cáo này tách biệt rõ giữa “đã triển khai trong source code” và “đã rollout lên cluster”. Trong quá trình làm task, không có workload, namespace, policy, binding hoặc tài nguyên Kubernetes nào bị create, patch, label, restart hay delete.

## 2. Phạm vi đã hoàn thành trong source code

### 2.1. Hardening Helm workload

Đã thay đổi `techx-corp-chart/values.yaml` và `techx-corp-chart/templates/_objects.tpl`:

- Thêm baseline mặc định cho application container và sidecar:
  - `allowPrivilegeEscalation: false`.
  - Drop toàn bộ Linux capabilities bằng `ALL`.
  - `seccompProfile.type: RuntimeDefault`.
- Sửa logic Helm template từ “component override thay thế hoàn toàn default” thành “merge default với component override”. Nhờ đó, các component đã có UID/GID riêng vẫn nhận được các guard mặc định mới.
- Không bật `readOnlyRootFilesystem` global vì chưa kiểm tra đầy đủ write path của từng image.
- Pin toàn bộ BusyBox init container về đúng digest quan sát được trên runtime:
  `busybox@sha256:fd8d9aa63ba2f0982b5304e1ee8d3b90a210bc1ffb5314d980eb6962f1a9715d`.
- Harden BusyBox init container với:
  - UID `65534`.
  - `runAsNonRoot: true`.
  - `allowPrivilegeEscalation: false`.
  - Drop `ALL` capabilities.
  - `RuntimeDefault` seccomp.
  - Giữ nguyên CPU/memory requests và limits hiện có.
- Chỉ thêm `runAsNonRoot: true` cho những image có bằng chứng trực tiếp trong Dockerfile rằng final image/user là non-root:
  - `accounting`: Dockerfile có `USER app`.
  - `checkout`: dùng distroless image `:nonroot`.
  - `fraud-detection`: dùng distroless image `:nonroot`.
  - `image-provider`: dùng `nginx-unprivileged`, `USER 101`.
  - `product-catalog`: dùng distroless image `:nonroot`.
  - `shipping`: dùng distroless image `:nonroot`.
- Sau khi runtime evidence xác nhận `load-generator` chạy UID/GID 0, đã remediation source của component này:
  - Tạo user/group cố định UID/GID `10001` trong final Docker image.
  - Đặt `HOME=/home/loadgenerator` và `XDG_CACHE_HOME=/home/loadgenerator/.cache` để Locust/Chromium có home/cache path của non-root user.
  - Chuyển ownership của application directory, home và Playwright browser directory cho UID/GID 10001.
  - Dùng `COPY --chown=10001:10001` cho `locustfile.py` và `people.json`.
  - Đặt `USER 10001:10001` trong Dockerfile.
  - Thêm `runAsUser`, `runAsGroup` và `runAsNonRoot` tương ứng trong Helm values.
  - Chưa bật `readOnlyRootFilesystem`; cần build image và smoke/load test write path trước.
- Giữ nguyên UID/GID đã tồn tại của `frontend`, `frontend-proxy`, `kafka`, `payment`, `quote` và `valkey-cart`, đồng thời merge thêm baseline guard mới.

### 2.2. Admission policy-as-code

Đã thêm native Kubernetes `ValidatingAdmissionPolicy` trong thư mục `deploy/admission/`:

- Policy cho các loại resource:
  - Pod.
  - Deployment.
  - StatefulSet.
  - DaemonSet.
  - Job.
  - CronJob.
- Có cover thao tác update ephemeral container của Pod.
- Kiểm tra cả application container và init container đối với:
  - Bắt buộc non-root.
  - Không cho privilege escalation.
  - Drop capability `ALL`.
  - Dùng `RuntimeDefault` hoặc `Localhost` seccomp.
  - Image phải dùng tag cố định hoặc SHA-256 digest.
  - Cấm image không tag và `latest`.
  - Bắt buộc CPU/memory requests và limits.
- Audit binding chỉ có hiệu lực với namespace mang label:
  `security.techx.io/runtime-hardening=audit`.
- Enforce binding chỉ có hiệu lực với namespace mang label:
  `security.techx.io/runtime-hardening=enforce`.
- Có manifest test tách riêng cho:
  - Chạy root.
  - Dùng image `latest`.
  - Thiếu resource limits.
  - Manifest hợp lệ làm control case.
- Có README hướng dẫn rollout/rollback và ADR 014 ghi lại quyết định kỹ thuật.

Giải pháp được chọn là native ValidatingAdmissionPolicy vì Kubernetes server đang chạy phiên bản v1.34.9 và giải pháp này không cần cài thêm controller. Kyverno và Gatekeeper vẫn là phương án thay thế nếu platform team đã vận hành sẵn một trong hai công cụ đó.

## 3. Baseline runtime thu thập trước khi thay đổi

Namespace kiểm tra: `techx-tf4`.

### 3.1. Các lệnh dùng để thu thập baseline

#### Xác nhận đúng cluster context

```powershell
kubectl config current-context
```

Kết quả quan sát:

```text
arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster
```

Lý do chạy: tránh thu thập nhầm cluster hoặc vô tình sử dụng kết luận của môi trường khác.

#### Liệt kê tất cả loại workload trong namespace

```powershell
kubectl -n techx-tf4 get deploy,statefulset,daemonset,job,cronjob -o wide
```

Lý do chạy: không chỉ kiểm tra Deployment mà còn tìm StatefulSet, DaemonSet, Job và CronJob vì admission policy phải cover tất cả các nhóm workload này.

Kết quả tóm tắt:

- Có 22 Deployment.
- Output không ghi nhận StatefulSet, DaemonSet, Job hoặc CronJob trong namespace tại thời điểm kiểm tra.
- Snapshot đầu tiên ghi nhận `load-generator` là `0/0`. Evidence do owner chạy lại sau đó cho thấy workload đã chuyển thành `1/1`, tức đang active. Evidence mới hơn bên dưới thay thế kết luận `0/0` cũ.

#### Thu thập main container của từng Pod

```powershell
kubectl -n techx-tf4 get pods `
  -o jsonpath='{range .items[*]}{range .spec.containers[*]}{..metadata.name}{"\t"}{.name}{"\t"}{.image}{"\t"}{.securityContext}{"\t"}{.resources}{"\n"}{end}{end}'
```

Mỗi dòng output gồm:

```text
pod-name    container-name    image    securityContext    resources
```

Lý do chạy:

- Xác định image thực tế được khai báo trong Pod spec.
- Kiểm tra container nào có hoặc thiếu `securityContext`.
- Kiểm tra requests/limits của từng container, không chỉ nhìn values mặc định.
- Dùng vòng lặp `range .spec.containers[*]` để không bỏ sót sidecar.

Ví dụ output đã quan sát:

```text
frontend  <ECR image>:8340af1-frontend  {"runAsGroup":1001,"runAsNonRoot":true,"runAsUser":1001}  {"limits":{"cpu":"400m","memory":"320Mi"},"requests":{"cpu":"100m","memory":"192Mi"}}
postgresql  postgres:17.6  <securityContext rỗng>  {"limits":{"cpu":"500m","memory":"512Mi"},"requests":{"cpu":"50m","memory":"256Mi"}}
```

Ví dụ trên đã rút gọn tên Pod/ECR để tài liệu dễ đọc; raw output của lệnh là nguồn kiểm chứng chính.

#### Evidence bổ sung cho load-generator

Owner chạy lại workload inventory và ghi nhận:

```text
deployment.apps/load-generator  1/1  1  1  7d14h  load-generator  511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-load-generator
```

Ý nghĩa:

- `READY 1/1`: một trên một Pod mong muốn đang Ready.
- `UP-TO-DATE 1`: một Pod dùng Deployment template mới nhất.
- `AVAILABLE 1`: một Pod đang available.
- Workload đang active nên phải được smoke/load test và theo dõi SLO khi harden; không được coi là workload đang tắt.

Lệnh kiểm tra riêng Pod, image, securityContext và resources:

```bash
kubectl -n techx-tf4 get pods \
  -l opentelemetry.io/name=load-generator \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\\t"}{range .spec.containers[*]}{.name}{"\t"}{.image}{"\t"}{.securityContext}{"\t"}{.resources}{"\n"}{end}{end}'
```

Output do owner cung cấp:

```text
load-generator-7dbc8d784-dxcq6  load-generator  511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-load-generator  <securityContext rỗng>  {"limits":{"cpu":"600m","memory":"512Mi"},"requests":{"cpu":"300m","memory":"256Mi"}}
```

Kết luận từ Pod spec:

- Image dùng tag cố định `8340af1-load-generator`, không dùng `latest`.
- Có đủ CPU/memory requests và limits.
- Container-level `securityContext` đang rỗng.
- Resources trên runtime khác default values hiện đọc trong source. Trước rollout phải xác định đúng values override hoặc release source đang điều khiển Deployment.

Lệnh xác minh UID/GID thực tế bên trong container:

```bash
kubectl -n techx-tf4 exec deployment/load-generator -- id
```

Output:

```text
uid=0(root) gid=0(root) groups=0(root)
```

Kết luận bảo mật:

- `load-generator` được runtime xác nhận đang chạy root, không còn chỉ là suy luận từ securityContext rỗng.
- Workload vi phạm yêu cầu “không container nào chạy root” của Directive #5.
- Không được chuyển namespace sang enforce khi manifest của `load-generator` chưa remediation. Nếu Pod bị recreate sau enforce, admission có thể từ chối Pod mới và làm giảm availability.
- Source đã được sửa để final image dùng UID/GID 10001 và Helm bắt buộc non-root. Vẫn phải build/push image bằng tag mới, cập nhật release source và chạy smoke/load test trước khi coi runtime đã remediation.
- Không ép một UID ngẫu nhiên trong Helm vì image có thể cần ghi file. Phải kiểm tra working directory, cache, report/output path và file ownership.

#### Thu thập init container riêng

```powershell
kubectl -n techx-tf4 get pods `
  -o jsonpath='{range .items[*]}{range .spec.initContainers[*]}{..metadata.name}{"\t"}{.name}{"\t"}{.image}{"\t"}{.securityContext}{"\t"}{.resources}{"\n"}{end}{end}'
```

Lý do chạy: init container cũng có thể chạy root, dùng image `latest`, thiếu resources hoặc privilege guard. Chỉ kiểm tra `.spec.containers` sẽ bỏ sót nhóm này.

Kết quả tóm tắt:

- Quan sát được 7 init-container instance.
- Các init container đều có CPU/memory requests và limits.
- Các init container dùng `busybox:latest` hoặc `busybox` không tag.
- Runtime `securityContext` của chúng đang rỗng trước thay đổi.

#### Xác định digest thật của BusyBox đang chạy

```powershell
kubectl -n techx-tf4 get pods `
  -o jsonpath='{range .items[*]}{range .status.initContainerStatuses[*]}{..metadata.name}{"\t"}{.name}{"\t"}{.image}{"\t"}{.imageID}{"\n"}{end}{end}'
```

Lý do chạy: tag `latest` có thể trỏ sang image khác theo thời gian. Lấy `status.initContainerStatuses[*].imageID` giúp pin đúng digest đang chạy, tránh vừa harden vừa vô tình đổi phiên bản image.

Kết quả quan sát cho cả 7 instance:

```text
docker.io/library/busybox@sha256:fd8d9aa63ba2f0982b5304e1ee8d3b90a210bc1ffb5314d980eb6962f1a9715d
```

#### Kiểm tra Dockerfile để xác minh image có non-root user

```powershell
rg --files -g 'Dockerfile*' -g '!**/node_modules/**'
rg -n '^(USER|FROM)|user:' techx-corp-platform `
  -g 'Dockerfile*' `
  -g 'docker-compose*.yml'
```

Lý do chạy: runtime thiếu `runAsNonRoot` không chứng minh chắc chắn process là root. Dockerfile cung cấp thêm bằng chứng về final base image và lệnh `USER`, giúp quyết định service nào có thể vào batch non-root ít rủi ro.

Giới hạn:

- Dockerfile trong repository chỉ là bằng chứng source; image trên ECR có thể được build từ commit khác.
- Cần đối chiếu image tag/commit và smoke test trước khi rollout.
- Với third-party image như PostgreSQL, Valkey và flagd, cần kiểm tra thêm tài liệu/image metadata và quyền volume.

#### Kiểm tra quyền đọc admission inventory

```powershell
kubectl get crd
kubectl get validatingadmissionpolicies,validatingadmissionpolicybindings
kubectl get validatingwebhookconfigurations
```

Lý do chạy: xác định cluster đã có Kyverno, Gatekeeper, VAP hoặc webhook khác hay chưa để tránh cài policy trùng/xung đột.

Kết quả: các lệnh bị `Forbidden` do role hiện tại không có quyền đọc tài nguyên cluster scope. Vì vậy báo cáo không khẳng định cluster chưa có admission engine; báo cáo chỉ ghi “chưa thể xác nhận”. Chi tiết quyền cần bổ sung nằm ở mục 10.

### 3.2. Tổng quan workload

- Phát hiện 22 Deployment.
- Tất cả main container đang chạy đều dùng image tag cố định.
- Tất cả main container và init container quan sát được đều có CPU/memory requests và limits.
- Có 7 instance init container đang dùng `busybox:latest` hoặc `busybox` không tag.
- Cả 7 instance đều resolve về cùng digest đã được pin ở phần trên.
- Output không ghi nhận StatefulSet, DaemonSet, Job hoặc CronJob trong namespace.

### 3.3. Baseline securityContext của main container

| Workload | `runAsNonRoot` trên runtime trước thay đổi | Quyết định trong source |
|---|---:|---|
| accounting | Thiếu | Batch 1: thêm; final Dockerfile user là `app` |
| ad | Thiếu | Cần exception/remediation; chưa có bằng chứng `USER` trong final image |
| cart | Thiếu | Cần exception/remediation; chưa có bằng chứng `USER` trong final image |
| checkout | Thiếu | Batch 1: thêm; dùng distroless non-root image |
| currency | Thiếu | Cần exception/remediation; chưa có bằng chứng `USER` trong final image |
| email | Thiếu | Cần exception/remediation; chưa có bằng chứng `USER` trong final image |
| flagd | Thiếu | Third-party image; cần test và xác minh UID upstream |
| fraud-detection | Thiếu | Batch 1: thêm; dùng distroless non-root image |
| frontend | Có, UID/GID 1001 | Giữ nguyên và merge thêm baseline guard |
| frontend-proxy | Có, UID/GID 101 | Giữ nguyên và merge thêm baseline guard |
| image-provider | Thiếu | Batch 1: thêm UID/GID 101; dùng unprivileged image |
| kafka | Có, UID/GID 1000 | Stateful batch; giữ nguyên và test PVC |
| llm | Thiếu | Cần exception/remediation; chưa có bằng chứng `USER` trong final image |
| load-generator | Thiếu; active 1/1; lệnh `id` xác nhận UID/GID 0 root | Source đã sửa UID/GID 10001; còn build/push tag mới, rollout và smoke/load test trước enforce |
| payment | Có, UID/GID 1000 | Giữ nguyên và merge thêm baseline guard |
| postgresql | Thiếu | Stateful third-party exception; cần test entrypoint và quyền PVC |
| product-catalog | Thiếu | Batch 1: thêm; dùng distroless non-root image |
| product-reviews | Thiếu | Cần exception/remediation; chưa có bằng chứng `USER` trong final image |
| quote | Có, UID/GID 33 | Giữ nguyên và merge thêm baseline guard |
| recommendation | Thiếu | Cần exception/remediation; chưa có bằng chứng `USER` trong final image |
| shipping | Thiếu | Batch 1: thêm; dùng distroless non-root image |
| valkey-cart | Có, UID 999/GID 1000 | Stateful batch; giữ nguyên và test PVC |

Runtime thiếu `securityContext` không tự động chứng minh process đang chạy UID 0. Nó chứng minh rằng Kubernetes chưa enforce non-root cho container đó. Danh sách exception phải tiếp tục mở cho tới khi image metadata, runtime UID và smoke test được review.

## 4. Đánh giá rủi ro và kế hoạch rollout theo batch

### Batch 0 — Chỉ audit admission

1. Xin quyền cluster scope hoặc nhờ platform operator thực hiện.
2. Nguyên review policy, binding và `failurePolicy`.
3. Chạy server-side dry-run để API server compile CEL.
4. Apply policy và audit binding.
5. Chỉ label một namespace test riêng ở chế độ `audit`.

### Batch 1 — Stateless image đã xác minh non-root

Các service:

- accounting.
- checkout.
- fraud-detection.
- image-provider.
- product-catalog.
- shipping.

Mỗi lần chỉ deploy một batch nhỏ. Cần theo dõi rollout, event, restart count, log, latency/error rate và chạy service smoke test.

### Batch 2 — Workload đã khai báo non-root từ trước

Các service:

- frontend.
- frontend-proxy.
- payment.
- quote.

Thay đổi có hiệu lực mới trong batch này là APE=false, drop ALL và RuntimeDefault seccomp.

### Batch 3 — Stateful và component đặc biệt

- `kafka` và `valkey-cart`: phải kiểm tra PVC ownership và write path.
- `postgresql`: phải xác định UID/GID non-root, test database initialization và quyền trên PVC hiện có.
- `flagd`: phải test init container copy config và xác minh UID của image upstream.

### Batch 4 — Image cần remediation

Các service:

- ad.
- cart.
- currency.
- email.
- llm.
- load-generator — source non-root đã sửa; chưa hoàn thành runtime cho tới khi image mới được build/push, rollout và smoke/load test pass.
- product-reviews.
- recommendation.

Cần thêm non-root user vào final image hoặc chứng minh được một runtime UID an toàn trước khi bật `runAsNonRoot`.

### Giai đoạn enforce

1. Enforce trong namespace test riêng trước.
2. Chứng minh root/latest/missing-limits bị từ chối.
3. Chứng minh manifest hợp lệ vẫn được chấp nhận.
4. Chỉ chuyển namespace `techx-tf4` sang enforce khi:
   - Audit violation bằng 0.
   - Nguyên approve.
   - Service owner smoke test pass.
   - Có ngưỡng rollback theo SLO được thống nhất.

## 5. Safety và rollback

### 5.1. Rollback workload

- Revert commit Helm/GitOps hoặc rollback về Helm revision đã ghi nhận.
- Chỉ rollback option/batch gây lỗi, không gỡ các control không liên quan.
- Rollback nếu xuất hiện:
  - CrashLoopBackOff.
  - Init container fail.
  - Permission denied.
  - Smoke test fail.
  - Error rate/latency/restart vượt ngưỡng SLO đã thống nhất.
- Không sửa Pod trực tiếp vì controller sẽ tạo lại theo template.

### 5.2. Rollback admission

- Đổi namespace label từ `enforce` về `audit` để ngừng Deny nhưng vẫn giữ warning/audit.
- Nếu cần, chỉ remove enforce binding gây vấn đề thông qua source of truth.
- Không tạo exception rộng cho cả namespace nếu chỉ một workload bị false positive.
- Exception phải có workload, rule, lý do, owner, approval và thời hạn.
- Không xóa toàn bộ policy như phương án rollback đầu tiên.

## 6. Kết quả verification

### 6.1. Đã pass

- `helm lint techx-corp-chart`: pass; chỉ có thông báo optional về chart icon.
- Helm render application: pass.
- Helm render observability: pass trong vòng kiểm tra đầu tiên.
- `git diff --check`: pass.
- Không còn BusyBox `latest`/không tag trong chart hoặc application render.
- Chỉ manifest negative test `deny-latest.yaml` còn chứa `busybox:latest` theo chủ đích.
- Client dry-run parse thành công cả bốn Deployment test.
- `kubectl create --dry-run=client` parse thành công ba policy và sáu binding.
- Kubernetes server version hỗ trợ `admissionregistration.k8s.io/v1` VAP.
- Helm render sau remediation `load-generator` có UID/GID 10001, `runAsNonRoot`, APE=false, drop ALL và RuntimeDefault seccomp.

### 6.2. Chưa thể hoàn thành do RBAC và approval

- Server-side compile/dry-run CEL của VAP.
- Apply policy hoặc binding.
- Label namespace audit/enforce.
- Thu evidence mentor thấy manifest sai bị reject.
- Deploy thay đổi workload.
- Verify runtime pod specs sau rollout.
- Service smoke test và theo dõi SLO.
- Docker image build test cho `load-generator`; Docker client có nhưng Docker Desktop Linux daemon không chạy.

Role hiện tại trả về `no` cho các quyền:

- Get/Create ValidatingAdmissionPolicy.
- Create ValidatingAdmissionPolicyBinding.
- Patch Namespace.

Role cũng trả lỗi `Forbidden` khi list CRD, VAP, binding và validating webhook. Cần platform reviewer/operator có quyền phù hợp.

## 7. Nhật ký đầy đủ các lệnh đã chạy

Các lệnh dưới đây đã được chạy trong quá trình thực hiện. Không lệnh nào thay đổi cluster.

### 7.1. Kiểm tra workspace

```powershell
Get-ChildItem -Force
```

Lần chạy trong sandbox thất bại trước khi process được khởi tạo với Windows error 1312. Yêu cầu escalation đầu tiên bị từ chối. Sau đó cùng lệnh read-only được approve và chạy thành công, xác định repository là `tf4-phase3-repo`.

### 7.2. Inventory repository

```powershell
Get-ChildItem -Path D:\XBrain_phase3 -Filter AGENTS.md -Recurse -Force
Get-ChildItem -Force
git status --short
rg --files -g '*.yaml' -g '*.yml' -g '*.json' -g '*.tf' -g '*.md' -g '!**/.git/**'
```

Kết quả:

- Không có `AGENTS.md`.
- Repository ban đầu sạch.
- Xác định Helm chart và Directive #5.

### 7.3. Đọc directive và source chính

```powershell
Get-Content -Raw mandates\MANDATE-05-runtime-hardening.md
Get-Content -Raw techx-corp-chart\Chart.yaml
Get-Content -Raw techx-corp-chart\values.yaml
Get-Content -Raw techx-corp-chart\values.schema.json
Get-Content -Raw techx-corp-chart\templates\component.yaml
Get-Content -Raw techx-corp-chart\templates\component-pvcs.yaml
Get-Content -Raw deploy\values-observability.yaml
Get-Content -Raw deploy\values-flagd-sync.yaml
Get-Content -Raw deploy\values-app-stamp.yaml
Get-Content -Raw deploy\values-aio-llm.yaml
```

Kết quả: xác nhận `default.securityContext` đang rỗng và Directive #5 yêu cầu admission reject tự động.

### 7.4. Kiểm tra chart, tool và kube context

```powershell
rg -n 'define "techx-corp.deployment"|securityContext|podSecurityContext|initContainers|sidecarContainers|image:.*latest|resources:' techx-corp-chart deploy
rg -n '^  [a-zA-Z0-9-]+:$|enabled: true|imageOverride:|image:' techx-corp-chart\values.yaml
Get-ChildItem techx-corp-chart\templates -Force
helm version --short
kubectl version --client
kubectl config current-context
```

Kết quả:

- Helm v4.2.1.
- kubectl v1.34.1.
- Context là `techx-tf4-cluster`.

### 7.5. Thu thập runtime và admission inventory

```powershell
kubectl -n techx-tf4 get deploy,statefulset,daemonset,job,cronjob -o wide
kubectl -n techx-tf4 get pods -o jsonpath='{range .items[*]}{range .spec.containers[*]}{..metadata.name}{"\t"}{.name}{"\t"}{.image}{"\t"}{.securityContext}{"\t"}{.resources}{"\n"}{end}{end}'
kubectl -n techx-tf4 get pods -o jsonpath='{range .items[*]}{range .spec.initContainers[*]}{..metadata.name}{"\t"}{.name}{"\t"}{.image}{"\t"}{.securityContext}{"\t"}{.resources}{"\n"}{end}{end}'
kubectl get crd
kubectl get validatingadmissionpolicies,validatingadmissionpolicybindings
kubectl get validatingwebhookconfigurations
```

Kết quả:

- Đọc workload trong namespace thành công.
- Các thao tác đọc admission/CRD ở cluster scope bị `Forbidden`.

### 7.6. Research Dockerfile USER và Helm template

```powershell
rg --files -g 'Dockerfile*' -g '!**/node_modules/**'
rg -n '^(USER|FROM)|user:' techx-corp-platform -g 'Dockerfile*' -g 'docker-compose*.yml'
Get-Content techx-corp-chart\templates\_objects.tpl -TotalCount 175
Get-Content techx-corp-chart\values.yaml | Select-Object -Skip 470 -First 230
Get-Content techx-corp-chart\values.yaml | Select-Object -Skip 870 -First 310
kubectl version
```

Kết quả:

- Xác định các final image có bằng chứng non-root.
- Server version là v1.34.9-eks-8f14419.

### 7.7. Lấy digest BusyBox đang chạy

```powershell
kubectl -n techx-tf4 get pods -o jsonpath='{range .items[*]}{range .status.initContainerStatuses[*]}{..metadata.name}{"\t"}{.name}{"\t"}{.image}{"\t"}{.imageID}{"\n"}{end}{end}'
```

Kết quả: toàn bộ BusyBox init instance resolve về digest `fd8d...a9715d`.

### 7.8. Kiểm tra vị trí patch

```powershell
rg -n -A35 '^  (accounting|checkout|fraud-detection|product-catalog|shipping):' techx-corp-chart\values.yaml
rg -n 'busybox(:latest)?$|busybox@|securityContext:' techx-corp-chart\values.yaml
Get-Content techx-corp-chart\values.yaml | Select-Object -Skip 188 -First 18
Get-Content techx-corp-chart\values.yaml | Select-Object -Skip 340 -First 18
Get-Content techx-corp-chart\values.yaml | Select-Object -Skip 438 -First 18
Get-Content techx-corp-chart\values.yaml | Select-Object -Skip 758 -First 12
Get-Content techx-corp-chart\values.yaml | Select-Object -Skip 896 -First 12
```

Có một lần `apply_patch` không khớp context và không thay đổi file. Sau khi đọc đúng vị trí, patch được áp lại bằng anchor hẹp hơn và thành công.

### 7.9. Verification local lần thứ nhất

```powershell
helm lint techx-corp-chart
helm template techx-app techx-corp-chart -n techx-tf4 -f deploy\values-app-stamp.yaml --set opentelemetry-collector.enabled=false --set jaeger.enabled=false --set prometheus.enabled=false --set grafana.enabled=false --set opensearch.enabled=false --set metrics-server.enabled=false > $env:TEMP\cdo08-app-rendered.yaml
helm template techx-observability techx-corp-chart -n techx-observability -f deploy\values-observability.yaml > $env:TEMP\cdo08-observability-rendered.yaml
rg -n 'image:.*(:latest|image: busybox$)|allowPrivilegeEscalation|runAsNonRoot|drop:|type: RuntimeDefault' $env:TEMP\cdo08-app-rendered.yaml
kubectl apply --dry-run=client --validate=false -f deploy\admission\runtime-hardening-policy.yaml
kubectl apply --dry-run=client --validate=false -f deploy\admission\runtime-hardening-audit-bindings.yaml
kubectl apply --dry-run=client --validate=false -f deploy\admission\runtime-hardening-enforce-bindings.yaml
kubectl apply --dry-run=client --validate=false -f deploy\admission\tests\deny-root.yaml
kubectl apply --dry-run=client --validate=false -f deploy\admission\tests\deny-latest.yaml
kubectl apply --dry-run=client --validate=false -f deploy\admission\tests\deny-missing-limits.yaml
kubectl apply --dry-run=client --validate=false -f deploy\admission\tests\allow-valid.yaml
```

Kết quả:

- Helm lint và render pass.
- Các Deployment test pass client dry-run.
- `kubectl apply --dry-run=client` vẫn thử đọc VAP/binding hiện có trên cluster và bị RBAC `Forbidden`.
- Không resource nào được persist.

### 7.10. Kiểm tra cuối

```powershell
git diff --check
helm lint techx-corp-chart
helm template techx-app techx-corp-chart -n techx-tf4 -f deploy\values-app-stamp.yaml --set opentelemetry-collector.enabled=false --set jaeger.enabled=false --set prometheus.enabled=false --set grafana.enabled=false --set opensearch.enabled=false --set metrics-server.enabled=false > $env:TEMP\cdo08-app-rendered-final.yaml
rg -n 'image:.*:latest|image: busybox$' techx-corp-chart deploy $env:TEMP\cdo08-app-rendered-final.yaml
rg -n 'securityContext: \{\}|resources: \{\}' techx-corp-chart\values.yaml
kubectl auth can-i get validatingadmissionpolicies.admissionregistration.k8s.io
kubectl auth can-i create validatingadmissionpolicies.admissionregistration.k8s.io
kubectl auth can-i create validatingadmissionpolicybindings.admissionregistration.k8s.io
kubectl auth can-i patch namespace
git status --short
git diff --stat
```

Kết quả:

- Lint và diff check pass.
- Chỉ negative test `deny-latest.yaml` match floating-tag search.
- Cả bốn kiểm tra quyền đều trả `no`.

### 7.11. Verification sau khi tạo báo cáo

```powershell
git diff --check
helm lint techx-corp-chart
kubectl create --dry-run=client --validate=false -f deploy\admission\runtime-hardening-policy.yaml -o name
kubectl create --dry-run=client --validate=false -f deploy\admission\runtime-hardening-audit-bindings.yaml -o name
kubectl create --dry-run=client --validate=false -f deploy\admission\runtime-hardening-enforce-bindings.yaml -o name
git status --short
git diff --stat
```

Kết quả:

- Tất cả lệnh exit thành công.
- Client parse đúng ba VAP và sáu binding.
- Git chỉ ghi nhận các file thuộc task này.
- Các thông báo LF-to-CRLF là warning chuẩn hóa line ending của Git, không phải validation failure.

### 7.12. Remediation và verification source của load-generator

Các file được đọc trước khi sửa:

```powershell
Get-Content -Raw techx-corp-platform\src\load-generator\Dockerfile
rg -n 'WORKDIR|ENTRYPOINT|CMD|open\(|write|report|csv|html|/tmp|LOCUST|requirements|COPY' techx-corp-platform\src\load-generator techx-corp-chart\values.yaml -g '!**/__pycache__/**'
```

Lý do: xác định final image chưa có `USER`, application working directory và các write path có thể liên quan trước khi chọn UID/GID.

Sau khi sửa Dockerfile và Helm values, đã chạy:

```powershell
git diff --check
helm lint techx-corp-chart
helm template techx-app techx-corp-chart -n techx-tf4 -f deploy\values-app-stamp.yaml --set opentelemetry-collector.enabled=false --set jaeger.enabled=false --set prometheus.enabled=false --set grafana.enabled=false --set opensearch.enabled=false --set metrics-server.enabled=false > $env:TEMP\cdo08-load-generator-rendered.yaml
Select-String -Path $env:TEMP\cdo08-load-generator-rendered.yaml -Pattern 'name: load-generator' -Context 0,55
docker version --format '{{.Client.Version}}'
```

Kết quả:

- `git diff --check`: pass.
- Helm lint: pass.
- Helm render: pass và chứa securityContext đã merge.
- Docker client version: 29.4.0.
- Docker daemon check thất bại với `failed to connect to the docker API ... dockerDesktopLinuxEngine`; vì vậy chưa chạy được image build/smoke test local.

Giới hạn và việc cần làm:

- Cần khởi động Docker Desktop hoặc dùng CI builder đã được phê duyệt.
- Build/push phải dùng tag mới, không ghi đè `8340af1-load-generator` đang chạy.
- Sau rollout phải xác minh lại bằng `kubectl exec deployment/load-generator -- id`; expected UID/GID là 10001, không phải 0.

## 8. Danh sách file đã thay đổi hoặc tạo mới

- `techx-corp-chart/values.yaml`.
- `techx-corp-chart/templates/_objects.tpl`.
- `techx-corp-platform/src/load-generator/Dockerfile`.
- `deploy/admission/runtime-hardening-policy.yaml`.
- `deploy/admission/runtime-hardening-audit-bindings.yaml`.
- `deploy/admission/runtime-hardening-enforce-bindings.yaml`.
- `deploy/admission/tests/deny-root.yaml`.
- `deploy/admission/tests/deny-latest.yaml`.
- `deploy/admission/tests/deny-missing-limits.yaml`.
- `deploy/admission/tests/allow-valid.yaml`.
- `deploy/admission/README.md`.
- `docs/audit/adr/014-native-validating-admission-policy-runtime-hardening.md`.
- `docs/cdo08/week2/CDO08-SEC-04-IMPLEMENTATION-REPORT.md`.

Các chỉnh sửa được thực hiện bằng workspace patch mechanism. Không chạy lệnh filesystem/Git mang tính phá hủy.

## 9. Việc bắt buộc còn lại để đóng ticket

1. Nguyên review Helm diff, CEL, `failurePolicy`, namespace selector và ADR.
2. Platform operator có quyền VAP chạy server-side dry-run và apply audit-only policy/binding.
3. Service owner deploy và smoke-test từng batch trong khi theo dõi SLO.
4. Remediation các image trong exception list cho tới khi audit violation bằng 0.
5. Platform operator bật Deny trong namespace test riêng.
6. Mentor chạy ba invalid test và một valid control; attach API-server response vào Jira.
7. Sau approval, enforce namespace `techx-tf4`, verify runtime pod specs và attach smoke/SLO evidence.
8. Owner xác nhận acceptance criteria; PM cập nhật backlog status.

## 10. Quyền đang thiếu và nội dung đề nghị bổ sung

### 10.1. Vì sao cần bổ sung quyền

ValidatingAdmissionPolicy và ValidatingAdmissionPolicyBinding là tài nguyên ở cluster scope, không thuộc riêng namespace `techx-tf4`. Role hiện tại `TF4-SecReliabilityReadOnlyAudit` chỉ đọc được workload trong namespace và không có quyền đọc hoặc quản lý hai loại tài nguyên admission này.

Nếu không bổ sung quyền hoặc không có platform operator thực hiện thay:

- Không xác nhận được cluster đã có Kyverno, Gatekeeper hoặc admission policy nào khác hay chưa.
- Không chạy được server-side dry-run để API server compile và kiểm tra CEL expression.
- Không apply được audit binding.
- Không chuyển namespace test sang enforce.
- Không tạo được evidence mentor apply manifest sai và bị admission layer từ chối.
- Không thể hoàn thành acceptance criterion và Definition of Done ở phần admission.

Các lỗi thực tế đã gặp:

```text
cannot list resource "customresourcedefinitions" at the cluster scope
cannot list resource "validatingadmissionpolicies" at the cluster scope
cannot list resource "validatingadmissionpolicybindings" at the cluster scope
cannot list resource "validatingwebhookconfigurations" at the cluster scope
```

Kết quả `kubectl auth can-i`:

```text
get validatingadmissionpolicies.admissionregistration.k8s.io: no
create validatingadmissionpolicies.admissionregistration.k8s.io: no
create validatingadmissionpolicybindings.admissionregistration.k8s.io: no
patch namespace: no
create pods/exec trong namespace techx-tf4: no
```

Quyền `pods/exec` được kiểm tra bằng:

```bash
kubectl auth can-i create pods/exec -n techx-tf4
```

Kết quả mới nhất:

```text
no
```

Ảnh hưởng: owner không thể dùng `kubectl exec deployment/<name> -- id` để xác minh UID/GID thực tế cho toàn bộ workload. Evidence `load-generator` đã thu được ở lần exec trước vẫn được giữ, nhưng các workload khác phải dùng Pod spec, Dockerfile/image metadata hoặc nhờ service/platform owner thực hiện runtime UID verification.

### 10.2. Quyền read-only tối thiểu để research và verify

Đề nghị cấp trước các quyền chỉ đọc sau:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: tf4-runtime-hardening-admission-audit
rules:
  - apiGroups: ["admissionregistration.k8s.io"]
    resources:
      - validatingadmissionpolicies
      - validatingadmissionpolicybindings
      - validatingwebhookconfigurations
      - mutatingwebhookconfigurations
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apiextensions.k8s.io"]
    resources: ["customresourcedefinitions"]
    verbs: ["get", "list", "watch"]
```

Lý do cần từng nhóm quyền:

- Read VAP/binding: kiểm tra policy nào đã tồn tại, tránh trùng hoặc xung đột.
- Read validating/mutating webhook: kiểm tra admission engine hiện có và thứ tự/tác động admission.
- Read CRD: xác định cluster có Kyverno hoặc Gatekeeper hay không.
- `watch` không bắt buộc nếu platform team muốn tối thiểu hơn; `get/list` là đủ cho inventory một lần.

### 10.3. Quyền thay đổi admission đề nghị cấp tạm thời

Phương án ưu tiên là platform operator review rồi apply các file trong `deploy/admission/`. Nếu owner phải tự triển khai, đề nghị cấp quyền có thời hạn và thu hồi sau khi hoàn tất:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: tf4-runtime-hardening-admission-operator-temporary
rules:
  - apiGroups: ["admissionregistration.k8s.io"]
    resources:
      - validatingadmissionpolicies
      - validatingadmissionpolicybindings
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: [""]
    resources: ["namespaces"]
    verbs: ["get", "list", "patch", "update"]
```

Giải thích:

- `create`: tạo policy và binding lần đầu.
- `update/patch`: sửa policy, đổi binding hoặc rollback từ enforce về audit qua source-of-truth.
- `delete`: rollback riêng binding/policy bị lỗi. Nếu platform team không muốn cấp `delete`, platform operator phải chịu trách nhiệm rollback thay.
- `get/list/watch`: kiểm tra trạng thái trước và sau apply.
- `patch/update namespaces`: thêm hoặc đổi label `security.techx.io/runtime-hardening` cho namespace test và namespace đích.

Không đề nghị quyền quản lý toàn bộ CRD, webhook hoặc resource Kubernetes khác. Không đề nghị `cluster-admin`.

Nếu reviewer yêu cầu owner tự xác minh UID runtime, đề nghị cấp tạm trong riêng namespace `techx-tf4`:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: tf4-runtime-uid-verifier-temporary
  namespace: techx-tf4
rules:
  - apiGroups: [""]
    resources: ["pods/exec"]
    verbs: ["create"]
```

Lý do chỉ xin `create` trên `pods/exec`: Kubernetes dùng verb này để mở exec subresource. Đây là quyền nhạy cảm vì có thể chạy command trong container, nên chỉ cấp có thời hạn, giới hạn namespace và thu hồi sau khi hoàn tất evidence. Phương án ưu tiên vẫn là service/platform owner chạy lệnh `id` và gửi output thay vì cấp quyền lâu dài cho role audit.

### 10.4. Giới hạn phạm vi namespace label

Kubernetes RBAC tiêu chuẩn không giới hạn quyền patch Namespace theo tên bằng `resourceNames` một cách hữu ích cho thao tác label khi request dùng collection/path khác nhau. Vì vậy lựa chọn an toàn hơn là:

1. Platform operator tự label namespace test và `techx-tf4`; hoặc
2. Dùng admission guard riêng để giới hạn label; hoặc
3. Cấp quyền tạm trong rollout window rồi thu hồi ngay sau verification.

Không nên cấp quyền patch mọi Namespace lâu dài cho role audit.

### 10.5. Mẫu nội dung gửi platform/IAM team

```text
Subject: Request temporary admission-policy access for CDO08-SEC-04

Context:
CDO08-SEC-04 / Directive #5 yêu cầu admission layer reject manifest chạy root,
dùng latest hoặc thiếu resources. Target cluster là techx-tf4-cluster,
Kubernetes v1.34.9.

Current blocker:
Role AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit không có quyền get/list/create
ValidatingAdmissionPolicy, ValidatingAdmissionPolicyBinding, không đọc được CRD/webhook
và không patch được namespace label. Các lệnh kubectl trả Forbidden/no.

Requested access:
1. Permanent/read-only: get/list (watch nếu được) cho VAP, VAP binding,
   validating/mutating webhook và CRD để inventory/verify.
2. Temporary during approved rollout: get/list/create/update/patch/delete cho VAP và
   VAP binding; patch namespace label cho namespace test và techx-tf4.

Preferred safer alternative:
Platform operator review và trực tiếp chạy server-side dry-run/apply/rollback thay owner.
Không yêu cầu cluster-admin.

Source manifests:
- deploy/admission/runtime-hardening-policy.yaml
- deploy/admission/runtime-hardening-audit-bindings.yaml
- deploy/admission/runtime-hardening-enforce-bindings.yaml

Rollback:
Đổi namespace label từ enforce về audit hoặc remove riêng enforce binding.
```

### 10.6. Lệnh kiểm tra sau khi được bổ sung quyền

```powershell
kubectl auth can-i list customresourcedefinitions.apiextensions.k8s.io
kubectl auth can-i list validatingadmissionpolicies.admissionregistration.k8s.io
kubectl auth can-i create validatingadmissionpolicies.admissionregistration.k8s.io
kubectl auth can-i create validatingadmissionpolicybindings.admissionregistration.k8s.io
kubectl auth can-i patch namespaces
kubectl auth can-i create pods/exec -n techx-tf4
```

Chỉ tiếp tục rollout nếu kết quả đúng với phương án đã được approve. Nếu chỉ được cấp read-only, owner chỉ inventory/verify; platform operator vẫn phải apply.

## 11. Mẫu cập nhật Jira

```text
CDO08-SEC-04 update

Đã hoàn thành trong source:
- Thêm baseline APE=false, drop ALL và RuntimeDefault seccomp.
- Pin BusyBox init image bằng digest runtime hiện tại.
- Bật runAsNonRoot cho batch image đã xác minh.
- Thêm native ValidatingAdmissionPolicy, audit/enforce bindings và test manifests.
- Helm lint/render và client manifest parsing đều pass.

Runtime/admission rollout:
- Chưa rollout do role TF4-SecReliabilityReadOnlyAudit không có quyền VAP/binding/patch namespace.
- Đang chờ Nguyên review và platform operator thực hiện server-side dry-run/audit rollout.

Exceptions cần xử lý:
- ad, cart, currency, email, flagd, llm, load-generator, postgresql,
  product-reviews, recommendation.

Safety:
- Không bật readOnlyRootFilesystem global.
- Rollout theo batch và rollback từng option nếu smoke test/SLO fail.
- Admission đi theo audit → fix workload → enforce namespace test → enforce production.
```
