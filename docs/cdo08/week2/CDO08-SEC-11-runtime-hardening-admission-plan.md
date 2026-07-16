# Plan: CDO08-SEC-11 — Enforce runtime hardening policy as code (admission)

**Owner:** Quân
**Reviewer:** Nguyên
**Priority:** P0
**Backlog:** CDO08-SEC-11
**Directive:** MANDATE-05 (Runtime Hardening) — hạn nộp thứ Sáu 17/07/2026
**Ngày:** 2026-07-16

---

## 0. Phạm vi

Task này hiện thực yêu cầu #4 của MANDATE-05: đẩy các luật runtime hardening vào **admission control** dưới dạng policy-as-code, để manifest vi phạm bị Kubernetes API server từ chối ngay lúc apply.

- **Cơ chế:** 4 `ValidatingAdmissionPolicy` (CEL) + 4 `ValidatingAdmissionPolicyBinding`, tất cả ở `[Deny]`.
- **Phạm vi áp dụng:** 2 namespace production `techx-tf4` và `techx-observability` (qua `namespaceSelector`) — không đụng namespace nào khác.
- **Nơi đặt code:** `techx-corp-chart/templates/admission-hardening.yaml` — nhúng vào chart ứng dụng để tự động deploy/cập nhật theo pipeline release có sẵn (build → bot promote → ArgoCD sync), không cần `kubectl apply` tay hay bootstrap namespace thủ công.
- **Điều kiện hạ tầng:** ArgoCD chỉ sync được resource cluster-scoped nếu AppProject whitelist kind đó — xem §6.

MANDATE-05 #1 yêu cầu cả "không chạy root" **và** "drop capability thừa", nên #1 được tách thành 2 policy. Bốn policy ánh xạ tới các yêu cầu như sau:

| # | Yêu cầu Mandate-05 | Luật admission |
|---|---|---|
| 1 | Không container chạy root | `require-run-as-nonroot` |
| 1 | Drop capability thừa | `require-drop-all-capabilities` |
| 2 | Cấm image tag trôi (`latest`/untagged) | `disallow-mutable-image-tag` |
| 3 | Bắt buộc requests/limits | `require-resource-limits` |

> **Ghi chú phạm vi (ticket vs mandate):** phần "việc cần làm" của ticket SEC-11 chỉ nêu 3 mục enforce (non-root, image tag, resources), **không** nêu capabilities. Nhưng Mandate-05 #1 ghi rõ *"drop mấy capability thừa"* là một phần của yêu cầu chống-root, nên plan bám theo mandate và có thêm luật `drop-all-capabilities`.

**Trạng thái compliance tại thời điểm bật Deny** (verify trực tiếp trên cluster, §2.1):
- `techx-tf4`: **sạch cả 4 luật** (22/22 workload) — không workload nào bị chặn.
- `techx-observability`: còn **4 workload vi phạm** (`otel-collector-agent`, `jaeger-es-index-cleaner` CronJob, init container `fsgroup-volume` của `opensearch`, `alertmanager` thiếu `drop: [ALL]`). Các workload này sẽ bị reject khi redeploy/scale/restart cho tới khi được sửa. Đây là **rủi ro đã biết và được owner chấp nhận** (§4, §6.1); nguyên nhân gốc nằm ngoài phạm vi task (§2.1).

---

## 1. Mục tiêu

Đẩy các luật hardening của Mandate-05 vào **admission** — manifest vi phạm bị API server từ chối **ngay lúc apply**, không phụ thuộc người review bằng mắt hay CI (CI có thể bị bypass bởi `kubectl apply` tay, `helm upgrade --set` tay, hoặc PR không đi qua CI).

**Không thuộc phạm vi:** sửa container hiện có để hết vi phạm (đó là SEC-09/SEC-10). Task này đảm bảo: (a) hạ tầng admission sẵn sàng — 4 policy + 4 binding `[Deny]` áp đúng 2 namespace production; (b) rollback path rõ ràng (§8) nếu một luật chặn nhầm workload; (c) notification bắt buộc (§6.2) để biết ngay khi có reject.

---

## 2. Bối cảnh hệ thống hiện tại (evidence)

Verify trực tiếp trên repo trước khi chọn phương án:

| Hạng mục | Evidence | Ý nghĩa cho quyết định |
|---|---|---|
| K8s version | `infra/terraform/variables.tf:24-33` — `cluster_version = "1.34"`, không override ở `terraform.tfvars`; `infra/terraform/eks.tf` truyền thẳng vào module EKS 20.x | `ValidatingAdmissionPolicy` (VAP) **GA/stable từ 1.30** — cluster 1.34 dùng được ngay, không cần bật feature-gate. |
| Admission engine hiện có | Grep toàn repo: không có `ValidatingAdmissionPolicy`, Kyverno, Gatekeeper, OPA, admission webhook nào (ngoài thư mục vendor `.terraform/modules`) | Bắt đầu từ số 0, không có gì để migrate/tương thích ngược. |
| Namespace thật | `ci.yaml` render 2 namespace: `techx-tf4` (app) và `techx-observability`. Không có namespace riêng cho từng pillar/team. | "Namespace team quản lý" trong ticket **không khớp thực tế** — không có namespace riêng của CDO-08. Phải scope theo `techx-tf4` (nơi checkout/payment/shipping — service CDO-08 sở hữu — chạy chung với toàn bộ 27 service của cả TF) + `techx-observability`. |
| Cách deploy chart | Chart `techx-corp` được ArgoCD cài làm 2 release: `techx-corp` (ns `techx-tf4`) và `techx-observability` (ns `techx-observability`), `syncPolicy.automated` + `selfHeal: true`. Chart đã render sẵn cluster-scoped resource (`ClusterRole`/`ClusterRoleBinding` trong `templates/team-rbac.yaml`). | Có sẵn đường để nhúng policy vào chart và được ArgoCD tự sync — không cần dựng Application/pipeline riêng. |
| AppProject whitelist | `argocd/root-resources/techx-production.yaml` (repo gitops): `clusterResourceWhitelist` hiện có `ClusterRole`/`ClusterRoleBinding`/webhook config nhưng **chưa** có `ValidatingAdmissionPolicy`, `ValidatingAdmissionPolicyBinding`, `Namespace`. | ArgoCD chặn sync cluster-scoped kind ngoài whitelist → phải thêm 3 kind này trước (§6). |
| CI hiện có | `.github/workflows/ci.yaml`: helm lint + helm template render 2 release + Python assert resources. Không có bước OPA/conftest/kubeval. | CI chỉ chạy trên PR, **không thay thế** admission — không chặn `kubectl apply`/`helm upgrade` tay. |


---

## 3. Ba phương án — tradeoff

### 3.1 Bảng so sánh

| Tiêu chí | Kubernetes native `ValidatingAdmissionPolicy` (VAP) | Kyverno | Gatekeeper (OPA) |
|---|---|---|---|
| Cách chạy | CEL expression, chạy **trong API server**, không cần pod/controller riêng | Admission webhook controller riêng (Deployment, thường 3 pod HA) + CRD `ClusterPolicy` | Admission webhook controller riêng (constraint + audit controller, thường 2-3 pod) + CRD `ConstraintTemplate`/`Constraint` |
| Chi phí hạ tầng thêm | **0** — dùng API server sẵn có, không thêm pod, không thêm request/limit | Thêm ~3 pod controller + webhook service, cần CPU/mem request riêng, theo dõi HA/upgrade | Tương tự Kyverno, cộng audit pod định kỳ quét cluster |
| Yêu cầu version K8s | Cần **GA từ 1.30+** (cluster 1.34 → OK, không cần feature-gate) | Không phụ thuộc version K8s | Không phụ thuộc version K8s |
| Ngôn ngữ viết luật | CEL — cú pháp gọn nhưng cần học | YAML pattern-matching — dễ đọc nhất | Rego — mạnh nhất nhưng đường học cao nhất |
| Audit → Enforce transition | `validationActions: [Audit, Warn]` ↔ `[Deny]` per-binding | `validationFailureAction: Audit` ↔ `Enforce` per-policy | `enforcementAction: dryrun/warn` ↔ `deny` per-constraint |
| Rủi ro vận hành nếu lỗi | Lỗi CEL nằm trong tiến trình API server có sẵn — không thêm network hop; lỗi cú pháp có thể ảnh hưởng request khớp `matchConstraints` | Thêm 1 network hop; webhook pod down/chậm → `failurePolicy` quyết định fail-open/closed toàn cluster | Tương tự Kyverno — thêm network hop, thêm điểm lỗi |
| Bảo trì lâu dài | Chỉ là YAML theo version K8s — không có chart/app riêng để vá/nâng cấp | Thêm 1 Helm chart cần theo dõi CVE, upgrade, monitoring riêng | Tương tự Kyverno |
| Khả năng mở rộng | Còn non hơn cho luật phức tạp (mutate, generate, image verify) | Hệ sinh thái policy phong phú, hỗ trợ mutate + generate | Hệ sinh thái OPA rộng, dùng chung nhiều mục đích |
| Khớp ràng buộc Mandate-05 | *"gần như không tốn thêm chi phí hạ tầng"* → khớp tuyệt đối | Vi phạm — cần thêm pod/controller | Vi phạm — cần thêm pod/controller |

