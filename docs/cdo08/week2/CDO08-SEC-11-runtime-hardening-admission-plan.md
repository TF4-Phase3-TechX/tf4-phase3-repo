# Plan: CDO08-SEC-11 — Enforce runtime hardening policy as code (admission)

**Owner:** Quân
**Reviewer:** Nguyên
**Priority:** P0
**Backlog:** CDO08-SEC-11
**Directive:** MANDATE-05 (Runtime Hardening) — hạn nộp thứ Sáu 17/07/2026
**Ngày:** 2026-07-16

---

## 0. Phạm vi task này (đọc trước khi review)

MANDATE-05 có 4 yêu cầu. Task này **chỉ** làm yêu cầu 4 (đẩy 3 luật còn lại vào admission, policy-as-code). Không làm lại yêu cầu 1–3 ở đây:

| # | Yêu cầu Mandate-05 | Trạng thái hiện tại (đã verify với repo) | Có nằm trong task này không |
|---|---|---|---|
| 1 | Không container chạy root | **Chưa xong** — người khác đang làm (SEC-09/10, chưa có trong code). Chỉ `frontend` (`values.yaml:579-582`) và `frontend-proxy` (`:669-672`) có `runAsNonRoot: true`. Default toàn chart là `securityContext: {}` (`values.yaml:35-36`) — phần lớn ~27 component (cart, payment, checkout, shipping, currency, ad, quote, fraud-detection...) **không có securityContext** → chạy được với root. | Không sửa container. Chỉ viết luật + để **audit mode** (xem §5). |
| 2 | Cấm image tag trôi (`latest`) | **Đã gần như xong trong thực tế** — `values.yaml:23` pin default tag là short-SHA (`8340af1`), CI (`build-and-push.yaml`) luôn build & patch tag theo SHA, không tìm thấy `latest`/tag trôi nào trong `values.yaml`. | Viết luật, có thể **enforce ngay**. |
| 3 | Bắt buộc requests/limits | **Đã xong** — hầu hết component trong `values.yaml` có `resources.requests/limits` (vd `checkout` L261-263, `payment` L738-740, các sidecar otel...). CI đã có bước "Assert application resource and HPA defaults" (`ci.yaml`) nhưng chỉ check 12/27 component tại **build time**, không phải admission time. | Viết luật, **enforce ngay** — làm nốt phần còn thiếu ở admission time cho toàn bộ chart, không phải 12 component CI đang assert. |
| 4 | **Enforce tự động qua admission (policy-as-code)** | Chưa có gì — không `ValidatingAdmissionPolicy`, Kyverno, Gatekeeper, hay webhook nào trong repo. | **Đây là task.** |

Vì yêu cầu 1 chưa xong ở tầng container, plan này **không thể** demo "root bị reject" ở chế độ enforce thật trong tuần này mà không tự ý enforce lên workload người khác đang code dở — điều này được nêu rõ ràng ở §5 và §8, không giấu.

---

## 1. Mục tiêu

Đẩy 3 luật hardening của Mandate-05 (non-root, no mutable tag, resources bắt buộc) vào **admission** — manifest vi phạm bị Kubernetes API server từ chối **ngay lúc apply**, không phụ thuộc người review bằng mắt hay CI (CI có thể bị bypass bởi `kubectl apply` tay, `helm upgrade --set` tay, hoặc PR future không đi qua CI).

**Không mục tiêu:** sửa container hiện có để hết vi phạm root (đó là SEC-09/10). Task này chỉ đảm bảo: (a) hạ tầng enforce đã sẵn sàng, (b) 2/3 luật đã bật enforce thật, (c) luật còn lại (non-root) đã **viết xong, đã bật audit**, sẵn sàng bật enforce ngay khi SEC-09/10 xong mà không cần thêm code mới.

---

## 2. Bối cảnh hệ thống hiện tại (evidence)

Verify trực tiếp trên repo trước khi chọn phương án:

