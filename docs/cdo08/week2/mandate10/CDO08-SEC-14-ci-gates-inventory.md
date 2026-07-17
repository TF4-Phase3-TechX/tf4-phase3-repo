# CDO08-SEC-14 - Inventory CI deploy gates hiện tại

## Phạm vi

Subtask: `Inventory current CI deploy gates and required checks`

Mục tiêu của tài liệu này là lập inventory các workflow/check hiện có và xác định check nào phải trở thành required gate cho Mandate 10. Scope phải cover cả source repo `tf4-phase3-repo` và GitOps repo `tf4-phase3-gitops-manifests`.

Đây chỉ là docs output, chưa cấu hình branch protection/ruleset và chưa tạo PR test fail. Các subtask sau phải chứng minh bằng PR đỏ bị chặn merge thật, không chỉ bằng screenshot workflow fail.

## Repo ownership và branch cần protect

| Khu vực | Repo / branch | Mục đích | Owner cần xác nhận | Target cần protect |
|---|---|---|---|---|
| Source repository | `TF4-Phase3-TechX/tf4-phase3-repo` / `main` | Source code, Helm chart, Terraform, CI workflows | `tf4-leads`; CDO08 SEC-14 owner: Nhân | Protect `main` với PR review và required status checks |
| GitOps deploy path | `TF4-Phase3-TechX/tf4-phase3-gitops-manifests` / `main` | Target của promotion PR do `build-and-push.yaml` tạo để deploy qua Argo CD | `@TF4-Phase3-TechX/platform-owners` theo `CODEOWNERS`; GitOps/platform owner cần xác nhận | Protect GitOps target branch với PR review và required promotion/deploy checks |

Ghi chú:

- `build-and-push.yaml` tạo hoặc cập nhật GitOps promotion PR từ branch `promotion/production` vào GitOps `main`.
- GitOps repo hiện có branch remote `origin/promotion/production`; target deploy/promotion quan sát được là PR vào `main`.
- Nếu GitOps repo dùng deploy branch khác ở runtime, cần thay `main` bằng branch thực tế trong evidence.
- Required scope không dừng ở source repo. Promotion/deploy PR vào GitOps repo cũng phải bị chặn nếu validation fail.

## Inventory workflow hiện có

| Workflow | Trigger | Jobs hiện tại | Vai trò hiện tại trong delivery |
|---|---|---|---|
| `.github/workflows/ci.yaml` | `pull_request` vào `main` hoặc `master` | `Detect changed areas`; `YAML parse check`; `Terraform infra plan`; `Helm lint and render`; `Docker smoke build checkout + shipping` | Candidate pre-merge PR gate chính cho source repo |
| `.github/workflows/build-and-push.yaml` | `push` vào `main` khi đổi app/chart/build script/workflow; manual `workflow_dispatch` | `Select images to build`; `Build and push app images`; `Open GitOps promotion PR` | Build/push sau merge và tạo GitOps promotion PR |
| `.github/workflows/terraform-apply.yaml` | `push` vào `main` khi đổi `infra/terraform/**` hoặc workflow | `Detect Terraform changes`; `Terraform apply infra` | Apply infra sau merge |

## Inventory GitOps workflow hiện có

Repo GitOps local đã được kiểm tra tại `TF4-Phase3-TechX/tf4-phase3-gitops-manifests`.

| Workflow | Trigger | Jobs/check hiện tại | Vai trò hiện tại trong delivery |
|---|---|---|---|
| `.github/workflows/validate.yaml` (`GitOps Manifest Validation`) | `pull_request` vào `main` | `validate` job: checkout config repo, cài PyYAML, chạy `python scripts/validate.py`, đọc deployed chart revision, checkout source chart, Helm lint/render production releases | Pre-merge validation gate cho GitOps promotion/deploy PR |

GitOps manifest paths chính:

- `argocd/root-resources/applications.yaml`
- `argocd/root-resources/techx-production.yaml`
- `environments/production/app-values.yaml`
- `environments/production/flagd-values.yaml`
- `environments/production/image-revisions.yaml`
- `environments/production/observability-values.yaml`
- `environments/production/alertmanager-routing-values.yaml`
- `platform/secrets/*.yaml`

## Bảng current checks vs required gates

