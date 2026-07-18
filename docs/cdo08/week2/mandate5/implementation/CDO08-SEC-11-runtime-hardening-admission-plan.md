# Plan: CDO08-SEC-11 — Enforce runtime hardening policy as code (admission)

**Owner:** Quân
**Reviewer:** Nguyên
**Priority:** P0
**Backlog:** CDO08-SEC-11
**Directive:** MANDATE-05 (Runtime Hardening) — hạn nộp thứ Sáu 17/07/2026
**Ngày:** 2026-07-18

---

## 0. Phạm vi

Task này hiện thực yêu cầu #4 của MANDATE-05: đẩy các luật runtime hardening vào **admission control** dưới dạng policy-as-code, để manifest vi phạm bị Kubernetes API server từ chối ngay lúc apply.

- **Cơ chế:** 4 `ValidatingAdmissionPolicy` (CEL) + 4 `ValidatingAdmissionPolicyBinding`.
- **Phạm vi áp dụng:** **toàn cluster, trừ 3 namespace hệ thống Kubernetes** (`kube-system`, `kube-node-lease`, `kube-public`) qua `namespaceSelector` deny-list — không phải allow-list 2 namespace như bản thiết kế đầu tiên. Namespace mới phát sinh sau này tự động nằm trong phạm vi enforce, không cần ai gắn label thủ công.
- **Nơi đặt code:** tách 2 file trong `techx-corp-chart/templates/`:
  - `admission-hardening.yaml` — 4 `ValidatingAdmissionPolicy`.
  - `admission-hardening-bindings.yaml` — 4 `ValidatingAdmissionPolicyBinding` + logic exclude-list.

  Cả 2 nhúng vào chart ứng dụng để tự động deploy/cập nhật theo pipeline release có sẵn (build → bot promote → ArgoCD sync), không cần `kubectl apply` tay hay bootstrap namespace thủ công.
- **Điều kiện hạ tầng:** ArgoCD chỉ sync được resource cluster-scoped nếu AppProject whitelist kind đó — **đã merge xong** (xem §2).
- **Trạng thái enforce hiện tại:** cả 4 binding đang ở `[Audit, Warn]`, **chưa phải `[Deny]`**. Sẽ chuyển sang `[Deny]` sau khi merge và quan sát hệ thống ổn định (§6).

MANDATE-05 #1 yêu cầu cả "không chạy root" **và** "drop capability thừa", nên #1 được tách thành 2 policy. Bốn policy ánh xạ tới các yêu cầu như sau:

| # | Yêu cầu Mandate-05 | Luật admission |
|---|---|---|
| 1 | Không container chạy root | `require-run-as-nonroot` |
| 1 | Drop capability thừa | `require-drop-all-capabilities` |
| 2 | Cấm image tag trôi (`latest`/untagged) | `disallow-mutable-image-tag` |
| 3 | Bắt buộc requests/limits | `require-resource-limits` |

> **Ghi chú phạm vi (ticket vs mandate):** phần "việc cần làm" của ticket SEC-11 chỉ nêu 3 mục enforce (non-root, image tag, resources), **không** nêu capabilities. Nhưng Mandate-05 #1 ghi rõ *"drop mấy capability thừa"* là một phần của yêu cầu chống-root, nên plan bám theo mandate và có thêm luật `drop-all-capabilities`.

**Trạng thái compliance hiện tại** (verify trực tiếp trên cluster, §2.1, §6.1):
- `techx-tf4`: **sạch cả 4 luật** (22/22 workload).
- `techx-observability`: **sạch 8/10** — 2 "vi phạm" còn lại là Job lịch sử của `jaeger-es-index-cleaner` đã chạy xong trước khi fix, không phải rủi ro thật (CronJob template hiện tại đã sạch, xác nhận bằng lần chạy mới nhất cũng sạch).
- `argocd`, `external-secrets`: **CỐ Ý không loại trừ khỏi phạm vi**, nhưng cả 2 đang `resources: {}` rỗng hoàn toàn — cần bổ sung trước khi bật `[Deny]` (xem §6, §10).