| Hạng mục | Evidence | Ý nghĩa cho quyết định |
|---|---|---|
| K8s version | `infra/terraform/variables.tf:24-33` — `cluster_version = "1.34"`, không override ở `terraform.tfvars`; `infra/terraform/eks.tf` truyền thẳng vào module EKS 20.x | `ValidatingAdmissionPolicy` (VAP) **GA/stable từ 1.30** — cluster 1.34 dùng được ngay, không cần bật feature-gate. |
| Admission engine hiện có | Grep toàn repo: không có `ValidatingAdmissionPolicy`, Kyverno, Gatekeeper, OPA, admission webhook nào (ngoài thư mục vendor `.terraform/modules`) | Bắt đầu từ số 0, không có gì để migrate/tương thích ngược. |
| Namespace thật | `ci.yaml` render 2 namespace: `techx-tf4` (app, `deploy/values-app-stamp.yaml` + `values-flagd-sync.yaml` + `values-aio-llm.yaml`) và `techx-observability` (`deploy/values-observability.yaml`). Không có namespace riêng cho từng pillar/team. | "Namespace team quản lý" trong task **không khớp thực tế** — không có namespace riêng của CDO-08. Phải scope theo `techx-tf4` (nơi checkout/payment/shipping — service CDO-08 sở hữu — chạy chung với toàn bộ 27 service của cả TF). Ghi rõ trong ADR, không tự suy diễn thành "namespace riêng". |
| Namespace không do Terraform quản lý | Không có `kubernetes_namespace` resource cho `techx-tf4`/`techx-observability` trong `infra/terraform/` | Gắn label lên namespace phải làm bằng `kubectl label` thủ công (one-time bootstrap), không có chỗ để khai báo as-code — ghi rõ trong runbook rollout (§6). |
| CI hiện có | `.github/workflows/ci.yaml`: helm lint + helm template render 2 release + bước Python assert resources cho 12/27 deployment. Không có bước OPA/conftest/kubeval nào. | Cơ hội mở rộng CI sau này (không thuộc scope task), nhưng **không thay thế** được admission — CI chỉ chạy trên PR, không chặn `kubectl apply`/`helm upgrade` tay. |

---

## 3. Ba phương án — tradeoff

### 3.1 Bảng so sánh

| Tiêu chí | Kubernetes native `ValidatingAdmissionPolicy` (VAP) | Kyverno | Gatekeeper (OPA) |
|---|---|---|---|
| Cách chạy | CEL expression, chạy **trong API server**, không cần pod/controller riêng | Admission webhook controller riêng (Deployment, thường 3 pod HA) + CRD `ClusterPolicy` | Admission webhook controller riêng (constraint controller + audit controller, thường 2-3 pod) + CRD `ConstraintTemplate`/`Constraint` |
| Chi phí hạ tầng thêm | **0** — dùng API server sẵn có, không thêm pod, không thêm request/limit trên cluster | Thêm ~3 pod controller + webhook service, cần CPU/mem request riêng, cần theo dõi HA/upgrade | Tương tự Kyverno, cộng thêm audit pod định kỳ quét cluster |
| Yêu cầu version K8s | Cần **GA từ 1.30+** (cluster đang 1.34 → OK, không cần feature-gate) | Không phụ thuộc version K8s, cài qua Helm ở bất kỳ cluster nào | Không phụ thuộc version K8s |
| Ngôn ngữ viết luật | CEL (Common Expression Language) — cú pháp gọn nhưng cần học CEL | YAML pattern-matching — dễ đọc nhất, gần giống manifest thường | Rego (ngôn ngữ OPA riêng) — mạnh nhất, nhưng đường học cao nhất trong 3 lựa chọn |
| Audit → Enforce transition | `validationActions: [Audit, Warn]` ↔ `[Deny]` per-binding, đổi 1 field, apply lại | `validationFailureAction: Audit` ↔ `Enforce` per-policy | `enforcementAction: dryrun/warn` ↔ `deny` per-constraint |
| Rủi ro vận hành nếu lỗi | Lỗi CEL là lỗi trong tiến trình API server có sẵn — không thêm network hop; nhưng lỗi cú pháp có thể ảnh hưởng toàn bộ request khớp `matchConstraints` | Thêm 1 network hop (API server → webhook service); nếu webhook pod down/chậm, `failurePolicy` (Fail/Ignore) quyết định fail-open hay fail-closed toàn cluster | Tương tự Kyverno — thêm network hop, thêm điểm lỗi |
| Bảo trì lâu dài | Chỉ là YAML áp theo version K8s — không có chart/app riêng để vá lỗi/nâng cấp | Thêm 1 Helm chart cần theo dõi CVE, upgrade riêng, thêm alert/monitoring cho chính engine | Tương tự Kyverno |
| Khả năng mở rộng sau này | Đang cải thiện nhưng còn non hơn cho luật phức tạp (mutate, generate, image verify...) | Hệ sinh thái policy có sẵn phong phú (Kyverno policies hub), hỗ trợ mutate (tự sửa) + generate | Hệ sinh thái OPA rộng, dùng chung được cho nhiều mục đích ngoài K8s (CI, API gateway...) |
| Khớp ràng buộc Mandate-05 | Mandate: *"gần như không tốn thêm chi phí hạ tầng... đừng mượn cớ xin thêm resource"* → khớp tuyệt đối | Vi phạm tinh thần ràng buộc — cần thêm pod/controller | Vi phạm tinh thần ràng buộc — cần thêm pod/controller |

