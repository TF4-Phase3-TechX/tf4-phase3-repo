# Helm Upgrade & Rollback Runbook

## 0. Task metadata

| Field            | Value                                                                                                              |
| ---------------- | ------------------------------------------------------------------------------------------------------------------ |
| Jira task        | `[Runtime] Xác minh Helm upgrade và rollback path`                                                                 |
| Owner / Assignee | Hoàng Nam                                                                                                          |
| Area / Ownership | Kubernetes Runtime Reliability                                                                                     |
| Pillar           | Reliability                                                                                                        |
| Priority         | P1                                                                                                                 |
| Reviewer         | Nguyên                                                                                                             |
| Output artifact  | `docs/cdo08/week1/helm-upgrade-rollback-runbook.md`                                                                |
| Current status   | Static runbook completed; kubectl runtime checks partially verified; Helm release evidence blocked by secrets RBAC |
| Runtime blocker  | `helm -n techx-tf4 list` bị `Forbidden` vì role audit chưa có quyền `list secrets` trong namespace `techx-tf4`     |
| Last updated     | 2026-07-08                                                                                                         |

## 1. Mục tiêu

Runbook này chuẩn hóa đường deploy và rollback bằng Helm cho hệ thống TechX trên EKS TF4. Mục tiêu là đảm bảo mọi thay đổi Tuần 2-3 đều có cách deploy, kiểm tra trạng thái, rollback và verify sau rollback rõ ràng trước khi tác động production/runtime thật.

Scope của task này là viết runbook và xác minh command bằng static evidence/local render. Không rollback production thật nếu chưa có approval.

## 2. Nguồn evidence

| Evidence                               | Ý nghĩa                                                                                                                                                    |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `docs/requirements/GETTING_STARTED.md` | Tài liệu deploy chính thức: build image vào ECR, chuẩn bị Helm repo/dependency, `helm upgrade --install`, kiểm tra pod và port-forward storefront          |
| `deploy/values-observability.yaml`     | Overlay bật observability stack và tắt app components theo comment hiện tại                                                                                |
| `deploy/values-flagd-sync.yaml`        | Overlay runtime cho flagd; cần luôn được include để không làm mất flagd path, nhưng central sync hiện đang deferred tới khi token/flagd args được xác nhận |
| `deploy/values-app-stamp.yaml`         | Overlay app-only khi observability tách riêng; trỏ OTLP về collector chung                                                                                 |
| `deploy/values-aio-llm.yaml`           | Optional overlay cho AIO/product-reviews khi dùng LLM thật                                                                                                 |
| `deploy/ingress.yaml`                  | Ingress ALB route `/` tới service `frontend-proxy:8080` trong namespace `techx-tf4`                                                                        |
| `techx-corp-chart/Chart.yaml`          | Chart name `techx-corp`, version `0.40.9`, appVersion `2.2.0`, dependencies gồm collector/jaeger/prometheus/grafana/opensearch                             |

Local render check đã chạy được với command baseline:

```bash
helm template techx-corp ./techx-corp-chart \
  --namespace techx-tf4 \
  --set default.image.repository=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp \
  -f deploy/values-observability.yaml \
  -f deploy/values-flagd-sync.yaml
```

Kết quả: command parse/render được local. Runtime `helm status/history`, `helm rollback` dry-run against cluster và `kubectl` checks chưa thực hiện được vì role audit chưa được map vào Kubernetes RBAC.

## 3. Biến chuẩn dùng trong runbook

Chạy từ root repo `tf4-phase3-repo/`.

```bash
export AWS_ACCOUNT_ID=511825856493
export AWS_REGION=us-east-1
export EKS_CLUSTER=techx-tf4-cluster
export NS=techx-tf4
export RELEASE=techx-corp
export CHART=./techx-corp-chart
export REG=${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/techx-corp
```

PowerShell equivalent:

```powershell
$Env:AWS_ACCOUNT_ID="511825856493"
$Env:AWS_REGION="us-east-1"
$Env:EKS_CLUSTER="techx-tf4-cluster"
$Env:NS="techx-tf4"
$Env:RELEASE="techx-corp"
$Env:CHART="./techx-corp-chart"
$Env:REG="$Env:AWS_ACCOUNT_ID.dkr.ecr.$Env:AWS_REGION.amazonaws.com/techx-corp"
```