---

## 1. Mục tiêu

Đẩy các luật hardening của Mandate-05 vào **admission** — manifest vi phạm bị API server từ chối **ngay lúc apply**, không phụ thuộc người review bằng mắt hay CI (CI có thể bị bypass bởi `kubectl apply` tay, `helm upgrade --set` tay, hoặc PR không đi qua CI).

**Không thuộc phạm vi:** sửa container hiện có để hết vi phạm (đó là SEC-09/SEC-10). Task này đảm bảo: (a) hạ tầng admission sẵn sàng — 4 policy + 4 binding áp toàn cluster trừ 3 namespace hệ thống; (b) rollback path rõ ràng (§8) nếu một luật chặn nhầm workload; (c) notification bắt buộc (§6.2) để biết ngay khi có reject/warn.

---

## 2. Bối cảnh hệ thống hiện tại (evidence)

Verify trực tiếp trên repo + cluster trước khi chọn phương án:

| Hạng mục | Evidence | Ý nghĩa cho quyết định |
|---|---|---|
| K8s version | `infra/terraform/variables.tf:24-33` — `cluster_version = "1.34"` | `ValidatingAdmissionPolicy` (VAP) **GA/stable từ 1.30** — dùng ngay, không cần feature-gate. |
| Admission engine hiện có | Grep toàn repo: không có Kyverno, Gatekeeper, OPA, admission webhook nào khác | Bắt đầu từ số 0, không có gì để migrate/tương thích ngược. |
| Cách deploy chart | Chart `techx-corp` được ArgoCD cài làm 2 release: `techx-corp` (ns `techx-tf4`) và `techx-observability` (ns `techx-observability`), `syncPolicy.automated` + `selfHeal: true`. | Có sẵn đường để nhúng policy vào chart và được ArgoCD tự sync. |
| AppProject whitelist | `argocd/root-resources/techx-production.yaml` (repo gitops): **đã merge xong**, `clusterResourceWhitelist` hiện có đủ `ValidatingAdmissionPolicy`, `ValidatingAdmissionPolicyBinding`, `Namespace`, `StorageClass`. | Không còn là blocker — ArgoCD sync được các kind cluster-scoped mà policy này cần. |
| CI hiện có | `.github/workflows/ci.yaml`: helm lint + helm template render 2 release + Python assert resources. Không có bước OPA/conftest/kubeval. | CI chỉ chạy trên PR, **không thay thế** admission — không chặn `kubectl apply`/`helm upgrade` tay. |

### 2.1 Scan toàn cluster theo namespace (kubectl get pods -o json + đối chiếu securityContext/resources/image từng container)

| Namespace | Compliance | Ghi chú |
|---|---|---|
| `techx-tf4` | 22/22 | Sạch hoàn toàn cả 4 luật. |
| `techx-observability` | 8/10 | 2 Job lịch sử của `jaeger-es-index-cleaner` (đã chạy xong trước khi SEC-09 fix rollout) — không phải rủi ro thật, CronJob template hiện tại đã sạch. |
| `kube-system` | 1/8 (chỉ `karpenter` sạch) | Xem §2.2 — lý do loại trừ. |
| `argocd` | 0/7 | Chỉ thiếu `resources` — đã non-root, đã drop capabilities, đã pin image. Xem §6/§10. |
| `external-secrets` | 0/3 | Tương tự `argocd` — chỉ thiếu `resources`. |
| `kube-node-lease`, `kube-public`, `default`, `techx-admission-test` | không có pod | Không cần enforce gì. |

### 2.2 Vì sao loại trừ đúng 3 namespace (`kube-system`, `kube-node-lease`, `kube-public`), không phải carve-out từng workload

Bằng chứng cụ thể trong `kube-system`:

- `kube-proxy`, `aws-node` (VPC CNI), `ebs-csi-node`, `eks-pod-identity-agent`: chạy `privileged: true` hoặc `capabilities.add: [NET_ADMIN/NET_RAW]` **theo thiết kế bắt buộc** — cấu hình iptables/eBPF, mount thiết bị host. Là DaemonSet được tạo lại trên **mọi node mới** (Karpenter scale-out) — nếu bị Deny chặn, node mới sẽ không có networking/storage, blast radius là toàn cluster.
- `coredns`, `aws-load-balancer-controller`, `ebs-csi-controller`, `karpenter` (cũng trong `kube-system`) — không có yêu cầu privileged, chỉ thiếu vài field (resource limits, capabilities.drop) — **có thể sửa**, nhưng namespace-level exclusion không tách được 2 nhóm này.

**Đã cân nhắc và loại bỏ hướng carve-out theo từng workload** (dùng `objectSelector` theo label thay vì `namespaceSelector` theo tên namespace) vì 2 lý do:
1. Không phải pattern chuẩn ngành — Pod Security Admission của chính upstream Kubernetes cũng exempt `kube-system` nguyên khối trong mọi hướng dẫn triển khai chính thức; không có tiền lệ carve-out từng workload hệ thống bằng objectSelector.
2. **Mở lỗ hổng nghiêm trọng hơn**: nếu chỉ dùng `objectSelector` (bỏ `namespaceSelector`), bất kỳ ai có quyền tạo pod ở **namespace bất kỳ** (kể cả `techx-tf4`) đều có thể tự gắn label giống hệt (`k8s-app: aws-node`...) để né toàn bộ 4 luật — namespace-level exclusion không có lỗ hổng này vì rào cản là quyền ghi vào `kube-system`, không phải tự set label.

**Rủi ro "ai đó thêm workload vi phạm vào 3 namespace bị loại trừ" — chấp nhận được vì 2 lớp phòng thủ:**
1. RBAC đã chặn từ tầng dưới — quyền tạo/sửa pod trong `kube-system` là quyền cluster-admin, các role làm việc thường ngày của TF không có (verify thực tế: role audit thông thường còn không tạo được pod trong namespace app `techx-tf4`).
2. Admission policy không phải lớp phòng thủ chống cluster-admin — ai đã có quyền ghi vào `kube-system` thì cũng có quyền xoá chính `ValidatingAdmissionPolicy`. Kiểm soát nhóm quyền này thuộc RBAC + audit log, không phải việc của policy này.

### 2.3 `argocd` và `external-secrets` — CỐ Ý không loại trừ

Verify: cả 2 đã non-root, đã drop capabilities, đã pin image — chỉ thiếu `resources` (đang `{}` rỗng hoàn toàn). Đây là fix được, không phải giới hạn bảo mật, nên luật vẫn áp — xem §6/§10 cho kế hoạch bổ sung trước khi bật `[Deny]`.

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
| **Enforce toàn cluster → chặn add-on hệ thống** | VAP match theo `resourceRules`; nếu không giới hạn namespace sẽ áp cả `kube-system` — một số pod ở đó chạy privileged theo thiết kế bắt buộc → risk brick cluster (mất autoscaling/ingress/DNS/storage khi node mới join). | **Deny-list qua `namespaceSelector`**: `kubernetes.io/metadata.name NotIn [kube-system, kube-node-lease, kube-public]` — mọi namespace khác đều enforce, kể cả namespace mới phát sinh sau này. Chi tiết lý do chọn deny-list namespace thay vì objectSelector: §2.2. |
| **`argocd`/`external-secrets` bị chặn redeploy vì thiếu resources** | Cả 2 đang `resources: {}` — nếu bật `[Deny]` ngay, lần redeploy tiếp theo của bất kỳ component nào trong 2 namespace này sẽ bị chặn. | Bổ sung resources trước khi bật `[Deny]` (§6, §10) — `external-secrets` qua PR GitOps, `argocd` qua lệnh `helm upgrade` thủ công (không quản lý qua GitOps). Trong lúc chờ, giữ `[Audit, Warn]` để không chặn gì cả. |
| **Enforce lên `techx-tf4` = ảnh hưởng cả TF, không riêng CDO-08** | Không có namespace riêng CDO-08 — luật enforce trên `techx-tf4` tác động toàn bộ 27 service của cả 4 team. | Mandate-05 vốn *"áp dụng toàn bộ Task Force"* nên không phải mở rộng phạm vi trái phép — nhưng vẫn **thông báo tf4-leads** trước khi enforce Deny (§6, §10). |
| **`failurePolicy: Fail` treo request nếu policy lỗi** | CEL lỗi runtime (truy cập field không tồn tại) + `failurePolicy: Fail` → reject luôn request thay vì cho qua. | CEL dùng optional-chaining `?.` + `orValue(...)` (§5.2) nên không truy cập field vắng mặt → không gây runtime error; test `--dry-run=server` trước (§7). |
| **Regex image-tag reject nhầm reference hợp lệ** | Bản đầu chỉ chấp nhận `repo:tag` HOẶC `repo@sha256:digest`, không chấp nhận cả 2 cùng lúc (`repo:tag@sha256:digest`) — chính image của `karpenter` dùng format này. | Đã sửa regex thêm alternative thứ 3 cho phép tag+digest kết hợp (§5.2). |