### 3.2 Vì sao không chọn Kyverno/Gatekeeper

Cả hai đều **đủ năng lực** làm 3 luật này (không phải vấn đề tính năng). Lý do loại:

1. **Mandate-05 tự đặt ràng buộc chi phí hạ tầng** ("gần như không tốn thêm chi phí hạ tầng... không phải dựng thêm service") — Kyverno/Gatekeeper đều là thêm 1 controller chạy 24/7 trên cluster production, tốn CPU/mem request thật, tốn thêm 1 thứ phải theo dõi SLO/upgrade/CVE.
2. **Task tự nêu out-of-scope**: *"Không cài policy engine mới nếu cluster đã có native admission đủ đáp ứng và ít rủi ro hơn."* — Cluster 1.34 đã đủ (VAP GA), nên điều kiện "không cài mới" áp dụng.
3. **Ít rủi ro vận hành hơn**: không thêm network hop admission → webhook, không thêm điểm lỗi khi webhook pod bị OOM/crash trong lúc production đang chạy — hợp với yêu cầu "không phá SLO lúc siết".
4. Nhu cầu hiện tại (non-root, tag cố định, resources bắt buộc) là validate đơn giản trên field có sẵn của Pod spec — không cần mutate, không cần generate, không cần integration ngoài cluster. Đây đúng là use-case CEL/VAP được thiết kế cho.

**Quyết định: dùng native `ValidatingAdmissionPolicy` + `ValidatingAdmissionPolicyBinding`.** Nếu sau này nhu cầu tăng (cần auto-mutate default resources, cần policy hub dùng chung nhiều cluster, cần Rego phức tạp hơn CEL cho phép), đây là quyết định có thể revisit — ghi rõ trong ADR là "đủ dùng cho nhu cầu hiện tại", không phải "không bao giờ cần Kyverno".

---

## 4. Ảnh hưởng tới hệ thống hiện tại (impact analysis)

Đây là điểm quan trọng nhất — vì hệ thống đang production, có khách thật.

