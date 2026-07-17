# Báo cáo hiện trạng implementation GitOps, Argo CD và CI/CD

> **Phạm vi bằng chứng:** đây là báo cáo hiện trạng implementation đang có trong hai repository: `tf4-phase3-repo` (source) và `tf4-phase3-gitops-manifests` (GitOps), không phải implementation plan hay setup guide. Báo cáo đối chiếu workflow, manifest, values và Terraform đã tồn tại; nó không khẳng định EKS, Argo CD, ECR hay AWS đang healthy ở runtime.

## 1. Tổng quan và ranh giới trách nhiệm


| Repository                    | Vai trò thực tế                                                                                                                                                                  |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tf4-phase3-repo`             | Application source, Docker build context, Helm chart `techx-corp-chart`, Terraform infrastructure và GitHub Actions cho CI/build/promotion.                                      |
| `tf4-phase3-gitops-manifests` | Production desired state: Argo CD bootstrap/Application/AppProject, production Helm values, image revisions, raw Kubernetes resources, External Secrets và GitOps PR validation. |


Mô hình là **two-repository GitOps**:

- CI ở source repository build/push image và tạo GitOps promotion PR; không chạy direct Helm deployment.
- GitOps repository là source of truth cho revision được deploy vào production.
- Argo CD đọc GitOps revision đã merge và reconcile vào Kubernetes.

Safety model được ghi rõ tại `tf4-phase3-repo/.github/workflows/README.md:15-26`: Pull Request chỉ validation; không push image, `terraform apply`, `helm upgrade`, cấu hình kubeconfig hoặc deploy EKS. Cùng tài liệu xác nhận GitOps PR do platform owner review/merge và Argo CD deploy revision đã merge (`README.md:63-71`).

## 2. CI trong `tf4-phase3-repo`

### 2.1 Pull Request validation

Workflow `tf4-phase3-repo/.github/workflows/ci.yaml` chạy khi có Pull Request vào `main` hoặc `master` (`ci.yaml:1-5`). Job `changes` dùng `dorny/paths-filter` để phân loại thay đổi app/chart/deploy/Terraform/workflow/docs (`ci.yaml:20-58`), rồi conditionally chạy các gate sau:


| Gate                   | Điều kiện                                    | Kiểm tra thực tế                                                                                                                                                                   |
| ---------------------- | -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `yaml-check`           | App/chart/deploy/Terraform/workflow thay đổi | Parse YAML trong `.github`, `deploy`, `techx-corp-chart`, bỏ qua generated chart/template files (`ci.yaml:60-91`).                                                                 |
| `terraform-infra-plan` | `infra/terraform/**` thay đổi                | AWS OIDC plan role, `terraform fmt`, `init`, `validate`, `plan`, rồi upload `tfplan` artifact (`ci.yaml:93-135`).                                                                  |
| `helm-render`          | Chart/deploy/workflow thay đổi               | Build dependencies, lint chart, render observability và app release; assert Deployment resource requests/limits và HPA cho `frontend`, `checkout`, `currency` (`ci.yaml:137-218`). |
| `app-smoke-build`      | Application thay đổi                         | Docker Buildx smoke build cho `checkout` và `shipping`; `shipping` (Rust) được chọn để lỗi compile xuất hiện trước merge (`ci.yaml:220-246`).                                      |


### 2.2 Build, push ECR và promotion

`tf4-phase3-repo/.github/workflows/build-and-push.yaml` chạy khi push vào `main` có thay đổi application/chart/build script/workflow, hoặc bằng `workflow_dispatch` với danh sách service explicit (`build-and-push.yaml:1-20`).

1. **Chọn input:** job `changes` duy trì allowlist 19 service và xác định service source thay đổi; chart thay đổi được theo dõi riêng (`build-and-push.yaml:35-88`).
2. **Build/push:** job `build` assumes `AWS_GITHUB_ACTIONS_BUILD_ROLE_ARN` qua GitHub OIDC, login ECR, lấy `image_tag` là short Git SHA hoặc manual input, rồi tạo image repository `${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}` (`build-and-push.yaml:90-138`).
3. **Tag format:** `deploy/build-push-images.sh` build từng selected service bằng `docker buildx bake` (linux/amd64) và push `${IMAGE_NAME}:${DEMO_VERSION}-${SERVICE}` (`../tf4-phase3-repo/deploy/build-push-images.sh:15-23`). Ví dụ current desired tags: `8340af1-frontend`, `4526141-accounting`, `c16ecbe-product-reviews` trong [image-revisions.yaml](environments/production/image-revisions.yaml#L1-L58).
4. **Post-build evidence:** workflow gọi `aws ecr describe-images` cho từng pushed tag và lưu `image-digests.txt`; `build-metadata.json` cùng digest list được upload thành artifact (`build-and-push.yaml:152-187`).

### 2.3 Handoff từ source sang GitOps repository

Job `promote` là crossing point duy nhất được thấy trong workflow (`build-and-push.yaml:189-296`):

1. Tạo GitHub App token có quyền vào `TF4-Phase3-TechX/tf4-phase3-gitops-manifests`, rồi checkout target repo (`build-and-push.yaml:201-215`).
2. Với service đã build, script patch chính xác một `imageOverride.tag` cho từng service trong `environments/production/image-revisions.yaml`; mismatch số lần thay thế làm job fail (`build-and-push.yaml:235-248`).
3. Khi chart thay đổi, script patch cả **hai** `targetRevision` của source chart trong `argocd/root-resources/applications.yaml` bằng full 40-character source SHA; chỉ chấp nhận đúng hai lần thay thế (`build-and-push.yaml:250-260`).
4. Workflow tạo lại branch `promotion/production` từ GitOps `main`, push bằng `--force-with-lease`, rồi create/update GitOps PR. Nội dung PR nói rõ: **“Review and merge to let Argo CD deploy this release.”** (`build-and-push.yaml:217-296`).

Vì vậy, build thành công **không trực tiếp deploy production**. Human review + merge GitOps PR là gate trước Argo CD reconciliation.

### 2.4 Infrastructure apply

Workflow `tf4-phase3-repo/.github/workflows/terraform-apply.yaml` chạy khi `infra/terraform/**` thay đổi trên `main` (`terraform-apply.yaml:1-16`). Sau khi assumes Terraform apply OIDC role, workflow có thể sync Alertmanager Slack webhook sang Secrets Manager và security webhook sang SSM (`terraform-apply.yaml:65-85`), sau đó chạy `terraform fmt`, `init`, `validate`, `apply -auto-approve` và in outputs (`terraform-apply.yaml:87-107`).

Terraform ownership cho ESO chỉ là AWS IRSA identity: `infra/terraform/eso-irsa.tf:1-35` tạo policy đọc `techx/tf4/*` và role trust `external-secrets:external-secrets`; controller ESO vẫn được Argo CD deploy.

## 3. GitOps repository Pull Request validation

Workflow [`.github/workflows/validate.yaml`](.github/workflows/validate.yaml#L1-L54) chạy trên Pull Request vào `main` và:

1. cài PyYAML, chạy [`scripts/validate.py`](scripts/validate.py#L1-L64);
2. đọc source-chart revision được cấu hình trong Argo CD Applications;
3. checkout `tf4-phase3-repo` đúng revision đó;
4. Helm lint/render `techx-corp` với app/flag/image values và render `techx-observability` với observability/Alertmanager values.

Validator custom enforce các invariant sau:

- tất cả Application chart sources phải dùng cùng một immutable full SHA gồm 40 hex characters ([`validate.py:20-28`](scripts/validate.py#L20-L28));
- không có duplicate `(apiVersion, kind, namespace, name)` giữa YAML manifests ([`validate.py:30-42`](scripts/validate.py#L30-L42));
- chặn potential plaintext credential ngoài `all-secrets.yaml` ([`validate.py:43-44`](scripts/validate.py#L43-L44));
- chặn xóa manifest chứa PVC/PV/Service/Namespace/CRD trừ reviewed override riêng ([`validate.py:46-56`](scripts/validate.py#L46-L56)).

## 4. Argo CD implementation thực tế

### 4.1 Bootstrap và AppProject

`root-bootstrap` là Application app-of-apps: nó đọc `argocd/root-resources` trong GitOps `main`, deploy vào namespace `argocd`, với `selfHeal: true` và `prune: false` ([`argocd/bootstrap/root.yaml`](argocd/bootstrap/root.yaml#L1-L18)). `prune: false` nghĩa là config hiện tại không yêu cầu Argo CD tự xóa resource không còn trong Git revision.

`techx-production` AppProject giới hạn:

- source repositories: source repo, GitOps repo và `https://charts.external-secrets.io`;
- destinations: `techx-tf4`, `techx-observability`, `external-secrets`, `argocd`, `kube-system`, cùng in-cluster server;
- cluster/namespace resource allowlists;
- orphan resource warning, với Helm release Secret exclusions.

Chi tiết policy nằm tại [`argocd/root-resources/techx-production.yaml`](argocd/root-resources/techx-production.yaml#L1-L92).

### 4.2 Ordered sync waves

[`applications.yaml`](argocd/root-resources/applications.yaml#L1-L141) định nghĩa năm child Applications, cùng pattern `automated: { prune: false, selfHeal: true }`:


| Sync wave | Application           | Source / mục đích                                         | Destination namespace |
| ---------: | --------------------- | --------------------------------------------------------- | --------------------- |
| `-2`      | `external-secrets`    | External Secrets Helm chart `0.9.20`, `installCRDs: true` | `external-secrets`    |
| `-1`      | `platform-secrets`    | GitOps `platform/secrets`                                 | `techx-tf4`           |
| `0`       | `techx-raw`           | GitOps `environments/production/raw`                      | `techx-tf4`           |
| `1`       | `techx-observability` | Helm chart + GitOps observability values                  | `techx-observability` |
| `2`       | `techx-corp`          | Helm chart + GitOps app/flag/image values                 | `techx-tf4`           |


### 4.3 Multi-source Helm releases và image pinning

Hai Applications ở wave 1/2 đều dùng Argo CD multi-source:

- **Chart source:** `tf4-phase3-repo`, path `techx-corp-chart`, pinned full SHA `2e98734c73b31c08cf172f630afb3895ea893a35`.
- **Values source:** GitOps repository tại `main`, alias `values-source`.
- `techx-observability` dùng `observability-values.yaml`, `alertmanager-routing-values.yaml` ([`applications.yaml:70-101`](argocd/root-resources/applications.yaml#L70-L101)).
- `techx-corp` dùng `app-values.yaml`, `flagd-values.yaml`, `image-revisions.yaml` ([`applications.yaml:103-141`](argocd/root-resources/applications.yaml#L103-L141)).

Cả hai có `FailOnSharedResource=true` và `ApplyOutOfSyncOnly=true`. `techx-corp` ignore `/spec/replicas` của Deployment, phù hợp với việc HPA sở hữu replica count.

Promotion cập nhật [image-revisions.yaml](environments/production/image-revisions.yaml#L1-L58). Helm chart dùng `imageOverride.tag` khi có; nếu không có mới fallback sang default tag cộng component name (`tf4-phase3-repo/techx-corp-chart/templates/_objects.tpl:66-67`). Điều này nối trực tiếp GitOps promotion tag với rendered workload image.

## 5. Secrets, network và observability

### 5.1 External Secrets Operator

Wave `-2` cài operator. Wave `-1` khai báo `ClusterSecretStore aws-secretsmanager`, provider AWS Secrets Manager tại `us-east-1`, xác thực JWT qua ServiceAccount `external-secrets` trong namespace `external-secrets` ([`cluster-secret-store.yaml`](platform/secrets/cluster-secret-store.yaml#L1-L15)). Contract này khớp IRSA Terraform nêu ở phần 2.4.

[`all-secrets.yaml`](platform/secrets/all-secrets.yaml#L1-L103) khai báo năm `ExternalSecret`, tất cả refresh mỗi giờ và tạo target Secret theo `creationPolicy: Owner`:


| ExternalSecret             | Target Secret               | AWS Secrets Manager key  | Namespace             |
| -------------------------- | --------------------------- | ------------------------ | --------------------- |
| `postgres-db-secret`       | `postgres-db-credentials`   | `techx/tf4/postgres`     | `techx-tf4`           |
| `alertmanager-smtp-secret` | `alertmanager-smtp-auth`    | `techx/tf4/alertmanager` | `techx-observability` |
| `openai-api-secret`        | `openai-api-key`            | `techx/tf4/openai`       | `techx-tf4`           |
| `grafana-admin-secret`     | `grafana-admin-credentials` | `techx/tf4/grafana`      | `techx-observability` |
| `flagd-bearer-secret`      | `flagd-bearer-token`        | `techx/tf4/flagd`        | `techx-tf4`           |


### 5.2 Raw Kubernetes resources

Wave `0` deploy raw resources từ GitOps:

- internet-facing AWS ALB Ingress, target type `ip`, HTTP 80, `/` đến `frontend-proxy:8080` ([`raw/ingress.yaml`](environments/production/raw/ingress.yaml#L1-L22));
- `ResourceQuota`: 4 CPU requests, 8 CPU limits, 8Gi memory requests, 12Gi memory limits và 40 pods ([`raw/quota.yaml`](environments/production/raw/quota.yaml#L1-L10)).

### 5.3 Observability và cross-namespace integration

Wave `1` bật OpenTelemetry Collector, Jaeger, Prometheus, Grafana, OpenSearch và metrics-server, đồng thời tắt toàn bộ application components trong release observability ([`observability-values.yaml`](environments/production/observability-values.yaml#L1-L47)).

Wave `2` application values cấu hình `OTEL_COLLECTOR_NAME=otel-collector.techx-observability.svc.cluster.local`; `frontend-proxy` cũng tham chiếu Grafana/Jaeger bằng cross-namespace DNS ([`app-values.yaml`](environments/production/app-values.yaml#L12-L28)). Alertmanager được config receiver email qua Mailtrap và Slack webhook bằng file mount ([`alertmanager-routing-values.yaml`](environments/production/alertmanager-routing-values.yaml#L1-L23)).

## 6. Luồng end-to-end

```text
Developer Pull Request
  -> source ci.yaml: validation-only gates
  -> merge/push main
  -> build-and-push.yaml: detect affected services/chart
  -> GitHub OIDC -> build amd64 image -> push ECR -> verify digest
  -> GitHub App opens/updates GitOps promotion/production PR
  -> GitOps validate.yaml: static validation + chart-at-pinned-SHA Helm render
  -> platform owner reviews and merges GitOps PR
  -> Argo CD root-bootstrap observes GitOps main
  -> waves -2 ESO -> -1 secrets -> 0 raw resources -> 1 observability -> 2 application
  -> Kubernetes reconciles the desired revision
```

**Source-of-truth boundary:** source repository owns artifact/chart creation; GitOps repository owns the production image revision, chart revision pin and environment configuration. Rollback at GitOps layer is represented by reverting the relevant GitOps revision; direct deployment command không xuất hiện trong examined CI workflows.