### 3.2 Vì sao chọn VAP, không chọn Kyverno/Gatekeeper

Cả hai đều **đủ năng lực** làm các luật này (không phải vấn đề tính năng). Lý do loại:

1. **Mandate-05 ràng buộc chi phí hạ tầng** ("gần như không tốn thêm chi phí hạ tầng... không phải dựng thêm service") — Kyverno/Gatekeeper là thêm controller chạy 24/7 trên production, tốn CPU/mem thật, thêm thứ phải theo dõi SLO/upgrade/CVE.
2. **Ít rủi ro vận hành hơn**: không thêm network hop admission → webhook, không thêm điểm lỗi khi webhook pod OOM/crash lúc production đang chạy.
3. Nhu cầu hiện tại (non-root, tag cố định, resources, drop cap) là validate đơn giản trên field sẵn có của Pod spec — không cần mutate/generate/integration ngoài cluster. Đúng use-case VAP được thiết kế cho.


---

## 4. Ảnh hưởng tới hệ thống hiện tại (impact analysis)

| Rủi ro | Chi tiết | Biện pháp giảm thiểu |
|---|---|---|
|
| **Enforce sai namespace → chặn add-on hệ thống** | VAP match theo `resourceRules`; nếu không giới hạn namespace sẽ áp cả `kube-system`, Karpenter, aws-load-balancer-controller, cert-manager, metrics-server... — các pod không do TF4 kiểm soát, một số chạy root theo thiết kế → risk brick cluster (mất autoscaling/ingress/DNS). | **Allow-list qua `namespaceSelector`**: chỉ namespace gắn label `techx.io/policy-scope: enforced` bị áp. Label chỉ gắn cho `techx-tf4` + `techx-observability` (tự động qua chart, §5.1). Không đụng namespace add-on — không cần deny-list dễ sót. |
| **Enforce lên `techx-tf4` = ảnh hưởng cả TF, không riêng CDO-08** | Không có namespace riêng CDO-08 (§2) — luật enforce trên `techx-tf4` tác động toàn bộ 27 service của cả 4 team. | Mandate-05 vốn *"áp dụng toàn bộ Task Force"* nên không phải mở rộng phạm vi trái phép — nhưng vẫn **thông báo tf4-leads** trước khi enforce (§6, §10). |
| **`failurePolicy: Fail` treo request nếu policy lỗi** | CEL lỗi runtime (truy cập field không tồn tại) + `failurePolicy: Fail` → reject luôn request thay vì cho qua. | CEL dùng optional-chaining `?.` + `orValue(...)` (§5.2) nên không truy cập field vắng mặt → không gây runtime error; test `--dry-run=server` trước (§7). |
| **Tin đọc tĩnh `values.yaml` thay vì runtime** | `values.yaml` có thể đã hardening nhưng cluster chưa rollout (đúng trường hợp `techx-observability`). | Mọi đánh giá compliance (§2.1) dựa trên quét pod **đang chạy**, không dựa trên đọc tĩnh. |

---

## 5. Thiết kế chi tiết

Toàn bộ nằm trong 1 file: `techx-corp-chart/templates/admission-hardening.yaml`.

### 5.1 Namespace label — tự gắn qua chart

Namespace không quản lý qua Terraform (§2), và cũng không cần `kubectl label` tay. Template gắn label ngay trên `.Release.Namespace`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: {{ .Release.Namespace }}
  labels:
    techx.io/policy-scope: enforced