| Rủi ro | Chi tiết | Biện pháp giảm thiểu trong plan này |
|---|---|---|
| **Enforce root ngay → chặn nhầm ~25/27 component đang chạy** | Chỉ `frontend`/`frontend-proxy` có `runAsNonRoot`. Nếu bật `Deny` cho luật root ngay, **mọi lần deploy lại** (rolling update do CD, do HPA scale, do node bị Karpenter consolidate) của cart/payment/checkout/... sẽ bị admission reject → outage diện rộng. | Luật root **chỉ bật `[Audit, Warn]`**, không bao giờ `Deny` cho đến khi SEC-09/10 xác nhận toàn bộ container đã có `runAsNonRoot`. Đây không phải thiếu sót của task — đây là *đúng* tinh thần "đi từ audit sang enforce có kiểm soát" mà Mandate-05 yêu cầu. |
| **Enforce sai namespace → ảnh hưởng add-on hệ thống** | VAP mặc định match theo `resourceRules`, nếu không giới hạn namespace sẽ áp cả lên `kube-system`, Karpenter, aws-load-balancer-controller, cert-manager, metrics-server... Những pod này không do TF4 kiểm soát, có thể không tuân luật (vd 1 số add-on chạy root theo thiết kế) → risk brick cluster (add-on không tự phục hồi được → mất autoscaling/ingress/DNS). | Dùng **allow-list qua `namespaceSelector`** thay vì áp cluster-wide: chỉ namespace được gắn label `techx.io/policy-scope: enforced` mới bị áp. Chỉ label `techx-tf4` và `techx-observability`. Không đụng `kube-system` hay namespace add-on khác — không cần deny-list dễ sót. |
| **Enforce lên namespace `techx-tf4` = ảnh hưởng cả TF, không riêng CDO-08** | Không có namespace riêng CDO-08 (xem §2) — mọi luật enforce trên `techx-tf4` tác động toàn bộ 27 service của cả 4 team | Mandate-05 vốn *"Áp dụng: toàn bộ Task Force"* nên về nguyên tắc đây không phải mở rộng phạm vi trái phép — nhưng vẫn cần **thông báo trước cho tf4-leads** trước khi flip bất kỳ luật nào sang `Deny` (không chỉ âm thầm enforce), vì §out-of-scope của task yêu cầu review toàn TF trước khi ảnh hưởng workload team khác. Xem §6 bước thông báo. |
| **`failurePolicy: Fail` làm API server treo nếu policy lỗi** | Nếu CEL expression lỗi runtime (vd field không tồn tại gây exception), `failurePolicy: Fail` sẽ reject luôn request thay vì cho qua | CEL dùng `has()` guard trước khi truy cập field lồng nhau (xem §5.2) để tránh runtime error; test bằng `--dry-run=server` trước khi bind thật (xem §7) trước khi set `Fail`. |
| **Tag/resources enforce ngay có thể chặn nhầm workload đang OK** | Task đánh giá yêu cầu 2, 3 "đã xong" dựa trên đọc `values.yaml` tĩnh — chưa xác nhận **runtime thật trên cluster** khớp 100% với chart (vd ai đó từng `kubectl set image` tay, hoặc patch ngoài Helm) | Trước khi bind `Deny` cho 2 luật này: chạy audit mode trước (dù ngắn), xem `kubectl get events`/audit annotations có violation nào không, đúng AC "cluster đang chạy không còn workload nào vi phạm" trước khi tuyên bố enforce xong. |

---

## 5. Thiết kế chi tiết

### 5.1 Namespace scope — bootstrap label (one-time, thủ công)

Vì namespace không quản lý qua Terraform (xem §2), bootstrap bằng tay trước khi apply policy:

```bash
kubectl label namespace techx-tf4 techx.io/policy-scope=enforced --overwrite
kubectl label namespace techx-observability techx.io/policy-scope=enforced --overwrite

# Xác nhận KHÔNG label các namespace add-on/hệ thống — allow-list, không phải deny-list
kubectl get ns --show-labels | grep -v "techx-tf4\|techx-observability"
```

### 5.2 3 `ValidatingAdmissionPolicy` — một file cho mỗi luật

File đề xuất: `techx-corp-chart/templates/admission/sec11-runtime-hardening-vap.yaml` (deploy độc lập ngoài vòng đời app release — xem lý do ở §6.1).

```yaml
# Luật 1 — Mandate-05 #1: cấm chạy root
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: sec11-no-root-containers
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
    - apiGroups: [""]
      apiVersions: ["v1"]
      operations: ["CREATE"]
      resources: ["pods"]
  validations:
  - expression: >
      object.spec.containers.all(c,
        has(c.securityContext) && has(c.securityContext.runAsNonRoot) &&
        c.securityContext.runAsNonRoot == true) &&
      (!has(object.spec.initContainers) || object.spec.initContainers.all(c,
        has(c.securityContext) && has(c.securityContext.runAsNonRoot) &&
        c.securityContext.runAsNonRoot == true))
    message: "Mandate-05 #1: container/initContainer phải set securityContext.runAsNonRoot=true."
---
# Luật 2 — Mandate-05 #2: cấm image tag trôi
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: sec11-no-mutable-image-tag
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
    - apiGroups: [""]
      apiVersions: ["v1"]
      operations: ["CREATE"]
      resources: ["pods"]
  validations:
  - expression: >
      object.spec.containers.all(c, c.image.contains(':') && !c.image.endsWith(':latest')) &&
      (!has(object.spec.initContainers) || object.spec.initContainers.all(c,
        c.image.contains(':') && !c.image.endsWith(':latest')))
    message: "Mandate-05 #2: image phải pin tag cố định hoặc digest (repo:tag hoặc repo@sha256:...), không dùng ':latest' hoặc untagged."
---
# Luật 3 — Mandate-05 #3: bắt buộc requests/limits
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: sec11-resources-required
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
    - apiGroups: [""]
      apiVersions: ["v1"]
      operations: ["CREATE"]
      resources: ["pods"]
  validations:
  - expression: >
      object.spec.containers.all(c,
        has(c.resources) &&
        has(c.resources.requests) && has(c.resources.requests.cpu) && has(c.resources.requests.memory) &&
        has(c.resources.limits) && has(c.resources.limits.cpu) && has(c.resources.limits.memory)) &&
      (!has(object.spec.initContainers) || object.spec.initContainers.all(c,
        has(c.resources) &&
        has(c.resources.requests) && has(c.resources.requests.cpu) && has(c.resources.requests.memory) &&
        has(c.resources.limits) && has(c.resources.limits.cpu) && has(c.resources.limits.memory)))
    message: "Mandate-05 #3: container/initContainer phải có đủ requests+limits cho cpu và memory."
```