## 4. Pre-flight checklist trước upgrade

| Check                           | Command                                    | Expected                                                       |
| ------------------------------- | ------------------------------------------ | -------------------------------------------------------------- |
| Đúng AWS identity               | `aws sts get-caller-identity`              | Account `511825856493`, role đúng theo account TF4             |
| Đúng kube context               | `kubectl config current-context`           | Context trỏ tới `techx-tf4-cluster`                            |
| Có quyền vào namespace app      | `kubectl -n $NS get pods`                  | Không bị `Unauthorized`/`Forbidden`                            |
| Namespace tồn tại hoặc tạo được | `kubectl get ns $NS`                       | Namespace tồn tại, hoặc Helm sẽ tạo khi upgrade/install        |
| Chart dependency sẵn sàng       | `helm dependency build ./techx-corp-chart` | Dependencies build thành công nếu chưa có sẵn                  |
| Registry đúng                   | `echo $REG`                                | Trỏ về ECR của TF4, không dùng seed registry làm runtime chính |
| Release hiện tại                | `helm -n $NS list`                         | Thấy release nếu đã deploy                                     |
| Release history                 | `helm -n $NS history $RELEASE`             | Có revision để rollback nếu upgrade lỗi                        |

Nếu `helm -n $NS list` báo thiếu quyền `secrets`, dừng ở phần Helm release evidence và yêu cầu bổ sung RBAC read-only cho Helm release secrets trong namespace `$NS`.

## 5. Helm upgrade command chuẩn

### 5.1 Baseline theo GETTING_STARTED

Command deploy baseline từ tài liệu chính thức:

```bash
helm upgrade --install $RELEASE $CHART -n $NS --create-namespace \
  --set default.image.repository=$REG \
  -f deploy/values-observability.yaml \
  -f deploy/values-flagd-sync.yaml
```

Quy tắc bắt buộc:

- Luôn include `deploy/values-flagd-sync.yaml` trong mọi lần upgrade để không làm mất flagd path.
- Nếu bật AIO LLM thật, chỉ thêm `-f deploy/values-aio-llm.yaml` sau khi secret `llm-api-key` đã tồn tại.
- Không sửa/tắt flagd hoặc hook đọc flag để né incident BTC.
- Không rollback production thật nếu chưa có approval từ reviewer/Tech Lead.

### 5.2 App-only khi observability đã tách riêng

`deploy/values-app-stamp.yaml` dùng khi observability stack chạy riêng và app chỉ cần trỏ OTLP về collector chung:

```bash
helm upgrade --install $RELEASE $CHART -n $NS --create-namespace \
  --set default.image.repository=$REG \
  -f deploy/values-app-stamp.yaml \
  -f deploy/values-flagd-sync.yaml
```

Lưu ý: `values-observability.yaml` hiện có comment bật observability và tắt toàn bộ app components. Vì vậy trước khi dùng command baseline cho môi trường thật, cần xác nhận với deploy owner profile nào đang là profile runtime chính: observability-only, app-only, hay full-stack overlay khác.

### 5.3 Dry-run/template trước khi upgrade thật

Local render không đụng cluster:

```bash
helm template $RELEASE $CHART -n $NS \
  --set default.image.repository=$REG \
  -f deploy/values-observability.yaml \
  -f deploy/values-flagd-sync.yaml
```

Server dry-run khi đã có quyền cluster:

```bash
helm upgrade --install $RELEASE $CHART -n $NS --create-namespace \
  --set default.image.repository=$REG \
  -f deploy/values-observability.yaml \
  -f deploy/values-flagd-sync.yaml \
  --dry-run
```

## 6. Check sau upgrade