```

Chart cài làm 2 release nên cả `techx-tf4` và `techx-observability` **tự động** được gắn label khi release chạy, tự phục hồi nếu label bị gỡ ngoài ý muốn (`selfHeal: true`). Mỗi release chỉ label namespace của chính nó — không đụng namespace khác, không cần guard.

### 5.2 4 `ValidatingAdmissionPolicy`

VAP/Binding là **cluster-scoped**. Chart cài 2 release → nếu render vô điều kiện, policy bị tạo 2 lần → ownership conflict (đúng loại bug đang xảy ra thật với 2 `ExternalSecret` tranh 1 Secret, §2.1). Guard theo release để chỉ render 1 lần, dùng đúng pattern đã có sẵn trong chart cho cluster-scoped resource khác (`templates/team-rbac.yaml` dùng `{{- if eq .Release.Namespace "..." }}` cho `ClusterRole`/`ClusterRoleBinding`):

```yaml
{{- if eq .Release.Namespace "techx-tf4" }}
# ... 4 policy + 4 binding, chỉ render khi release techx-corp chạy ...
{{- end }}
```

Nhờ vậy 4 policy + 4 binding **chỉ tạo đúng 1 lần** (bởi release `techx-corp`), dù chart cài ở 2 nơi. Nhúng trong chart (thay vì manifest độc lập cần `kubectl apply` tay hoặc Application riêng) giúp policy tự động deploy/cập nhật theo pipeline release có sẵn — giống PVC, PDB, ClusterRole của chính chart này.

```yaml
# Luật 1 — Mandate-05 #1: cấm chạy root
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: require-run-as-nonroot
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
    - apiGroups: [""]
      apiVersions: ["v1"]
      operations: ["CREATE", "UPDATE"]
      resources: ["pods"]
  validations:
  # Tính EFFECTIVE runAsNonRoot: container-level override pod-level (đúng ngữ nghĩa K8s).
  # Nếu chỉ check container-level sẽ reject NHẦM manifest set runAsNonRoot ở pod-level.
  - expression: >
      (object.spec.containers + object.spec.?initContainers.orValue([])).all(c,
        c.?securityContext.?runAsNonRoot.orValue(
          object.spec.?securityContext.?runAsNonRoot.orValue(false)) == true)
    message: "Container/initContainer must run as non-root: set runAsNonRoot=true at pod or container level."
---
# Luật 2 — Mandate-05 #2: cấm image tag trôi / untagged
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: disallow-mutable-image-tag
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
    - apiGroups: [""]
      apiVersions: ["v1"]
      operations: ["CREATE", "UPDATE"]
      resources: ["pods"]
  validations:
  # Bare contains(':') sai khi registry có port, vd "registry.local:5000/team/app" chứa ':'
  # nhưng không có tag. Regex neo tag/digest vào ĐOẠN CUỐI: (.*/)? nuốt hết tới dấu '/' cuối,
  # nên ':' của registry port bị hút vào prefix optional, không bị tính là dấu phân tách tag.
  - expression: >
      (object.spec.containers + object.spec.?initContainers.orValue([])).all(c,
        c.image.matches('^(.*/)?[^/:@]+(:[A-Za-z0-9_.-]+|@sha256:[0-9a-f]{64})$') &&
        !c.image.endsWith(':latest'))
    message: "Image must pin a fixed tag or digest (repo:tag or repo@sha256:<digest>); ':latest', untagged images, and untagged images behind a registry:port are not allowed."
---
# Luật 3 — Mandate-05 #3: bắt buộc requests/limits
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: require-resource-limits
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
    - apiGroups: [""]
      apiVersions: ["v1"]
      operations: ["CREATE", "UPDATE"]
      resources: ["pods"]
  validations:
  - expression: >
      (object.spec.containers + object.spec.?initContainers.orValue([])).all(c,
        has(c.resources) &&
        has(c.resources.requests) && has(c.resources.requests.cpu) && has(c.resources.requests.memory) &&
        has(c.resources.limits) && has(c.resources.limits.cpu) && has(c.resources.limits.memory))
    message: "Container/initContainer must define both requests and limits for cpu and memory."
---
# Luật 4 — Mandate-05 #1 (phần 2): drop capability thừa, chỉ giữ cái thật sự cần
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: require-drop-all-capabilities
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
    - apiGroups: [""]
      apiVersions: ["v1"]
      operations: ["CREATE", "UPDATE"]
      resources: ["pods"]
  validations:
  # "drop excess capabilities, keep only what's needed" = drop ALL rồi add lại cái cần.
  # Chỉ enforce phần drop: [ALL]; add lại capability cụ thể là quyết định của từng service.
  - expression: >
      (object.spec.containers + object.spec.?initContainers.orValue([])).all(c,
        c.?securityContext.?capabilities.?drop.orValue([]).exists(d, d == 'ALL'))
    message: "Container/initContainer must drop all capabilities: set securityContext.capabilities.drop: [\"ALL\"] (add back only what is required)."