> Match ở resource **`pods`** (không phải `deployments`) — vì Pod là nơi containers thực sự được tạo, kể cả pod sinh ra từ Deployment/StatefulSet/Job/CronJob. Đây cũng là cách Kyverno/Gatekeeper thường match cho đúng loại luật này.

### 5.3 3 `ValidatingAdmissionPolicyBinding` — audit/enforce tách riêng theo luật

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata:
  name: sec11-no-root-containers-binding
spec:
  policyName: sec11-no-root-containers
  validationActions: [Audit, Warn]   # PHASE: AUDIT — chờ SEC-09/10, KHÔNG Deny
  matchResources:
    namespaceSelector:
      matchLabels:
        techx.io/policy-scope: enforced
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata:
  name: sec11-no-mutable-image-tag-binding
spec:
  policyName: sec11-no-mutable-image-tag
  validationActions: [Deny]          # PHASE: ENFORCE — đã verify không còn vi phạm (§2, §7)
  matchResources:
    namespaceSelector:
      matchLabels:
        techx.io/policy-scope: enforced
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata:
  name: sec11-resources-required-binding
spec:
  policyName: sec11-resources-required
  validationActions: [Deny]          # PHASE: ENFORCE — đã verify không còn vi phạm (§2, §7)
  matchResources:
    namespaceSelector:
      matchLabels:
        techx.io/policy-scope: enforced
```

### 5.4 Exception policy (workload cần tạm miễn)

Nếu phát sinh workload hợp lệ nhưng cần audit tạm (vd job debug 1 lần, add-on nội bộ chưa kịp hardening), miễn trừ bằng `objectSelector` **ở binding**, không sửa policy gốc:

```yaml
  matchResources:
    namespaceSelector:
      matchLabels:
        techx.io/policy-scope: enforced
    objectSelector:
      matchExpressions:
      - key: techx.io/sec11-exempt
        operator: DoesNotExist