| Check / gate | Hiện trạng trong repo | Có nên required? | Trạng thái hiện tại | Ghi chú |
|---|---|---:|---|---|
| YAML parse | `ci.yaml` job `YAML parse check` parse YAML dưới `.github`, `deploy`, và `techx-corp-chart` | Có | Đã có | Nên required cho PR chạm workflow/deploy/chart/app paths |
| Helm render/lint | `ci.yaml` job `Helm lint and render` chạy dependency build, lint, render observability/app manifests và assertions | Có | Đã có | Nên required cho chart/deploy/workflow changes |
| Terraform plan | `ci.yaml` job `Terraform infra plan` chạy fmt, init, validate, plan và upload plan artifact | Có | Đã có | Required cho infra changes trước merge; apply vẫn là post-merge |
| Docker smoke build | `ci.yaml` job `Docker smoke build checkout + shipping` build image checkout và shipping | Có | Đã có | Required cho app changes; smoke coverage hiện mới có checkout/shipping |
| Build/push | `build-and-push.yaml` job `Build and push app images` build selected images, push lên ECR, verify digests | Delivery gate, không phải PR gate | Đã có | Chạy sau khi merge vào `main`; không được xem là thay thế PR gate |
| Promote | `build-and-push.yaml` job `Open GitOps promotion PR` cập nhật GitOps repo và tạo/sửa promotion PR | Có, trên GitOps path | Đã có | GitOps repo cần branch protection để promotion PR không bypass checks |
| Terraform apply | `terraform-apply.yaml` job `Terraform apply infra` apply infra sau merge | Delivery gate, không phải PR gate | Đã có | Phải phụ thuộc vào source PR plan gate đã pass trước khi merge |
| GitOps manifest validation | GitOps repo `.github/workflows/validate.yaml` job `validate` chạy `scripts/validate.py` và Helm lint/render production releases | Có, trên GitOps PR | Đã có ở GitOps repo | Phải được require trên GitOps `main` để promotion/deploy PR đỏ bị block |
| Secret scan | Chưa thấy dedicated secret scanning gate trong các workflow hiện tại | Có | Thiếu | Mandate 10 gap |
| SAST | Chưa thấy dedicated SAST gate trong các workflow hiện tại | Có | Thiếu | Mandate 10 gap |
| IaC security scan | Có Terraform fmt/validate/plan, nhưng chưa thấy dedicated IaC security scan | Có | Thiếu | Terraform plan không phải security scanner |
| Image CVE scan | Có ECR digest verification sau push; chưa thấy PR/promotion-blocking CVE scan | Có | Thiếu | ECR scan-on-push không đủ là required gate nếu chưa wire kết quả vào blocking check |
| Signing/provenance verification | Chưa thấy image signing, attestations hoặc provenance verification gate | Có | Thiếu | Mandate 10 gap |

## Khuyến nghị required gates

Minimum source repo required checks từ workflow hiện tại:

- `YAML parse check`
- `Helm lint and render`
- `Terraform infra plan`
- `Docker smoke build checkout + shipping`

Các Mandate 10 gates còn thiếu và cần được bổ sung bằng follow-up implementation/security-scan tasks:

- Secret scan
- SAST
- IaC security scan
- Image CVE scan
- Signing/provenance verification

Required gates cho GitOps/deploy path:

- GitOps PR review trước merge.
- GitOps manifest validation/status check `GitOps Manifest Validation / validate` trước merge.
- Promotion/deploy branch protection để GitOps `main` không bị update khi required checks đỏ.
- Evidence riêng cho GitOps PR cố tình đỏ bị block, nếu promotion PR là đường deploy production.

Required checks sau khi SEC-15/SEC-16/SEC-19 hoàn tất phải bao gồm ít nhất:

- YAML parse / manifest validation.
- Helm render/lint hoặc GitOps render validation tương đương.
- Terraform plan/IaC validation cho infra path.
- Docker smoke build hoặc build validation cho app path.
- Secret scan.
- SAST.
- IaC security scan.
- Image CVE scan có cơ chế blocking.
- Signing/provenance verification.

## Lưu ý quan trọng cho subtask tiếp theo

- Một số job trong `ci.yaml` đang dùng path filter với `if:` conditions. Khi cấu hình required status checks, cần xác nhận GitHub có xem skipped checks là acceptable trong ruleset mode được chọn không, hoặc thêm một aggregate gate luôn chạy ở implementation task sau.
- `build-and-push.yaml` và `terraform-apply.yaml` chạy trên `push` vào `main`, nên không đủ để chặn một PR xấu khỏi merge.
- Không được ghi ECR scan-on-push là đủ điều kiện gate. Nó chỉ là gate nếu scan result được query và enforce trước merge hoặc trước GitOps promotion.
- Evidence hợp lệ cho SEC-14 phải có merge box/ruleset báo blocked trên PR. Chỉ có workflow fail screenshot là chưa đủ.