```

> Match ở resource **`pods`** (không phải `deployments`) — vì Pod là nơi containers thực sự được tạo, kể cả pod sinh ra từ Deployment/StatefulSet/Job/CronJob.

> Cả 4 luật gộp `containers` + `initContainers` bằng `object.spec.?initContainers.orValue([])` (optional-chaining của CEL) — cùng một điều kiện, không lặp code, tự động là `[]` khi pod không có initContainers.

> `operations: ["CREATE", "UPDATE"]` (không chỉ `CREATE`) — Mandate-05 #4 yêu cầu "áp cho cả thay đổi sau này". Image tag đổi in-place (`kubectl set image`) và resources đổi qua in-place pod resize (K8s 1.34) đều là `UPDATE`, sẽ lọt nếu chỉ match `CREATE`. Status update của kubelet đi qua subresource `pods/status` (không phải `pods`) nên không bị bắt → không spam/overhead.

### 5.3 4 `ValidatingAdmissionPolicyBinding` — tất cả `[Deny]`

Cùng 4 policy, mỗi policy 1 binding, tất cả `[Deny]`, cùng `namespaceSelector`. 4 binding chỉ khác nhau ở `name` + `policyName`:

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata: { name: require-run-as-nonroot-binding }
spec:
  policyName: require-run-as-nonroot
  validationActions: [Deny]
  matchResources:
    namespaceSelector:
      matchLabels: { techx.io/policy-scope: enforced }
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata: { name: require-drop-all-capabilities-binding }
spec:
  policyName: require-drop-all-capabilities
  validationActions: [Deny]
  matchResources:
    namespaceSelector:
      matchLabels: { techx.io/policy-scope: enforced }
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata: { name: disallow-mutable-image-tag-binding }
spec:
  policyName: disallow-mutable-image-tag
  validationActions: [Deny]
  matchResources:
    namespaceSelector:
      matchLabels: { techx.io/policy-scope: enforced }
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata: { name: require-resource-limits-binding }
spec:
  policyName: require-resource-limits
  validationActions: [Deny]
  matchResources:
    namespaceSelector:
      matchLabels: { techx.io/policy-scope: enforced }
```

### 5.4 Exception policy (workload cần tạm miễn)

Nếu phát sinh workload hợp lệ cần miễn tạm (job debug 1 lần, add-on nội bộ chưa kịp hardening), miễn trừ bằng `objectSelector` **ở binding**, không sửa policy gốc:

```yaml
  matchResources:
    namespaceSelector:
      matchLabels:
        techx.io/policy-scope: enforced
    objectSelector:
      matchExpressions:
      - key: techx.io/admission-exempt
        operator: DoesNotExist
```

Workload cần miễn gắn label `techx.io/admission-exempt: "true"` + **bắt buộc** ghi lý do + ngày hết hạn vào ADR-015 (§9) — không miễn trừ âm thầm không thời hạn.

---

## 6. Rollout

Vì policy nằm trong chart và cả 3 loại object (VAP, Binding, Namespace) đều cluster-scoped, rollout cần **2 bước ở 2 repo** — bước 1 là điều kiện tiên quyết của bước 2:

| Bước | Việc | Kết quả |
|---|---|---|
| 0 | **(Tiên quyết)** Thêm `ValidatingAdmissionPolicy` + `ValidatingAdmissionPolicyBinding` + `Namespace` vào `clusterResourceWhitelist` của AppProject `techx-production` (repo gitops) — cần CDO-04 review vì whitelist là project-wide (§2). | ArgoCD được phép sync 3 kind cluster-scoped này; nếu bỏ bước này, Application `techx-corp` sẽ sync fail (`resource ... is not permitted in project`). |
| 1 | Merge `techx-corp-chart/templates/admission-hardening.yaml` vào `main` của `tf4-phase3-repo` | Bot promote (§10) tự tạo PR bump chart revision bên `tf4-phase3-gitops-manifests`. |
| 2 | Merge PR promote đó | ArgoCD tự sync 2 release. Mỗi release tự label namespace của mình (§5.1); release `techx-corp` tạo thêm 4 policy + 4 binding `[Deny]`. Không có bước `kubectl apply`/label tay nào. |
| 3 | Verify: `kubectl get validatingadmissionpolicy,validatingadmissionpolicybinding` | Thấy đủ 8 object; cả 4 luật đang chặn thật trên cả 2 namespace. |
| 4 | Theo dõi ngay sau enforce (§6.2) | 4 workload ở `techx-observability` (§2.1) sẽ bị reject khi redeploy/scale/restart. Nếu reject xảy ra ở workload ngoài danh sách §2.1 → rollback rule đó theo §8. |
| 5 | Thông báo tf4-leads/Nguyên: admission đã enforce `[Deny]` cả 4 luật trên production | Xác nhận review; mọi bên biết rủi ro đang chấp nhận. |