| Mục cần check           | Command                                              | Expected                                                   |
| ----------------------- | ---------------------------------------------------- | ---------------------------------------------------------- |
| Helm release status     | `helm -n $NS status $RELEASE`                        | Status không fail/pending quá lâu                          |
| Helm history            | `helm -n $NS history $RELEASE`                       | Revision mới xuất hiện, previous revision còn để rollback  |
| Pod status              | `kubectl -n $NS get pods`                            | Critical pods Running/Ready                                |
| Deployment/StatefulSet  | `kubectl -n $NS get deploy,sts`                      | Desired/ready replicas hợp lý                              |
| Service                 | `kubectl -n $NS get svc`                             | `frontend-proxy` và service critical tồn tại               |
| Frontend-proxy endpoint | `kubectl -n $NS get endpoints frontend-proxy`        | Có endpoint backing pod ready                              |
| Events                  | `kubectl -n $NS get events --sort-by=.lastTimestamp` | Không có lỗi kéo dài như ImagePullBackOff/CrashLoopBackOff |

Frontend check qua port-forward nếu chưa dùng ALB:

```bash
kubectl -n $NS port-forward svc/frontend-proxy 8080:8080
curl -I http://localhost:8080
```

Nếu ALB đã expose theo `deploy/ingress.yaml`, kiểm tra URL ALB hiện tại:

```bash
curl -I http://<alb-dns-name>/
```

Checkout smoke check cần phối hợp với Quân/Quyết vì flow đặt order cần dữ liệu/cart/payment path cụ thể. Minimum check cho CDO08 là xác nhận frontend-proxy, frontend, checkout dependencies và stateful dependencies đều Ready trước khi xem upgrade thành công.

## 7. Rollback path

### 7.1 Xác định revision cần rollback

```bash
helm -n $NS history $RELEASE
helm -n $NS status $RELEASE
```

Chọn revision gần nhất trước lần upgrade lỗi. Không rollback mù nếu chưa xác định revision đang tốt.

### 7.2 Rollback command

```bash
helm -n $NS rollback $RELEASE <REVISION> --wait --timeout 10m
```

Nếu chỉ cần rollback về revision liền trước:

```bash
helm -n $NS rollback $RELEASE --wait --timeout 10m
```

Không thêm `--force` mặc định. Chỉ cân nhắc `--force` khi reviewer/Tech Lead approve vì có thể recreate resources và tăng downtime.

### 7.3 Verify sau rollback

| Check                              | Command                                           | Expected                                 |
| ---------------------------------- | ------------------------------------------------- | ---------------------------------------- |
| Release quay về revision mong muốn | `helm -n $NS history $RELEASE`                    | Revision rollback được đánh dấu deployed |
| Release healthy                    | `helm -n $NS status $RELEASE`                     | Không ở trạng thái failed/pending        |
| Pod hồi phục                       | `kubectl -n $NS get pods`                         | Critical pods Running/Ready              |
| Workload desired/ready             | `kubectl -n $NS get deploy,sts`                   | Ready khớp desired cho service critical  |
| Frontend reachable                 | `curl -I http://localhost:8080` hoặc ALB URL      | HTTP trả 200/3xx hợp lệ                  |
| Checkout path                      | Smoke test order hoặc kiểm tra trace/log checkout | Checkout flow không còn lỗi do rollout   |
| Observability                      | Grafana/Jaeger vẫn truy cập được                  | Metrics/traces tiếp tục có data          |
| flagd safety                       | Kiểm tra flagd pod/config hoặc checklist của Thuỷ | Không mất flagd sync/path sau rollback   |

## 8. Flagd safety requirement

Finding quan trọng: `GETTING_STARTED.md` nhấn mạnh mỗi lần `helm upgrade` phải ghép lại `-f deploy/values-flagd-sync.yaml`, nếu không flagd có thể rớt về cấu hình local và mất kết nối nguồn trung tâm.

Tuy nhiên `deploy/values-flagd-sync.yaml` hiện ghi central flag sync đang deferred vì attempt cũ dùng shell wrapper, trong khi image `ghcr.io/open-feature/flagd:v0.12.9` không có `/bin/sh`. Vì vậy:

- Vẫn include `deploy/values-flagd-sync.yaml` trong command để giữ overlay runtime hiện tại.
- Không tự uncomment central sync block nếu chưa test với Thuỷ.
- Trước upgrade có thay đổi flagd, cần Thuỷ review checklist flagd safety.
- Sau rollback, cần verify flagd không bị đổi source ngoài ý muốn và không tắt mechanism BTC dùng để bơm incident.