## Verification cần có ở các subtask sau

| Verification | Repo / branch | Cách chứng minh | Kết quả pass |
|---|---|---|---|
| Source PR bị chặn khi required checks fail | `TF4-Phase3-TechX/tf4-phase3-repo` / `main` | Tạo PR test cố tình làm một required check fail | PR hiển thị merge blocked, không merge được |
| GitOps promotion/deploy PR bị chặn khi validation fail | `TF4-Phase3-TechX/tf4-phase3-gitops-manifests` / deploy branch, hiện quan sát là `main` | Tạo promotion/deploy PR test cố tình làm validation fail | PR hiển thị merge blocked, không deploy được |
| Required checks sau SEC-15/SEC-16/SEC-19 được wire vào ruleset | Source repo và GitOps repo | Screenshot/API ruleset liệt kê required checks | Các gate security/delivery mới là required status checks |
| Không nhầm ECR scan-on-push là gate đủ điều kiện | Source/GitOps evidence | Ghi rõ scan result phải blocking trước merge/promotion | ECR scan-on-push chỉ là signal nếu không wire vào required check |

## Checklist Jira comment

```text
SEC-14 inventory:

Source repo:
- Repo/branch: TF4-Phase3-TechX/tf4-phase3-repo / main
- Owner: tf4-leads; CDO08 SEC-14 owner: Nhân

GitOps repo:
- Repo/branch: TF4-Phase3-TechX/tf4-phase3-gitops-manifests / main
- Owner: @TF4-Phase3-TechX/platform-owners theo CODEOWNERS; GitOps/platform owner cần xác nhận
- Promotion branch observed in workflow: promotion/production
- Existing validation workflow: .github/workflows/validate.yaml
- Existing validation check: GitOps Manifest Validation / validate
- Required verification: promotion/deploy PR đỏ phải bị blocked, không chỉ workflow fail

Existing workflows/jobs:
- ci.yaml: Detect changed areas; YAML parse check; Terraform infra plan; Helm lint and render; Docker smoke build checkout + shipping
- build-and-push.yaml: Select images to build; Build and push app images; Open GitOps promotion PR
- terraform-apply.yaml: Detect Terraform changes; Terraform apply infra
- gitops validate.yaml: validate manifests with scripts/validate.py and Helm lint/render production releases

Current required-gate candidates:
- YAML parse check
- Helm lint and render
- Terraform infra plan
- Docker smoke build checkout + shipping

Mandate 10 missing gates:
- Secret scan: missing
- SAST: missing
- IaC security scan: missing
- Image CVE scan: missing as a blocking gate
- Signing/provenance verification: missing

Note:
- ECR scan-on-push is not sufficient as a required gate unless its result is wired into a blocking status check before merge or promotion.
- Evidence required later: source PR failed-check blocked + GitOps promotion/deploy PR validation-fail blocked.
```

## Trạng thái acceptance criteria

- [x] Đã liệt kê workflow hiện có: `ci.yaml`, `build-and-push.yaml`, `terraform-apply.yaml`.
- [x] Đã liệt kê jobs hiện tại: YAML parse, Helm render, Terraform plan, Docker smoke build, build/push, promote.
- [x] Đã có bảng current vs required gates.
- [x] Đã liệt kê các Mandate 10 gates còn thiếu.
- [x] Đã xác định source repo `main` và GitOps promotion/deploy branch.
- [x] Đã ghi rõ owner của source repo và GitOps repo cần xác nhận.
- [x] Đã kiểm tra GitOps repo local và ghi nhận workflow `validate.yaml` / check `validate`.
- [x] Đã ghi rõ caveat: ECR scan-on-push không đủ là required gate.
- [x] Đã bổ sung scope verify cả source PR và GitOps promotion/deploy PR bị block khi checks fail.
- [x] Đã ghi rõ required checks phải bao gồm gate sau khi SEC-15/SEC-16/SEC-19 hoàn tất.
- [x] Đã ghi rõ evidence phải là PR bị merge blocked, không chỉ screenshot workflow fail.