### 6.1 Rủi ro compliance tại thời điểm enforce

| Luật | `techx-tf4` | `techx-observability` |
|---|---|---|
| **Image tag** | ✅ 0 vi phạm | ✅ 0 vi phạm |
| **Resources** | ✅ 0 vi phạm | ✅ 0 vi phạm (Job lịch sử đã chạy xong, không redeploy) |
| **Non-root** | ✅ sạch | ❌ 3 workload vi phạm — do Helm release `techx-observability` đang `failed` (§2.1), không phải SEC-09 chưa xong |
| **Capabilities** | ✅ sạch | ❌ 4 workload vi phạm (3 ở trên + `alertmanager`) |

Owner chấp nhận enforce `[Deny]` cả 2 namespace ngay, biết rõ 4 workload ở `techx-observability` sẽ bị reject khi redeploy cho tới khi release được sync lại. Rollback tức thì nếu cần: patch binding về `[Audit, Warn]` (§8).

### 6.2 Observability & Notification — bắt buộc

Vì enforce `[Deny]` khi `techx-observability` còn workload vi phạm, quan sát là **bắt buộc**, không phải "nên có" — cần biết ngay khi một workload bị reject để rollback kịp. Mỗi `validationActions` surface ra một kênh khác nhau:

| Action | Surface ở đâu | Kênh nhận thông báo (tận dụng component có sẵn) |
|---|---|---|
| **Deny** | API reject → **ArgoCD sync fail** | **ArgoCD Notifications** (`argocd-notifications-controller` đang chạy): trigger `on-sync-failed`/`on-health-degraded` → Slack, kèm message reject của VAP. Thêm alert Prometheus `argocd_app_info{sync_status="OutOfSync"}`. |
| **Warn** | Warning header trên API response (không fail) | Hiện trong `argocd app get`/UI và `kubectl` stderr. Không tự bắn alert → dựa vào metric bên dưới. |
| **Audit** | Chỉ API server audit log + metric (KHÔNG có Event, KHÔNG về client) | (a) metric API server (dưới); (b) EKS control-plane audit log → CloudWatch (ADR-005 đã bật) → filter annotation `validation.policy.admission.k8s.io/validation_failure` → CloudWatch alarm/SNS. |

**Nguồn tin cậy nhất — metric API server** (phủ cả deny + audit + lỗi CEL, độc lập ArgoCD). Prometheus (đã chạy) scrape `https://kubernetes.default.svc/metrics`, alert qua Alertmanager (đã chạy):

```
# Có vi phạm bị policy đánh trượt (deny hoặc would-deny ở audit):
sum by (policy) (rate(apiserver_validating_admission_policy_check_total{enforcement_action="deny"}[5m])) > 0

# Policy tự lỗi CEL runtime (nguy hiểm — cần bắt sớm, nhất là khi failurePolicy: Fail):
sum by (policy) (rate(apiserver_validating_admission_policy_check_total{error_type!="no_error"}[5m])) > 0
```

> Cần xác nhận Prometheus có RBAC scrape endpoint `/metrics` của kube-apiserver. Nếu chưa, thêm scrape config + RBAC `nonResourceURLs: ["/metrics"]` cho SA của Prometheus — việc nhỏ, không thêm hạ tầng.

**Bắt buộc bật ngay:** (1) alert Prometheus theo 2 rule trên → Alertmanager; (2) ArgoCD `on-sync-failed`/`on-health-degraded` → Slack. Đây là kênh để biết ngay khi một workload thật bị chặn, kịp rollback trước khi thành outage kéo dài.

---

## 7. Manifest test vi phạm

**Điều kiện trước:** đã hoàn tất §6 — 4 policy + 4 binding `[Deny]` đang có hiệu lực.