---

## 5. Thiết kế chi tiết

### 5.1 4 `ValidatingAdmissionPolicy` (`techx-corp-chart/templates/admission-hardening.yaml`)

VAP là **cluster-scoped**. Chart cài 2 release → nếu render vô điều kiện, policy bị tạo 2 lần → ownership conflict (đúng loại bug đã gặp thật với 2 `ExternalSecret` tranh 1 Secret, đã CDO07 fix xong — xem §10). Guard theo release để chỉ render 1 lần, dùng đúng pattern đã có sẵn trong chart cho cluster-scoped resource khác (`templates/team-rbac.yaml` dùng `{{- if eq .Release.Namespace "..." }}` cho `ClusterRole`/`ClusterRoleBinding`):

```yaml
{{- if eq .Release.Namespace "techx-tf4" }}
# ... 4 policy, chỉ render khi release techx-corp chạy ...
{{- end }}
```

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
  # Alternative thứ 3 cho phép tag+digest kết hợp (repo:tag@sha256:<digest>) — reference hợp lệ,
  # thậm chí pin chặt hơn cả tag-only hay digest-only; karpenter's own image dùng format này.
  - expression: >
      (object.spec.containers + object.spec.?initContainers.orValue([])).all(c,
        c.image.matches('^(.*/)?[^/:@]+(:[A-Za-z0-9_.-]+|@sha256:[0-9a-f]{64}|:[A-Za-z0-9_.-]+@sha256:[0-9a-f]{64})$') &&
        !c.image.endsWith(':latest'))
    message: "Image must pin a fixed tag or digest (repo:tag, repo@sha256:<digest>, or repo:tag@sha256:<digest>); ':latest', untagged images, and untagged images behind a registry:port are not allowed."
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

### 5.2 4 `ValidatingAdmissionPolicyBinding` (`techx-corp-chart/templates/admission-hardening-bindings.yaml`)

Tách riêng khỏi file policy để giữ logic exclude-list độc lập, dễ đọc/sửa mà không đụng CEL. Cùng guard `{{- if eq .Release.Namespace "techx-tf4" }}` như policy — chỉ render 1 lần.

```yaml
{{- if eq .Release.Namespace "techx-tf4" }}
{{- $excludedNamespaces := list "kube-system" "kube-node-lease" "kube-public" }}
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata:
  name: require-run-as-nonroot-binding
spec:
  policyName: require-run-as-nonroot
  validationActions: [Audit, Warn]
  matchResources:
    namespaceSelector:
      matchExpressions:
      - key: kubernetes.io/metadata.name
        operator: NotIn
        values: {{ $excludedNamespaces | toYaml | nindent 8 }}
---
# ... 3 binding còn lại, cùng cấu trúc, chỉ khác name + policyName ...
{{- end }}
```