```

Workload cần miễn tạm thời gắn label `techx.io/sec11-exempt: "true"` + **bắt buộc** ghi lý do + ngày hết hạn miễn trừ vào ADR-015 (§9) — không miễn trừ âm thầm không thời hạn.

---

## 6. Rollout — audit → enforce có kiểm soát

| Bước | Việc | Luật | Điều kiện qua bước tiếp |
|---|---|---|---|
| 1 | Label 2 namespace (§5.1) | — | Namespace đã có label, không namespace add-on nào bị dính |
| 2 | Apply 3 `ValidatingAdmissionPolicy` (§5.2) — chưa có binding | Cả 3 | `kubectl get validatingadmissionpolicy` thấy đủ 3, `status.conditions` không lỗi |
| 3 | Apply binding luật **root** với `[Audit, Warn]` | Root | Không cần điều kiện — audit không chặn ai |
| 4 | **Full sweep** xác nhận zero violation runtime cho luật tag + resources trên toàn `techx-tf4`/`techx-observability` (không chỉ 12 component CI assert) | Tag, Resources | `kubectl get pods -A -o json` qua script check `image` regex + `resources` — 0 vi phạm |
| 5 | Apply binding luật **tag** + **resources** với `[Deny]` thẳng (đã confirm bước 4) | Tag, Resources | Dry-run `kubectl apply --server-side --dry-run=server` bằng chính workload thật (helm template) qua policy không bị reject |
| 6 | Thông báo tf4-leads/Nguyên: 2 luật đã enforce trên `techx-tf4` (namespace dùng chung toàn TF) | Tag, Resources | Có xác nhận review (Slack/PR comment) trước khi coi bước enforce là "chính thức" — không chỉ tự apply âm thầm |
| 7 | Theo dõi audit annotation của luật root trong lúc SEC-09/10 tiến triển | Root | Khi SEC-09/10 báo container cuối cùng đã có `runAsNonRoot`, chạy lại full sweep luật root |
| 8 | Flip binding luật root sang `[Deny]` | Root | Full sweep root = 0 vi phạm + thông báo tf4-leads |

Vì hạn Mandate-05 là 17/07/2026 (ngày mai), bước 1–6 làm **trong hôm nay**; bước 7–8 là follow-up phụ thuộc SEC-09/10 (không do task này block deadline — ADR ghi rõ đây là luật "còn ở audit và vì sao", đúng định dạng "Phải nộp" của mandate).

---

## 7. Manifest test vi phạm — cho mentor apply

3 file test, namespace `techx-tf4` (đã label `policy-scope: enforced`), dùng image công khai (`nginx`) để không phụ thuộc registry nội bộ:

`docs/cdo08/week2/sec11-test-manifests/bad-root-pod.yaml`
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: sec11-test-bad-root
  namespace: techx-tf4
spec:
  containers:
  - name: app
    image: nginx:1.27.0
    resources:
      requests: {cpu: "50m", memory: "64Mi"}
      limits: {cpu: "100m", memory: "128Mi"}
    # KHÔNG set securityContext.runAsNonRoot -> vi phạm luật 1
```

`docs/cdo08/week2/sec11-test-manifests/bad-latest-tag-pod.yaml`
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: sec11-test-bad-tag
  namespace: techx-tf4
spec:
  containers:
  - name: app
    image: nginx:latest   # vi phạm luật 2
    securityContext: {runAsNonRoot: true, runAsUser: 101}
    resources:
      requests: {cpu: "50m", memory: "64Mi"}
      limits: {cpu: "100m", memory: "128Mi"}
```

`docs/cdo08/week2/sec11-test-manifests/missing-resources-pod.yaml`
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: sec11-test-missing-resources
  namespace: techx-tf4
spec:
  containers:
  - name: app
    image: nginx:1.27.0
    securityContext: {runAsNonRoot: true, runAsUser: 101}
    # KHÔNG set resources -> vi phạm luật 3
```

### Verification

```bash
kubectl get validatingadmissionpolicy,validatingadmissionpolicybinding

# Luật đang ENFORCE — kỳ vọng bị reject
kubectl apply --server-side --dry-run=server -f docs/cdo08/week2/sec11-test-manifests/bad-latest-tag-pod.yaml
kubectl apply --server-side --dry-run=server -f docs/cdo08/week2/sec11-test-manifests/missing-resources-pod.yaml

# Luật ROOT còn ở AUDIT — kỳ vọng KHÔNG bị reject, nhưng có Warning + audit annotation
kubectl apply --server-side --dry-run=server -f docs/cdo08/week2/sec11-test-manifests/bad-root-pod.yaml
kubectl get events -n techx-tf4 --field-selector reason=ValidatingAdmissionPolicyAudit

# Xác nhận workload thật không bị chặn nhầm sau enforce
helm template techx-corp ./techx-corp-chart -n techx-tf4 -f deploy/values-app-stamp.yaml -f deploy/values-flagd-sync.yaml \
  | kubectl apply --server-side --dry-run=server -f -
helm template techx-observability ./techx-corp-chart -n techx-observability -f deploy/values-observability.yaml \
  | kubectl apply --server-side --dry-run=server -f -
```

**Điểm cần nói rõ với mentor (không giấu):** manifest `bad-root-pod.yaml` áp thử **sẽ pass** (không reject) trong tuần này, vì luật root đang audit-only — đây là chủ đích, không phải bug, lý do nằm ở §0/§4/§9 (ADR). Mentor sẽ thấy Warning message + audit annotation xác nhận policy có bắt được vi phạm, chỉ chưa chặn.