Không tạo namespace demo riêng — 3 file test dùng thẳng namespace `techx-tf4`, image công khai (`nginx`), và `--dry-run=server` để thấy **reject thật** mà không tạo object thật trong production:

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
    # KHÔNG set securityContext -> vi phạm luật 1 (runAsNonRoot) VÀ luật 4 (capabilities.drop)
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
    securityContext:
      runAsNonRoot: true
      runAsUser: 101
      capabilities: {drop: ["ALL"]}
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
    securityContext:
      runAsNonRoot: true
      runAsUser: 101
      capabilities: {drop: ["ALL"]}
    # KHÔNG set resources -> vi phạm luật 3
```

> Manifest tag + missing-resources cố tình set sẵn `runAsNonRoot` + `capabilities.drop: [ALL]` để **cô lập** đúng một luật vi phạm — thấy rõ luật nào reject, không lẫn với luật khác.

### Verification

```bash
kubectl get validatingadmissionpolicy,validatingadmissionpolicybinding

# (1) REJECT — apply thẳng vào techx-tf4 → cả 3 kỳ vọng BỊ REJECT
kubectl apply --server-side --dry-run=server -f docs/cdo08/week2/sec11-test-manifests/bad-root-pod.yaml
kubectl apply --server-side --dry-run=server -f docs/cdo08/week2/sec11-test-manifests/bad-latest-tag-pod.yaml
kubectl apply --server-side --dry-run=server -f docs/cdo08/week2/sec11-test-manifests/missing-resources-pod.yaml
# → mỗi lệnh trả error kèm message tương ứng (runAsNonRoot / image tag / requests+limits)

# (2) HEALTH CHECK — render toàn bộ workload thật rồi dry-run trong chính namespace production.
helm template techx-corp ./techx-corp-chart -n techx-tf4 -f deploy/values-app-stamp.yaml -f deploy/values-flagd-sync.yaml \
  | kubectl apply --server-side --dry-run=server -f -