## 9. Runtime verification status

Status hiện tại: **Partially verified / Helm release evidence blocked by RBAC**.

Đã xác minh được phần static/local:

- Đọc `GETTING_STARTED.md`, `deploy/values-observability.yaml`, `deploy/values-flagd-sync.yaml`, `deploy/values-app-stamp.yaml`, `deploy/ingress.yaml`, `techx-corp-chart/Chart.yaml`.
- `helm template` local với `values-observability.yaml` + `values-flagd-sync.yaml` chạy được.

Đã xác minh được against cluster trong namespace `techx-tf4`:

- `kubectl -n techx-tf4 get pods` chạy được; workload app/runtime đang Running/Ready.
- `kubectl -n techx-tf4 get deploy,sts` chạy được; các deployment critical đang Ready.
- Runtime access hiện đủ để lấy pod/deployment evidence cho replica/probe tasks.

Helm release evidence hiện còn bị block:

Command:

```bash
helm -n techx-tf4 list
```

Error:

```text
Error: list: failed to list: secrets is forbidden: User "arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155/nam" cannot list resource "secrets" in API group "" in the namespace "techx-tf4"
```

Nguyên nhân: Helm v3 lưu release metadata trong Kubernetes Secret. Vì vậy `helm list`, `helm status`, `helm history` cần quyền đọc/list `secrets` trong namespace release.

Blocker hiện tại: role `TF4-SecReliabilityReadOnlyAudit` thiếu RBAC `get/list/watch secrets` trong namespace `techx-tf4`. Sau khi bổ sung quyền này, cần chạy lại:

```bash
helm -n techx-tf4 list
helm -n techx-tf4 status techx-corp
helm -n techx-tf4 history techx-corp
```

Không thực hiện rollback production thật nếu chưa có approval.

## 10. Findings và follow-up

| Priority | Finding                                                                          | Evidence                                                                                  | Impact                                                                       | Proposed follow-up                                                                     | Owner/dependency      |
| -------- | -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | --------------------- |
| P1       | Rollback path cần được chuẩn hóa trước Week 2-3                                  | Task yêu cầu; `GETTING_STARTED.md` có deploy command nhưng chưa có rollback runbook riêng | Deploy lỗi có thể kéo dài downtime nếu không biết revision/rollback/verify   | Dùng runbook này làm checklist bắt buộc cho PR/deploy thay đổi runtime                 | CDO08 / Nguyên review |
| P1       | `values-flagd-sync.yaml` phải luôn được include nhưng central sync đang deferred | `GETTING_STARTED.md`, `deploy/values-flagd-sync.yaml`                                     | Upgrade sai values có thể làm flagd rớt về local hoặc phá incident mechanism | Review flagd checklist với Thuỷ trước thay đổi flagd; không tự uncomment sync block    | Thuỷ / flagd owner    |
| P1       | Helm release evidence đang bị chặn bởi RBAC `secrets`                            | `helm -n techx-tf4 list` báo thiếu quyền `list secrets`                                   | Chưa thể xác minh release status/history để chọn revision rollback           | Bổ sung RBAC read-only `get/list/watch secrets` trong namespace `techx-tf4`            | CDO04/admin EKS       |
| P2       | `values-observability.yaml` hiện tắt app components                              | File comment và content trong `deploy/values-observability.yaml`                          | Dễ dùng nhầm overlay khi muốn deploy full app/runtime                        | Xác nhận deploy profile thực tế: observability-only, app-only, hoặc full-stack overlay | Deploy owner / Nguyên |

## 11. Definition of Done checklist

- [x] Runbook có upgrade command.
- [x] Runbook có rollback command.
- [x] Có `values-flagd-sync.yaml` requirement.
- [x] Có post-upgrade và post-rollback checks.
- [x] Có namespace/release/registry placeholders.
- [x] Có static evidence từ GETTING_STARTED/deploy files/chart.
- [x] Có local `helm template` evidence.
- [x] Runtime `kubectl` workload verification trong namespace `techx-tf4` đã chạy được.
- [ ] Helm release verification bằng `helm list/status/history` sau khi bổ sung RBAC đọc/list `secrets`.