`kubernetes.io/metadata.name` là label built-in mọi namespace tự có (K8s ≥1.21) — không cần gắn label thủ công nào cho việc scoping, khác hẳn bản thiết kế đầu tiên (namespace phải tự gắn `techx.io/policy-scope: enforced`).

**`validationActions` hiện tại là `[Audit, Warn]`** — chưa Deny. Kế hoạch chuyển sang `[Deny]`: xem §6.

### 5.3 Exception policy (workload cần tạm miễn)

Nếu phát sinh workload hợp lệ cần miễn tạm (job debug 1 lần, add-on nội bộ chưa kịp hardening), miễn trừ bằng `objectSelector` **ở binding**, không sửa policy gốc:

```yaml
  matchResources:
    namespaceSelector:
      matchExpressions:
      - key: kubernetes.io/metadata.name
        operator: NotIn
        values: [kube-system, kube-node-lease, kube-public]
    objectSelector:
      matchExpressions:
      - key: techx.io/admission-exempt
        operator: DoesNotExist
```

Workload cần miễn gắn label `techx.io/admission-exempt: "true"` + **bắt buộc** ghi lý do + ngày hết hạn vào ADR-015 (§9) — không miễn trừ âm thầm không thời hạn.

---

## 6. Rollout

| Bước | Việc | Trạng thái |
|---|---|---|
| 0 | AppProject `techx-production` whitelist đủ `ValidatingAdmissionPolicy`/`Binding`/`Namespace`/`StorageClass` (repo gitops) | ✅ **Đã merge** |
| 1 | Merge PR [#302](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/302) (`tf4-phase3-repo`) — scope cluster-wide + fix regex tag+digest | ⏳ Đang chờ review |
| 2 | Bổ sung resources cho `external-secrets` — PR [#31](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/31) (repo gitops) | ⏳ Đang chờ review |
| 3 | Bổ sung resources cho `argocd` — lệnh `helm upgrade` thủ công (không quản lý qua GitOps, xem §10) | ⏳ Đang chờ CDO-04 chạy |
| 4 | Merge PR #302 → bot promote tạo PR bump chart revision bên gitops → merge PR đó → ArgoCD tự sync | Sau khi bước 1-3 xong |
| 5 | Verify: `kubectl get validatingadmissionpolicy,validatingadmissionpolicybinding` — đủ 8 object, `[Audit, Warn]` | Sau bước 4 |
| 6 | Quan sát hệ thống ổn định qua kênh audit/warn (§6.2) trong khoảng thời gian đủ tin cậy | Sau bước 5 |
| 7 | Chuyển `validationActions` từ `[Audit, Warn]` sang `[Deny]` — sửa `admission-hardening-bindings.yaml`, merge, ArgoCD tự áp | Sau bước 6, khi hệ thống ổn định |
| 8 | Thông báo tf4-leads/Nguyên: admission đã enforce `[Deny]` cả 4 luật trên production | Sau bước 7 |

### 6.1 Rủi ro compliance tại thời điểm dự kiến bật Deny

| Luật | `techx-tf4` | `techx-observability` | `argocd` | `external-secrets` |
|---|---|---|---|---|
| Non-root | ✅ | ✅ | ✅ | ✅ |
| Drop capabilities | ✅ | ✅ | ✅ | ✅ |
| Image tag | ✅ | ✅ | ✅ | ✅ |
| Resource limits | ✅ | ✅ | ❌ **(pending §6 bước 3)** | ❌ **(pending §6 bước 2)** |

Chỉ enforce `[Deny]` sau khi bảng trên toàn `✅` — không lặp lại sai lầm "Deny dựa trên workload đang vi phạm".

### 6.2 Observability & Notification — bắt buộc

Vì `[Deny]` sẽ là chặn thật ở Kubernetes API server, quan sát là **bắt buộc**, không phải "nên có". Mỗi `validationActions` surface ra một kênh khác nhau:

| Action | Surface ở đâu | Kênh xem |
|---|---|---|
| **Deny** (sau §6 bước 7) | API reject → **ArgoCD sync fail** | ArgoCD Notifications (`on-sync-failed`/`on-health-degraded` → Slack) + Prometheus `argocd_app_info{sync_status="OutOfSync"}`. |
| **Warn** (hiện tại) | Warning header trên API response (không fail) | `kubectl`/ArgoCD sync log trực tiếp; không tự bắn alert → dựa vào metric bên dưới. |
| **Audit** (hiện tại) | Chỉ API server audit log + metric (KHÔNG có Event) | (a) metric Prometheus; (b) EKS control-plane audit log → CloudWatch. |

**Metric Prometheus** (`apiserver_validating_admission_policy_check_total`, label `enforcement_action`):
```promql
# Warn (đang bật)
sum by (policy) (rate(apiserver_validating_admission_policy_check_total{enforcement_action="warn"}[5m])) > 0

# Audit (đang bật)
sum by (policy) (rate(apiserver_validating_admission_policy_check_total{enforcement_action="audit"}[5m])) > 0

# Deny (chưa bật, sẽ dùng sau §6 bước 7)
sum by (policy) (rate(apiserver_validating_admission_policy_check_total{enforcement_action="deny"}[5m])) > 0

# Policy tự lỗi CEL runtime — cần bắt sớm, nhất là khi failurePolicy: Fail
sum by (policy) (rate(apiserver_validating_admission_policy_check_total{error_type!="no_error"}[5m])) > 0
```
Kiểm tra Prometheus có scrape được kube-apiserver không: `up{job=~".*apiserver.*"}` — nếu rỗng, chưa có scrape config, phải bổ sung trước khi tin bất kỳ số nào ở trên.

**CloudWatch Logs Insights** (chi tiết đúng object/namespace/message, Prometheus không có):
```
Log group: /aws/eks/techx-tf4-cluster/cluster
Log stream: kube-apiserver-audit-*

fields @timestamp, objectRef.namespace, objectRef.name, objectRef.resource, user.username,
       annotations.validation_policy_admission_k8s_io_validation_failure
| filter ispresent(annotations.validation_policy_admission_k8s_io_validation_failure)
| sort @timestamp desc
| limit 20
```
(CloudWatch tự đổi `.`/`/` trong annotation key gốc `validation.policy.admission.k8s.io/validation_failure` thành `_` khi query.)

**Bắt buộc bật trước khi chuyển sang Deny:** (1) alert Prometheus theo 2 rule deny/error_type ở trên → Alertmanager; (2) ArgoCD `on-sync-failed`/`on-health-degraded` → Slack.

---

## 7. Manifest test vi phạm

**Vị trí:** `docs/cdo08/week2/mandate5/sec11-test-manifests/` — 3 file, namespace `techx-tf4`, image công khai (`nginx`).

```yaml
# bad-root-pod.yaml — vi phạm luật 1 (runAsNonRoot) VÀ luật 4 (capabilities.drop)
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
    # KHÔNG set securityContext
```

```yaml
# bad-latest-tag-pod.yaml — cô lập vi phạm luật 2 (image tag)
apiVersion: v1
kind: Pod
metadata:
  name: sec11-test-bad-tag
  namespace: techx-tf4
spec:
  containers:
  - name: app
    image: nginx:latest
    securityContext:
      runAsNonRoot: true
      runAsUser: 101
      capabilities: {drop: ["ALL"]}
    resources:
      requests: {cpu: "50m", memory: "64Mi"}
      limits: {cpu: "100m", memory: "128Mi"}
```

```yaml
# missing-resources-pod.yaml — cô lập vi phạm luật 3 (resources)
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
    # KHÔNG set resources
```

### Verification

```bash
kubectl get validatingadmissionpolicy,validatingadmissionpolicybinding

# Tạo vi phạm thử — dry-run để không rác pod thật trong techx-tf4
kubectl apply --server-side --dry-run=server -f docs/cdo08/week2/mandate5/sec11-test-manifests/bad-root-pod.yaml
kubectl apply --server-side --dry-run=server -f docs/cdo08/week2/mandate5/sec11-test-manifests/bad-latest-tag-pod.yaml
kubectl apply --server-side --dry-run=server -f docs/cdo08/week2/mandate5/sec11-test-manifests/missing-resources-pod.yaml

# HEALTH CHECK — render toàn bộ workload thật rồi dry-run trong chính namespace production.
helm template techx-corp ./techx-corp-chart -n techx-tf4 -f deploy/values-app-stamp.yaml -f deploy/values-flagd-sync.yaml \
  | kubectl apply --server-side --dry-run=server -f -
```

**Khi đang `[Audit, Warn]` (hiện tại):** cả 3 manifest test **KHÔNG bị reject** — chỉ hiện `Warning:` kèm message tương ứng, và audit log/metric (§6.2) ghi nhận vi phạm. Không nhầm với "chưa hoạt động" — đây đúng hành vi Audit/Warn theo thiết kế K8s (không có Event, không fail request).

**Sau khi chuyển sang `[Deny]` (§6 bước 7):** cả 3 manifest test phải bị **reject thật**, kèm message đúng luật vi phạm — đây mới là bằng chứng cuối cùng để nộp cho mentor theo yêu cầu mandate ("apply thử một manifest vi phạm và thấy bị từ chối").

---

## 8. Rollback / Safety

| Tình huống | Rollback | Lý do |
|---|---|---|
| Luật gây warn/audit nhầm workload không mong muốn (hiện tại, chưa Deny) | Sửa `matchExpressions`/`values` loại trừ thêm namespace/workload trong `admission-hardening-bindings.yaml`, merge, để ArgoCD tự áp lại. | Chưa Deny nên chưa có gì bị chặn — sửa qua git là đủ, không cần patch khẩn cấp. |
| Sau khi bật `[Deny]`: luật chặn nhầm workload production | Ngay lập tức: `kubectl patch validatingadmissionpolicybinding <name> --type merge -p '{"spec":{"validationActions":["Audit","Warn"]}}'` — đổi `Deny` → `Audit`, hiệu lực tức thì. Lâu dài: sửa `validationActions` trong `admission-hardening-bindings.yaml`, merge, để ArgoCD tự áp lại. | `kubectl patch` không cần rollout, dùng khi cần dừng khẩn; sửa chart là nguồn sự thật lâu dài (tránh drift). |
| Policy tự lỗi (CEL runtime error, chặn mọi request) | `kubectl delete validatingadmissionpolicybinding <name>` (giữ policy, xóa binding) hoặc `kubectl delete validatingadmissionpolicy <name>` nếu cần gỡ hẳn — sau đó sửa/xoá tương ứng trong chart rồi merge. | Xóa binding đủ để tắt hiệu lực ngay; sửa chart tránh `selfHeal` tạo lại y hệt bug. |
| Cần tắt toàn bộ admission khẩn cấp | `kubectl delete validatingadmissionpolicybinding --all` (4 binding, không đụng Namespace/PVC/PDB khác) — sau đó `git revert` commit liên quan rồi merge để ArgoCD không tạo lại. | Policy nằm trong chart chung, không có file/Application riêng để `kubectl delete -f`; `git revert` là rollback lâu dài đúng. |

**Nguyên tắc:** Không rollback bằng cách sửa `failurePolicy: Fail` → `Ignore` — làm vậy tắt mất bảo vệ khi API server có sự cố khác. Dùng đúng field `validationActions` để hạ enforce xuống audit.

---

## 9. ADR cần ký (giao nộp theo Mandate-05)

Tạo `docs/audit/adr/015-runtime-hardening-admission-policy.md` (tiếp số sau `014-ai-trust-safety-guardrails.md`), nội dung tối thiểu:

- Quyết định: dùng native VAP (không Kyverno/Gatekeeper) — lý do §3.
- Phạm vi: toàn cluster trừ `kube-system`/`kube-node-lease`/`kube-public` — lý do §2.2 (không dùng objectSelector, RBAC là lớp phòng thủ thật cho 3 namespace loại trừ).
- Trạng thái: hiện `[Audit, Warn]`, kế hoạch chuyển `[Deny]` sau khi `argocd`/`external-secrets` có resources và hệ thống quan sát ổn định (§6).
- Người ký: Quân (owner), review: Nguyên.

---

## 10. Coordination

| Role | Người | Trách nhiệm |
|---|---|---|
| Owner | Quân | Viết policy, test manifest, ADR |
| Reviewer | Nguyên | Review CEL rules + rollout plan |
| Review PR #302 | Nguyên | Scope cluster-wide + fix regex — `tf4-phase3-repo` |
| Review + merge PR #31 | CDO-04 | Resources cho `external-secrets` — `tf4-phase3-gitops-manifests` |
| Chạy `helm upgrade` cho `argocd` | CDO-04 | `argocd` không quản lý qua GitOps — cần chạy tay, pin đúng `--version 7.3.7` (verify khớp chart đang chạy trước khi chạy) |
| ✅ Đã xong | #233 (SEC-09) | Rollout `runAsNonRoot` + `capabilities.drop: [ALL]` — 100% sạch ở `techx-tf4` |
| ✅ Đã xong | #235 | Pin busybox init image → `1.36.1` — blocker luật tag đã gỡ |
| ✅ Đã xong | CDO07 (`pho-veteran`, "fix: patch argocd stage 1/2") | Gỡ xung đột `ExternalSecret alertmanager-slack-webhook` (2 ExternalSecret tranh 1 Secret) — xác nhận ArgoCD Application `techx-observability`/`techx-corp` đều `Synced/Healthy/Succeeded`. |
| Thông báo | tf4-leads | Xác nhận trước khi chuyển sang `[Deny]` (ảnh hưởng `techx-tf4` dùng chung toàn TF) |

---

## 11. Definition of Done

- [x] `techx-corp-chart/templates/admission-hardening.yaml` + `admission-hardening-bindings.yaml` — 4 policy + 4 binding, guard theo `.Release.Namespace`, deny-list namespace (`kube-system`/`kube-node-lease`/`kube-public`), regex tag+digest đã sửa.
- [x] AppProject whitelist (`ValidatingAdmissionPolicy`/`Binding`/`Namespace`/`StorageClass`) đã merge.
- [x] Không còn `deploy/admission/runtime-hardening.yaml`/`bootstrap-namespaces.sh` (đã xoá, trùng chức năng với chart).
- [x] Không còn policy `harden-*` cũ trên cluster (đã xoá — không quản lý qua code, tạo tay bởi bên khác, gây nhiễu debug).
- [x] Xung đột `ExternalSecret` của `techx-observability` đã gỡ (CDO07), ArgoCD sync sạch cho cả `techx-corp` và `techx-observability`.
- [ ] Merge PR #302 (`tf4-phase3-repo`) — scope cluster-wide.
- [ ] Merge PR #31 (gitops) — resources `external-secrets`.
- [ ] Chạy `helm upgrade` thủ công cho `argocd` — resources.
- [ ] Verify trên cluster: 8 object tồn tại, `[Audit, Warn]`; bảng compliance §6.1 toàn `✅`.
- [ ] Notification (§6.2) đã bật: alert Prometheus (deny + error_type) → Alertmanager; ArgoCD `on-sync-failed` → Slack.
- [ ] Quan sát ổn định qua kênh audit/warn trong khoảng thời gian đủ tin cậy.
- [ ] Chuyển `validationActions` sang `[Deny]`, merge, verify 3 manifest test bị reject thật.
- [ ] Thông báo tf4-leads; PM cập nhật backlog status.