# Kỳ vọng: techx-tf4 sạch cả 4 luật → toàn bộ pass. Nếu thấy reject ở đây,
# đó là workload ngoài dự kiến (rollback rule ngay theo §8).
```

**Điểm cần nói rõ:**
- `techx-tf4` `[Deny]` — manifest vi phạm bị reject thật, thỏa yêu cầu "apply thử một manifest vi phạm và thấy bị từ chối" của mandate.
- `techx-tf4` sạch hoàn toàn — không workload nào bị ảnh hưởng ngoài dự kiến. `techx-observability` còn 4 workload sẽ bị chặn khi redeploy (§2.1, §6.1) — rủi ro có chủ đích do Helm release riêng đang `failed`, đã chấp nhận.
- Nửa sau của mandate ("cluster không còn workload vi phạm") **chưa đạt tuyệt đối** cho `techx-observability` — nêu thẳng, không claim vượt thực tế.

---

## 8. Rollback / Safety

Rollback path dưới đây cần dùng NGAY nếu một workload thật bị chặn ngoài dự kiến (nhiều khả năng nhất: 1 trong 4 workload ở `techx-observability`, §6.1):

| Tình huống | Rollback | Lý do |
|---|---|---|
| Luật chặn nhầm workload production | Ngay lập tức: `kubectl patch validatingadmissionpolicybinding <name> --type merge -p '{"spec":{"validationActions":["Audit","Warn"]}}'` — đổi `Deny` → `Audit`, hiệu lực tức thì. Lâu dài: sửa `validationActions` trong `techx-corp-chart/templates/admission-hardening.yaml`, merge, để ArgoCD tự áp lại. | `kubectl patch` không cần rollout, dùng khi cần dừng khẩn; sửa chart là nguồn sự thật lâu dài (tránh drift — không patch tay rồi quên). |
| Policy tự lỗi (CEL runtime error, chặn mọi request) | `kubectl delete validatingadmissionpolicybinding <name>` (giữ policy, xóa binding) hoặc `kubectl delete validatingadmissionpolicy <name>` nếu cần gỡ hẳn — sau đó sửa/xoá tương ứng trong chart rồi merge. | Xóa binding đủ để tắt hiệu lực ngay; sửa chart tránh `selfHeal` tạo lại y hệt bug. |
| Cần tắt toàn bộ admission khẩn cấp | `kubectl delete validatingadmissionpolicybinding --all` (4 binding, không đụng Namespace/PVC/PDB khác) — sau đó `git revert` commit `admission-hardening.yaml` rồi merge để ArgoCD không tạo lại. | Policy nằm trong chart chung, không có file/Application riêng để `kubectl delete -f`; `git revert` là rollback lâu dài đúng, `kubectl delete` là chặn tạm trong lúc chờ merge. |

**Nguyên tắc:** Không rollback bằng cách sửa `failurePolicy: Fail` → `Ignore` — làm vậy tắt mất bảo vệ khi API server có sự cố khác. Dùng đúng field `validationActions` để hạ enforce xuống audit.

---

## 9. ADR cần ký (giao nộp theo Mandate-05)

Tạo `docs/audit/adr/015-runtime-hardening-admission-policy.md` (tiếp số sau `014-ai-trust-safety-guardrails.md`), nội dung tối thiểu:

- Quyết định: dùng native VAP (không Kyverno/Gatekeeper) — lý do §3.
- Trạng thái: 4 luật `[Deny]` trên `techx-tf4` + `techx-observability`. `techx-tf4` sạch 100%; `techx-observability` còn 4 workload vi phạm do Helm release riêng đang `failed` — rủi ro đã biết, owner chấp nhận để không trễ hạn.
- Ràng buộc hạ tầng: cần mở rộng `clusterResourceWhitelist` của AppProject `techx-production` (project-wide) — CDO-04 review.
- Người ký: Quân (owner), review: Nguyên.

---

## 10. Coordination

| Role | Người | Trách nhiệm |
|---|---|---|
| Owner | Quân | Viết policy, test manifest, ADR |
| Reviewer | Nguyên | Review CEL rules + rollout plan |
| Review hạ tầng | CDO-04 (platform) | Duyệt mở rộng `clusterResourceWhitelist` project-wide (§6 bước 0) |
| ✅ Đã xong | #233 (SEC-09) | Rollout `runAsNonRoot` + `capabilities.drop: [ALL]` — xác nhận 100% sạch ở `techx-tf4` (§2.1) |
| ✅ Đã xong | #235 | Pin busybox init image → `1.36.1` — blocker luật tag đã gỡ |
| Phụ thuộc còn lại | Người có quyền ArgoCD admin | Gỡ xung đột `ExternalSecret` + sync lại Helm release `techx-observability` đang `failed` (§2.1) — điều kiện để 4 workload còn lại hết vi phạm |
| Thông báo | tf4-leads | Xác nhận trước khi enforce (ảnh hưởng `techx-tf4` dùng chung toàn TF) |

---

## 11. Definition of Done

- [x] `techx-corp-chart/templates/admission-hardening.yaml` — 4 `ValidatingAdmissionPolicy` + 4 binding `[Deny]`, guard theo `.Release.Namespace` để không nhân đôi; Namespace tự label. Verify render bằng `helm template` cho cả 2 release (9 object cho `techx-corp`, 1 object cho `techx-observability`, không lặp policy).
- [x] Không còn `deploy/admission/runtime-hardening.yaml` hay `bootstrap-namespaces.sh` — đã xoá vì trùng chức năng với chart, tránh ownership conflict.
- [ ] Mở rộng `clusterResourceWhitelist` của AppProject `techx-production` (repo gitops, PR riêng) — CDO-04 duyệt.
- [ ] Merge chart vào `main`; bot promote tạo PR bump revision bên gitops; merge PR đó để ArgoCD sync.
- [ ] Verify trên cluster: 8 object tồn tại; cả 4 luật `[Deny]`; 2 namespace có label `techx.io/policy-scope=enforced`; không namespace add-on nào bị dính.
- [ ] 3 manifest test apply `--dry-run=server` vào `techx-tf4` → cả 3 bị reject thật.
- [ ] `helm template` dry-run toàn bộ workload thật vào `techx-tf4` → không workload nào bị reject ngoài dự kiến.
- [ ] Notification (§6.2) đã bật: alert Prometheus trên `apiserver_validating_admission_policy_check_total` (deny + error_type) → Alertmanager; ArgoCD `on-sync-failed` → Slack.
- [ ] Theo dõi 4 workload ở `techx-observability` (§2.1) khi redeploy — xác nhận đúng dự kiến, không phải sự cố ngoài ý muốn.
- [ ] Gỡ xung đột `ExternalSecret` + sync lại Helm release `techx-observability` (§10) — sau đó re-verify 4 workload còn lại hết vi phạm.
- [ ] Thông báo tf4-leads; PM cập nhật backlog status.