---

## 8. Rollback / Safety

| Tình huống | Rollback | Lý do chọn cách này |
|---|---|---|
| Enforce chặn nhầm workload production thật | `kubectl patch validatingadmissionpolicybinding <name> --type merge -p '{"spec":{"validationActions":["Audit","Warn"]}}'` — đổi ngay `Deny` → `Audit` | Không cần xóa policy, không mất lịch sử vi phạm đang audit, revert 1 field, có hiệu lực ngay (admission là đồng bộ, không cần rollout) |
| Policy tự nó lỗi (CEL runtime error, chặn mọi request) | `kubectl delete validatingadmissionpolicybinding <name>` (giữ policy, xóa binding) hoặc `kubectl delete validatingadmissionpolicy <name>` nếu cần gỡ hẳn | Xóa binding là đủ để tắt hiệu lực — không cần đụng workload đang chạy |
| Cần tắt toàn bộ admission SEC-11 khẩn cấp | `kubectl delete -f techx-corp-chart/templates/admission/sec11-runtime-hardening-vap.yaml` | Toàn bộ 3 policy + 3 binding nằm 1 file — rollback 1 lệnh, không ảnh hưởng app release (deploy tách rời — xem §6.1 lý do không nhúng vào chart chính) |

**Nguyên tắc:** Không bao giờ rollback bằng cách sửa `failurePolicy: Fail` → `Ignore` để "cho qua tạm" — làm vậy tắt mất bảo vệ khi API server có sự cố khác, dùng đúng field `validationActions` để hạ enforce xuống audit thay vì tắt failurePolicy.

---

## 9. ADR cần ký (giao nộp theo Mandate-05)

Tạo `docs/audit/adr/015-runtime-hardening-admission-policy.md` (tiếp số sau `014-ai-trust-safety-guardrails.md`), nội dung tối thiểu theo đúng yêu cầu "Phải nộp" của mandate:

- Luật nào đã **enforce** (tag, resources) và luật nào còn **audit** (root) — kèm lý do (SEC-09/10 chưa xong container).
- Điều kiện cụ thể để flip root sang enforce (full sweep = 0 violation + xác nhận SEC-09/10 done).
- Người ký: Quân (owner), review: Nguyên.

---

## 10. Coordination

| Role | Người | Trách nhiệm |
|---|---|---|
| Owner | Quân | Viết + apply policy, test manifest, ADR |
| Reviewer | Nguyên | Review CEL rules + rollout plan trước khi flip `Deny` |
| Phụ thuộc | (SEC-09/10 owner) | Hoàn tất `runAsNonRoot` cho container còn lại — điều kiện để flip luật root sang enforce |
| Thông báo | tf4-leads | Xác nhận trước khi enforce ảnh hưởng namespace `techx-tf4` dùng chung toàn TF |

---

## 11. Definition of Done

- [ ] 3 `ValidatingAdmissionPolicy` + 3 `ValidatingAdmissionPolicyBinding` apply thành công trên cluster
- [ ] Namespace `techx-tf4` và `techx-observability` đã label `techx.io/policy-scope=enforced`; không namespace hệ thống/add-on nào bị dính
- [ ] Luật tag + resources ở `validationActions: [Deny]`, đã full-sweep xác nhận 0 vi phạm trước khi flip
- [ ] Luật root ở `validationActions: [Audit, Warn]`, có audit annotation khi apply manifest vi phạm thử
- [ ] 3 manifest test (root/tag/resources) tạo sẵn cho mentor, mentor tự apply và thấy đúng kết quả kỳ vọng (2 reject, 1 audit-warn) — kết quả audit-warn cho root đã giải thích rõ, không phải bug
- [ ] `helm template` dry-run cả 2 release (app + observability) qua policy không bị chặn nhầm
- [ ] Rollback path verify được (patch `validationActions` về Audit, có hiệu lực ngay)
- [ ] ADR-015 ký tên (Quân) + review (Nguyên), map rõ luật nào enforce/luật nào audit và điều kiện flip
- [ ] Thông báo tf4-leads trước khi coi 2 luật enforce là chính thức (namespace dùng chung toàn TF)
- [ ] PM cập nhật backlog status
