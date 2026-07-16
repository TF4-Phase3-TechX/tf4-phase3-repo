# Plan: CDO08-SEC-11 — Enforce runtime hardening policy as code (admission)

**Owner:** Quân
**Reviewer:** Nguyên
**Priority:** P0
**Backlog:** CDO08-SEC-11
**Directive:** MANDATE-05 (Runtime Hardening) — hạn nộp thứ Sáu 17/07/2026
**Ngày:** 2026-07-16

---

## 0. Phạm vi task này (đọc trước khi review)

MANDATE-05 có 4 yêu cầu. Task này **chỉ** làm yêu cầu 4 (đẩy các luật hardening ở req 1–3 vào admission, policy-as-code). Không làm lại yêu cầu 1–3 ở đây. Ba yêu cầu hardening được hiện thực bằng **4 policy CEL** (req 1 tách 2 policy: non-root + drop-capabilities; req 2: image tag; req 3: resources):

| # | Yêu cầu Mandate-05 | Trạng thái hiện tại (đã verify với repo) | Có nằm trong task này không |
|---|---|---|---|
| 1 | Không container chạy root **+ drop capability thừa** | **Đã vào code, đang rollout** — commit **#233 (SEC-09)** thêm `runAsNonRoot` (nay 21 chỗ trong `values.yaml`) + `capabilities.drop` (20 chỗ). Cluster đang deploy dần (§2.1): quá nửa service đã non-root+drop ALL; còn ~12 service (accounting, ad, cart, currency, email, flagd, llm, load-generator, postgresql, recommendation, opensearch, otel-collector) chờ rollout. | Không sửa container (SEC-09 lo). Viết **2 luật** (non-root + drop-capabilities) để **audit**; flip Deny sau khi rollout xong + sweep=0 (§6.1). |
| 2 | Cấm image tag trôi (`latest`) | **Đã xong (sau pull 2026-07-16)** — commit **#235** pin toàn bộ busybox init → `1.36.1`. `values.yaml` **không còn `:latest`/untagged nào**; cluster (§2.1) 0 vi phạm tag. (Trước pull còn `busybox:latest` ở init container — nay đã fix.) | Viết luật, để **audit** trước theo quyết định "chưa deny ngay"; nay **không còn blocker** để flip Deny (§6.1). |
| 3 | Bắt buộc requests/limits | **Đã xong** — verify trên cluster thật (§2.1): **mọi** pod/container ở cả 2 namespace (kể cả grafana, jaeger, opensearch, otel, init container busybox) đều có đủ requests+limits. | Viết luật, để **audit** trước (theo quyết định "chưa deny ngay"); enforce sau full sweep + review. |
| 4 | **Enforce tự động qua admission (policy-as-code)** | Chưa có gì — không `ValidatingAdmissionPolicy`, Kyverno, Gatekeeper, hay webhook nào trong repo. | **Đây là task.** |

**Quyết định phạm vi (2026-07-16): tất cả 4 luật để AUDIT trên namespace production, CHƯA `Deny` cái nào trong tuần này.** Lý do (cập nhật sau pull): resources + tag nay **0 vi phạm** (repo lẫn cluster), có thể flip Deny sớm sau review; non-root + capabilities vừa được SEC-09 (#233) đưa vào code và **đang rollout dở** trên cluster — bật `Deny` khi rollout chưa xong sẽ chặn các service chưa kịp cập nhật. Để mentor **vẫn thấy manifest bị từ chối thật** (yêu cầu bắt buộc của mandate), plan dùng namespace cô lập `techx-admission-test` với binding `Deny` **chỉ** trong namespace đó — production không bị enforce, mentor vẫn thấy reject thật (§5.3, §7).

Vì SEC-09 chưa rollout xong toàn bộ, plan này **không** enforce non-root/capabilities trên production tuần này để tránh chặn service của người khác đang trong quá trình cập nhật — điều này được nêu rõ ở §2.1, §6.1, không giấu.

> **Ghi chú phạm vi (ticket vs mandate):** phần liệt kê "việc cần làm" của ticket SEC-11 (§3) chỉ nêu 3 mục enforce (non-root, image tag, resources), **không** nêu capabilities. Nhưng Mandate-05 #1 ghi rõ *"drop mấy capability thừa"* là một phần của yêu cầu chống-root. Plan này bám theo **mandate** nên có thêm luật `drop-all-capabilities`, để **audit mode** cùng nhóm với non-root (chờ SEC-09 rollout xong), không enforce trong tuần này → không tác động workload đang chạy. Nếu reviewer muốn giới hạn đúng chữ trong ticket, có thể bỏ luật này mà 3 luật còn lại không đổi.

---

## 1. Mục tiêu

Đẩy các luật hardening của Mandate-05 (non-root + drop-capabilities, no mutable tag, resources bắt buộc) vào **admission** — manifest vi phạm bị Kubernetes API server từ chối **ngay lúc apply**, không phụ thuộc người review bằng mắt hay CI (CI có thể bị bypass bởi `kubectl apply` tay, `helm upgrade --set` tay, hoặc PR future không đi qua CI).

**Không mục tiêu:** sửa container hiện có để hết vi phạm root (đó là SEC-09/10). Task này chỉ đảm bảo: (a) hạ tầng admission đã sẵn sàng, 4 policy + binding đã apply; (b) cả 4 luật bật **audit** trên production (`techx-tf4`, `techx-observability`) — chưa `Deny` cái nào; (c) demo **reject thật** trong namespace cô lập `techx-admission-test`; (d) mỗi luật có điều kiện flip sang `Deny` rõ ràng (§6), sẵn sàng enforce mà không cần thêm code mới khi điều kiện thỏa.

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

### 2.1 Verify trực tiếp trên cluster (kubectl, 2026-07-16, cập nhật sau pull)

Quét thật `kubectl get pods -o json` trên `techx-tf4` + `techx-observability` (cluster `techx-tf4-cluster`, EKS 1.34.9) — ground truth, **chính xác hơn** đọc tĩnh `values.yaml`.

> **Bối cảnh thay đổi trong ngày:** lần quét đầu (trước pull) phát hiện tag còn vi phạm ở init container `busybox:latest`/untagged và hầu hết container chạy root. Sau khi pull code mới, hai commit đã về: **#235** (`fix(sec): pin runtime and karpenter images` — pin busybox → `1.36.1`) và **#233** (`[CDO08-SEC-09] Remove root and privilege gaps` — thêm `runAsNonRoot`/`capabilities.drop` diện rộng). Bảng dưới là trạng thái **sau pull**.

| Luật | Kết quả quét (sau pull) | Có chặn nếu `Deny` không? |
|---|---|---|
| **Resources** | ✅ **0 vi phạm** — mọi container/initContainer ở cả 2 namespace đều đủ cpu+memory requests+limits (grafana, jaeger, opensearch, otel, prometheus, metrics-server, alertmanager, load-generator, và init container busybox). | Không chặn ai. |
| **Image tag** | ✅ **0 vi phạm** — #235 pin toàn bộ busybox init → `busybox:1.36.1`; `values.yaml` không còn `:latest`/untagged; cluster cũng 0 vi phạm. **Drift repo↔cluster đã hết.** | Không chặn ai — **không còn blocker để flip Deny**. |
| **Non-root** | ⏳ **Đang rollout (#233)** — repo đã có `runAsNonRoot` (21 chỗ). Cluster đã cập nhật quá nửa: **OK** = checkout, fraud-detection, frontend(-proxy), image-provider, kafka, payment, product-catalog, product-reviews, quote, shipping, valkey-cart, grafana, jaeger, metrics-server, prometheus, alertmanager. **Còn chờ** = accounting, ad, cart, currency, email, flagd, llm, load-generator, postgresql, recommendation, opensearch, otel-collector. | CÓ nếu enforce lúc này (service chưa rollout sẽ bị chặn) → giữ audit tới khi rollout xong. |
| **Capabilities** | ⏳ Tương tự non-root — repo có `drop:` (20 chỗ); cluster theo cùng nhịp rollout (alertmanager non-root OK nhưng chưa drop ALL). | CÓ nếu enforce lúc này → giữ audit. |

**Trả lời câu hỏi "service nào bị ảnh hưởng bởi các luật":**
- **2 luật sắp enforce (resources + tag): KHÔNG service nào bị ảnh hưởng** — cả repo lẫn cluster đều 0 vi phạm. Grafana, Locust (`load-generator`), và toàn bộ app/observability đều pass.
- **2 luật audit (non-root + capabilities):** còn ~12 service trên cluster chưa rollout (danh sách "Còn chờ" ở trên) sẽ *audit-warn*, nhưng **không bị chặn** vì để `[Audit, Warn]`. Khi #233 rollout xong, các service này sẽ hết vi phạm.
- Cần theo dõi riêng: **opensearch, otel-collector** (subchart bên thứ ba) — xác nhận #233 có phủ không, hay cần ghi exception (§5.4).

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

Cả hai đều **đủ năng lực** làm các luật này (không phải vấn đề tính năng). Lý do loại:

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
| **Enforce root khi #233 chưa rollout xong → chặn nhầm service chưa cập nhật** | SEC-09 (#233) đang rollout `runAsNonRoot` dần; tại thời điểm quét còn ~12 service chưa cập nhật (§2.1). Nếu bật `Deny` luật root lúc này, **mọi lần deploy lại** (rolling update do CD, HPA scale, Karpenter consolidate) của các service đó sẽ bị reject → outage. | Luật root **chỉ bật `[Audit, Warn]`**, không `Deny` cho đến khi #233 rollout xong + sweep=0. Đây là *đúng* tinh thần "đi từ audit sang enforce có kiểm soát" mà Mandate-05 yêu cầu. |
| **Enforce sai namespace → ảnh hưởng add-on hệ thống** | VAP mặc định match theo `resourceRules`, nếu không giới hạn namespace sẽ áp cả lên `kube-system`, Karpenter, aws-load-balancer-controller, cert-manager, metrics-server... Những pod này không do TF4 kiểm soát, có thể không tuân luật (vd 1 số add-on chạy root theo thiết kế) → risk brick cluster (add-on không tự phục hồi được → mất autoscaling/ingress/DNS). | Dùng **allow-list qua `namespaceSelector`** thay vì áp cluster-wide: chỉ namespace được gắn label `techx.io/policy-scope: enforced` mới bị áp. Chỉ label `techx-tf4` và `techx-observability`. Không đụng `kube-system` hay namespace add-on khác — không cần deny-list dễ sót. |
| **Enforce lên namespace `techx-tf4` = ảnh hưởng cả TF, không riêng CDO-08** | Không có namespace riêng CDO-08 (xem §2) — mọi luật enforce trên `techx-tf4` tác động toàn bộ 27 service của cả 4 team | Mandate-05 vốn *"Áp dụng: toàn bộ Task Force"* nên về nguyên tắc đây không phải mở rộng phạm vi trái phép — nhưng vẫn cần **thông báo trước cho tf4-leads** trước khi flip bất kỳ luật nào sang `Deny` (không chỉ âm thầm enforce), vì §out-of-scope của task yêu cầu review toàn TF trước khi ảnh hưởng workload team khác. Xem §6 bước thông báo. |
| **`failurePolicy: Fail` làm API server treo nếu policy lỗi** | Nếu CEL expression lỗi runtime (vd field không tồn tại gây exception), `failurePolicy: Fail` sẽ reject luôn request thay vì cho qua | CEL dùng optional-chaining `?.` + `orValue(...)` (xem §5.2) nên không truy cập field vắng mặt → không gây runtime error; test bằng `--dry-run=server` trước khi bind thật (§7). |
| **Tag/resources "đã xong" trên giấy nhưng runtime còn vi phạm** | Bản trước đánh giá req 2, 3 "đã xong" dựa trên đọc `values.yaml` tĩnh — **đã kiểm chứng lại trên cluster (§2.1)**: resources thật sự sạch, nhưng tag **còn vi phạm** ở busybox init container (opensearch/flagd/app) mà đọc tĩnh bỏ sót. | **Đã áp dụng: cả 4 luật để audit, không `Deny` cái nào tuần này.** Tag chỉ flip khi busybox init đã pin; resources flip sau review dù runtime đã sạch (§6.1). Đây chính là lý do phải verify runtime, không tin đọc tĩnh. |

---

## 5. Thiết kế chi tiết

### 5.1 Namespace scope — bootstrap label (one-time, thủ công)

Vì namespace không quản lý qua Terraform (xem §2), bootstrap bằng tay trước khi apply policy:

```bash
# Namespace production — nhận binding AUDIT (không chặn)
kubectl label namespace techx-tf4 techx.io/policy-scope=enforced --overwrite
kubectl label namespace techx-observability techx.io/policy-scope=enforced --overwrite

# Xác nhận KHÔNG label các namespace add-on/hệ thống — allow-list, không phải deny-list
kubectl get ns --show-labels | grep -v "techx-tf4\|techx-observability"
```

> Namespace demo `techx-admission-test` (đã tồn tại sẵn trên cluster, đang rỗng) **không cần label** — binding demo match qua label auto `kubernetes.io/metadata.name`. Tuyệt đối **không** gắn `policy-scope=enforced` cho nó (để binding production không áp) và không deploy workload thật vào đó.

### 5.2 4 `ValidatingAdmissionPolicy` — một file cho mỗi luật

File: `deploy/admission/runtime-hardening.yaml` — deploy **độc lập** (raw manifest, `kubectl apply -f`/ArgoCD app riêng), **KHÔNG** nhúng vào `techx-corp-chart/templates/`: VAP là cluster-scoped, mà chart cài 2 release (app + observability) → nếu nằm trong templates sẽ bị render 2 lần → ownership conflict. Đặt cạnh các raw cluster manifest khác trong `deploy/` (`ingress.yaml`, `quota.yaml`, `karpenter/`).

> **File này CHỈ chứa 4 policy + 4 binding production (Audit)** — 8 object, đây là phần "chuẩn" đứng lâu dài trong repo. Binding `Deny` cho demo mentor **không** nằm trong file này — xem §5.3.

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
# Luật 2 — Mandate-05 #2: cấm image tag trôi
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
  - expression: >
      (object.spec.containers + object.spec.?initContainers.orValue([])).all(c,
        c.image.contains(':') && !c.image.endsWith(':latest'))
    message: "Image must pin a fixed tag or digest (repo:tag or repo@sha256:...); ':latest' or untagged images are not allowed."
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
  # Chỉ enforce phần drop: [ALL]; việc add lại capability cụ thể là quyết định của từng service.
  - expression: >
      (object.spec.containers + object.spec.?initContainers.orValue([])).all(c,
        c.?securityContext.?capabilities.?drop.orValue([]).exists(d, d == 'ALL'))
    message: "Container/initContainer must drop all capabilities: set securityContext.capabilities.drop: [\"ALL\"] (add back only what is required)."
```

> Match ở resource **`pods`** (không phải `deployments`) — vì Pod là nơi containers thực sự được tạo, kể cả pod sinh ra từ Deployment/StatefulSet/Job/CronJob. Đây cũng là cách Kyverno/Gatekeeper thường match cho đúng loại luật này.

> Cả 4 luật gộp `containers` + `initContainers` bằng `object.spec.?initContainers.orValue([])` (optional-chaining của CEL) thay vì viết 2 nhánh `has(...) || initContainers.all(...)` riêng biệt — cùng một điều kiện nhưng không lặp code, và tự động là `[]` (rỗng, `.all()` qua vô nghĩa) khi pod không có initContainers.

> `operations: ["CREATE", "UPDATE"]` (không chỉ `CREATE`) — Mandate-05 #4 yêu cầu "áp cho cả thay đổi sau này". Image tag có thể đổi in-place (`kubectl set image`) và resources có thể đổi qua in-place pod resize (K8s 1.34) — cả hai là `UPDATE`, sẽ lọt nếu chỉ match `CREATE`. Status update của kubelet đi qua subresource `pods/status` (không phải `pods`) nên **không** bị policy này bắt → không gây spam/overhead.

### 5.3 Binding — production AUDIT (trong code) + test namespace DENY (apply thủ công, tách riêng)

Thiết kế 2 nhóm binding cho **cùng 4 policy**, nhưng **KHÔNG cùng một file** — chỉ nhóm production mới là code chuẩn:
- **Nhóm PRODUCTION** (`techx-tf4`, `techx-observability`): cả 4 luật `[Audit, Warn]` — **không chặn** workload đang chạy. Nằm trong `deploy/admission/runtime-hardening.yaml` (§5.2), apply cùng 4 policy.
- **Nhóm DEMO** (namespace cô lập `techx-admission-test`): cả 4 luật `[Deny]` — để mentor apply manifest vi phạm và thấy **reject thật** (yêu cầu mandate), không đụng production. **Không** nằm trong file deploy chuẩn — đây là artifact test, chỉ apply thủ công lúc demo, sống cùng chỗ với 3 manifest vi phạm: `docs/cdo08/week2/sec11-test-manifests/demo-deny-bindings.yaml`. Không wiring vào CI/CD hay ArgoCD.

#### Production bindings — tất cả AUDIT (trong `deploy/admission/runtime-hardening.yaml`)

```yaml
# 4 binding, KHÁC NHAU ở name + policyName, GIỐNG NHAU phần còn lại.
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata: { name: require-run-as-nonroot-binding }
spec:
  policyName: require-run-as-nonroot
  validationActions: [Audit, Warn]   # chờ SEC-09 (#233) rollout xong
  matchResources:
    namespaceSelector:
      matchLabels: { techx.io/policy-scope: enforced }
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata: { name: require-drop-all-capabilities-binding }
spec:
  policyName: require-drop-all-capabilities
  validationActions: [Audit, Warn]   # chờ SEC-09 (#233) rollout xong
  matchResources:
    namespaceSelector:
      matchLabels: { techx.io/policy-scope: enforced }
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata: { name: disallow-mutable-image-tag-binding }
spec:
  policyName: disallow-mutable-image-tag
  validationActions: [Audit, Warn]   # chờ pin busybox init image (§2.1, §6)
  matchResources:
    namespaceSelector:
      matchLabels: { techx.io/policy-scope: enforced }
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata: { name: require-resource-limits-binding }
spec:
  policyName: require-resource-limits
  validationActions: [Audit, Warn]   # runtime đã 0 vi phạm (§2.1); flip Deny sau review
  matchResources:
    namespaceSelector:
      matchLabels: { techx.io/policy-scope: enforced }
```

#### Demo bindings — DENY, chỉ trong `techx-admission-test` (file riêng, apply thủ công)

`docs/cdo08/week2/sec11-test-manifests/demo-deny-bindings.yaml` — 4 binding, lặp cấu trúc, chỉ khác `name` (hậu tố `-deny`) + `policyName`:

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata: { name: disallow-mutable-image-tag-deny }
spec:
  policyName: disallow-mutable-image-tag
  validationActions: [Deny]
  matchResources:
    namespaceSelector:
      # label auto của K8s, không cần gắn tay; giới hạn Deny đúng 1 namespace test.
      matchLabels: { kubernetes.io/metadata.name: techx-admission-test }
# ... 3 binding tương tự cho require-run-as-nonroot / require-drop-all-capabilities /
#     require-resource-limits, cùng namespaceSelector techx-admission-test.
```

Apply/gỡ thủ công (yêu cầu 4 policy ở `deploy/admission/runtime-hardening.yaml` đã tồn tại trước):
```bash
kubectl apply  -f docs/cdo08/week2/sec11-test-manifests/demo-deny-bindings.yaml
kubectl delete -f docs/cdo08/week2/sec11-test-manifests/demo-deny-bindings.yaml
```

> **KHÔNG** gắn label `techx.io/policy-scope: enforced` lên `techx-admission-test` → binding production (audit) không áp vào đó; chỉ binding demo (Deny) áp. Ngược lại, không gắn `kubernetes.io/metadata.name` cho production (label đó do K8s tự set theo tên namespace) nên binding demo không lọt sang production.

### 5.4 Exception policy (workload cần tạm miễn)

Nếu phát sinh workload hợp lệ nhưng cần audit tạm (vd job debug 1 lần, add-on nội bộ chưa kịp hardening), miễn trừ bằng `objectSelector` **ở binding**, không sửa policy gốc:

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

Workload cần miễn tạm thời gắn label `techx.io/admission-exempt: "true"` + **bắt buộc** ghi lý do + ngày hết hạn miễn trừ vào ADR-015 (§9) — không miễn trừ âm thầm không thời hạn.

---

## 6. Rollout — audit → enforce có kiểm soát

### 6.0 Phase 1 (tuần này) — tất cả AUDIT trên production + DENY demo trong test namespace

| Bước | Việc | Kết quả kỳ vọng |
|---|---|---|
| 1 | Label 2 namespace production (§5.1); **không** label `techx-admission-test` | 2 ns có label `policy-scope=enforced`, không ns add-on/hệ thống nào bị dính |
| 2 | Apply `deploy/admission/runtime-hardening.yaml` — 4 `ValidatingAdmissionPolicy` + 4 binding **production** `[Audit, Warn]` (§5.2, §5.3) | `kubectl get validatingadmissionpolicy,validatingadmissionpolicybinding` thấy đủ 8; không chặn workload nào; audit annotation bắt đầu ghi nhận vi phạm |
| 3 | (Chỉ lúc demo) Apply thủ công `docs/cdo08/week2/sec11-test-manifests/demo-deny-bindings.yaml` — 4 binding `[Deny]` scope `techx-admission-test` (§5.3) | Sẵn sàng cho mentor apply manifest vi phạm → thấy reject thật; gỡ lại sau demo nếu không cần giữ |
| 4 | **Full sweep** ghi nhận vi phạm hiện tại theo từng luật (input cho §6.1) | Report: tag còn busybox init (6 svc), root/caps còn nhiều, resources = 0 |
| 5 | Thông báo tf4-leads/Nguyên: admission đã lên **audit-only** trên production, demo Deny ở test ns (thủ công, riêng) | Có xác nhận review; không ai bị chặn |

**Không có bước nào flip production sang `Deny` trong Phase 1.** (Giữ nguyên nguyên tắc "chưa deny ngay" dù resources + tag nay đã 0 vi phạm — vẫn cần review tf4-leads trước khi flip.)

### 6.1 Phase 2 (follow-up) — flip từng luật sang `Deny`, mỗi luật một điều kiện riêng

Cập nhật sau pull 2026-07-16: #235 đã pin busybox (tag hết blocker), #233 (SEC-09) đang rollout non-root/caps.

| Luật | Điều kiện BẮT BUỘC trước khi flip production sang `[Deny]` | Trạng thái | Ai lo |
|---|---|---|---|
| **Resources** | Full sweep = 0 vi phạm (đã đạt) **+** review tf4-leads. | ✅ **Sẵn sàng flip** — chỉ chờ review. | Quân |
| **Image tag** | Repo + cluster 0 vi phạm tag (busybox đã pin qua #235). | ✅ **Sẵn sàng flip** — blocker busybox đã hết; chờ review cùng resources. | Quân |
| **Non-root** | #233 (SEC-09) **rollout xong** trên cluster; sweep = 0 (12 service "Còn chờ" ở §2.1 đã cập nhật); xác nhận opensearch/otel-collector (subchart) hoặc có exception (§5.4). | ⏳ Đang rollout | SEC-09 owner + Quân |
| **Capabilities** | Như non-root: rollout `capabilities.drop: [ALL]` xong; sweep = 0. | ⏳ Đang rollout | SEC-09 owner + Quân |

Mỗi lần flip: đổi đúng 1 field `validationActions: [Audit, Warn]` → `[Deny]` trên binding production tương ứng, sau khi dry-run `helm template ... | kubectl apply --dry-run=server` không bị reject + thông báo tf4-leads.

Vì hạn Mandate-05 là 17/07/2026 (ngày mai), **Phase 1 làm trong hôm nay** (đủ để nộp: admission đã lên, demo reject thật, evidence vi phạm rõ ràng). Phase 2 là follow-up có điều kiện — ADR (§9) ghi rõ luật nào chưa enforce và vì sao, đúng định dạng "Phải nộp" của mandate ("luật nào enforce, luật nào audit và vì sao").

### 6.2 Observability & Notification — làm sao biết khi có warn/deny

Vì Phase 1 để **tất cả luật ở audit**, nếu không có kênh quan sát thì audit = **mù** (không ai thấy vi phạm). Mỗi loại `validationActions` surface ra một kênh khác nhau — phải bắt đủ cả ba:

| Action | Surface ở đâu | Kênh nhận thông báo (tận dụng component có sẵn) |
|---|---|---|
| **Deny** | API reject → **ArgoCD sync fail** | **ArgoCD Notifications** (`argocd-notifications-controller` đang chạy): trigger `on-sync-failed`/`on-health-degraded` → Slack/webhook, kèm message reject của VAP. Thêm alert Prometheus `argocd_app_info{sync_status="OutOfSync"}`. |
| **Warn** | Warning header trên API response (không fail) | Hiện trong `argocd app get`/UI (sync condition) và `kubectl` stderr. Không tự bắn alert → dựa vào metric bên dưới. |
| **Audit** | **Chỉ** API server audit log + metric (KHÔNG có Event, KHÔNG về client) | (a) metric API server (dưới); (b) EKS control-plane audit log → CloudWatch (ADR-005 đã bật) → filter annotation `validation.policy.admission.k8s.io/validation_failure` → CloudWatch alarm/SNS. |

**Nguồn tin cậy nhất — metric API server** (phủ cả deny + audit + lỗi CEL, độc lập ArgoCD). Prometheus (đã chạy) scrape `https://kubernetes.default.svc/metrics`, alert qua Alertmanager (đã chạy):

```
# Có vi phạm bị policy đánh trượt (deny hoặc would-deny ở audit):
sum by (policy) (rate(apiserver_validating_admission_policy_check_total{enforcement_action="deny"}[5m])) > 0

# Policy tự lỗi CEL runtime (nguy hiểm — cần bắt sớm, nhất là khi failurePolicy: Fail):
sum by (policy) (rate(apiserver_validating_admission_policy_check_total{error_type!="no_error"}[5m])) > 0
```

> Cần xác nhận Prometheus của cluster có quyền RBAC scrape endpoint `/metrics` của kube-apiserver (metric `apiserver_validating_admission_policy_*` chỉ có từ đó). Nếu chưa, thêm ServiceMonitor/scrape config + RBAC `nonResourceURLs: ["/metrics"]` cho SA của Prometheus — đây là việc nhỏ, không thêm hạ tầng.

**Khuyến nghị tối thiểu cho Phase 1:** (1) alert Prometheus theo 2 rule trên → Alertmanager; (2) khi sang Phase 2 (flip Deny) bật thêm ArgoCD `on-sync-failed`. Có (1) thì audit mode mới thực sự "thấy" được vi phạm để lấy evidence và để biết khi nào đủ điều kiện flip (§6.1).

---

## 7. Manifest test vi phạm — cho mentor apply

**Điều kiện trước:** đã apply `deploy/admission/runtime-hardening.yaml` (§5.2/§5.3) **và** apply thủ công `docs/cdo08/week2/sec11-test-manifests/demo-deny-bindings.yaml` (§5.3) để namespace `techx-admission-test` có binding `Deny`.

3 file test, namespace **`techx-admission-test`**, dùng image công khai (`nginx`) để không phụ thuộc registry nội bộ. Áp vào đây để thấy **reject thật** mà không chạm production:

`docs/cdo08/week2/sec11-test-manifests/bad-root-pod.yaml`
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: sec11-test-bad-root
  namespace: techx-admission-test
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
  namespace: techx-admission-test
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
  namespace: techx-admission-test
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

> Manifest tag + missing-resources cố tình set sẵn `runAsNonRoot` + `capabilities.drop: [ALL]` để **cô lập** đúng một luật vi phạm — mentor thấy rõ luật nào reject, không lẫn với luật khác.

### Verification

```bash
kubectl get validatingadmissionpolicy,validatingadmissionpolicybinding

# (1) DEMO REJECT — apply vào techx-admission-test (binding Deny) → cả 3 kỳ vọng BỊ REJECT
kubectl apply --server-side --dry-run=server -f docs/cdo08/week2/sec11-test-manifests/bad-root-pod.yaml
kubectl apply --server-side --dry-run=server -f docs/cdo08/week2/sec11-test-manifests/bad-latest-tag-pod.yaml
kubectl apply --server-side --dry-run=server -f docs/cdo08/week2/sec11-test-manifests/missing-resources-pod.yaml
# → mỗi lệnh trả error kèm message tương ứng (runAsNonRoot / image tag / requests+limits)

# (2) PRODUCTION AUDIT — cùng manifest nhưng đổi namespace sang techx-tf4 (binding Audit)
#     → KHÔNG bị reject (chứng minh production không bị chặn); chỉ trả warning header.
sed 's/namespace: techx-admission-test/namespace: techx-tf4/' \
  docs/cdo08/week2/sec11-test-manifests/bad-root-pod.yaml \
  | kubectl apply --server-side --dry-run=server -f -
# ⚠️ audit-mode KHÔNG tạo Event object → `kubectl get events` sẽ RỖNG, đừng dùng.
#    Vi phạm audit chỉ ghi vào API server audit log (annotation
#    validation.policy.admission.k8s.io/validation_failure) + metric apiserver_validating_admission_policy_check_total.
#    Cách nhận thông báo audit/warn/deny: xem §6.2.

# (3) PRE-FLIP GATE — chạy TRƯỚC khi flip một luật sang Deny (Phase 2).
#     Render workload thật rồi dry-run trong namespace test (binding Deny) để chắc KHÔNG bị reject.
helm template techx-corp ./techx-corp-chart -n techx-admission-test -f deploy/values-app-stamp.yaml -f deploy/values-flagd-sync.yaml \
  | kubectl apply --server-side --dry-run=server -f -
# Hiện tại: resources + tag sạch (busybox đã pin qua #235) → pass; non-root/caps còn service
# chờ #233 rollout → sẽ báo, đó là lý do 2 luật đó chưa flip (§6.1).
```

**Điểm cần nói rõ với mentor (không giấu):**
- Trong `techx-admission-test` (Deny): cả 3 manifest **bị reject thật** — mentor tận mắt thấy, thỏa yêu cầu "apply thử một manifest vi phạm và thấy bị từ chối" của mandate.
- Trên **production** (`techx-tf4`/`techx-observability`): cả 4 luật đang **audit-only**, không chặn workload nào — có chủ đích (§0). Sau pull: resources + tag đã 0 vi phạm; non-root + caps còn vi phạm ở ~12 service đang chờ #233 rollout (§2.1). Vi phạm audit **không** hiện qua `kubectl get events` — theo dõi qua metric/audit log (§6.2).
- Do đó nửa sau của mandate ("cluster không còn workload vi phạm") **chưa đạt tuần này** — nêu thẳng, không claim vượt thực tế; điều kiện đạt nằm ở §6.1.

---

## 8. Rollback / Safety

Phase 1 (tuần này) không enforce production nên **gần như không có gì để rollback** — binding production là audit, không chặn ai. Bảng dưới áp dụng cho Phase 2 (sau khi flip `Deny`) và cho binding demo:

| Tình huống | Rollback | Lý do chọn cách này |
|---|---|---|
| (Phase 2) Sau khi flip `Deny`, luật chặn nhầm workload production | `kubectl patch validatingadmissionpolicybinding <name> --type merge -p '{"spec":{"validationActions":["Audit","Warn"]}}'` — đổi ngay `Deny` → `Audit` | Không cần xóa policy, không mất lịch sử vi phạm đang audit, revert 1 field, có hiệu lực ngay (admission là đồng bộ, không cần rollout) |
| Policy tự nó lỗi (CEL runtime error, chặn mọi request) | `kubectl delete validatingadmissionpolicybinding <name>` (giữ policy, xóa binding) hoặc `kubectl delete validatingadmissionpolicy <name>` nếu cần gỡ hẳn | Xóa binding là đủ để tắt hiệu lực — không cần đụng workload đang chạy |
| Cần tắt toàn bộ admission khẩn cấp | `kubectl delete -f deploy/admission/runtime-hardening.yaml` | 4 policy + 4 binding production nằm 1 file — rollback 1 lệnh, không ảnh hưởng app release (deploy tách rời) |
| Cần tắt binding demo sau khi test xong | `kubectl delete -f docs/cdo08/week2/sec11-test-manifests/demo-deny-bindings.yaml` | File riêng, không đụng production; xoá không ảnh hưởng 4 policy hay binding audit |

**Nguyên tắc:** Không bao giờ rollback bằng cách sửa `failurePolicy: Fail` → `Ignore` để "cho qua tạm" — làm vậy tắt mất bảo vệ khi API server có sự cố khác, dùng đúng field `validationActions` để hạ enforce xuống audit thay vì tắt failurePolicy.

---

## 9. ADR cần ký (giao nộp theo Mandate-05)

Tạo `docs/audit/adr/015-runtime-hardening-admission-policy.md` (tiếp số sau `014-ai-trust-safety-guardrails.md`), nội dung tối thiểu theo đúng yêu cầu "Phải nộp" của mandate:

- Trạng thái tuần này: **cả 4 luật audit** trên production, demo `Deny` trong `techx-admission-test` — kèm lý do vì sao chưa enforce (resources + tag đã 0 vi phạm, sẵn sàng flip sau review; non-root + capabilities chờ SEC-09 #233 rollout xong).
- Điều kiện cụ thể để flip **từng luật** sang enforce (bảng §6.1): resources + tag (sweep=0, đã đạt — chờ review) → non-root + capabilities (SEC-09 #233 rollout xong).
- Người ký: Quân (owner), review: Nguyên.

---

## 10. Coordination

| Role | Người | Trách nhiệm |
|---|---|---|
| Owner | Quân | Viết + apply policy, test manifest, ADR |
| Reviewer | Nguyên | Review CEL rules + rollout plan trước khi flip `Deny` |
| Phụ thuộc | SEC-09 owner (#233) | Rollout `runAsNonRoot` + `capabilities.drop: [ALL]` cho ~12 service còn lại (§2.1) — điều kiện flip luật non-root + capabilities |
| ✅ Đã xong | #235 | Pin busybox init image → `1.36.1` — blocker luật tag đã được gỡ |
| Thông báo | tf4-leads | Xác nhận trước mỗi lần flip `Deny` (ảnh hưởng namespace `techx-tf4` dùng chung toàn TF) |

---

## 11. Definition of Done

- [ ] `deploy/admission/runtime-hardening.yaml` (4 `ValidatingAdmissionPolicy` + 4 binding production Audit — **không** kèm binding demo) apply thành công
- [ ] Namespace `techx-tf4` và `techx-observability` đã label `techx.io/policy-scope=enforced`; `techx-admission-test` **KHÔNG** label; không namespace hệ thống/add-on nào bị dính
- [ ] **Cả 4 luật ở `[Audit, Warn]` trên production** — không chặn workload nào (đúng quyết định "chưa deny ngay")
- [ ] `docs/cdo08/week2/sec11-test-manifests/demo-deny-bindings.yaml` (4 binding Deny, scope `techx-admission-test`) apply **thủ công** riêng, chỉ lúc demo — không nằm trong deploy chuẩn
- [ ] 3 manifest test apply vào `techx-admission-test` → **cả 3 bị reject thật** (mentor thấy tận mắt, thỏa mandate)
- [ ] Cùng manifest apply vào `techx-tf4` → **không** bị reject (production an toàn); vi phạm audit theo dõi qua metric/audit log (§6.2), KHÔNG qua `kubectl get events`
- [ ] `helm template` dry-run: resources + tag sạch (busybox đã pin #235); non-root/caps còn báo cho service chờ #233 rollout (bằng chứng cho §6.1)
- [ ] **Notification (§6.2) đã bật:** alert Prometheus trên `apiserver_validating_admission_policy_check_total` (deny + error_type) → Alertmanager; xác nhận Prometheus có RBAC scrape `/metrics` của apiserver
- [ ] Full sweep runtime ghi nhận vi phạm theo từng luật (input cho điều kiện flip §6.1)
- [ ] ADR-015 ký tên (Quân) + review (Nguyên): 4 luật audit, demo Deny, điều kiện flip từng luật
- [ ] Thông báo tf4-leads: admission đã lên audit-only trên production, demo Deny ở test ns
- [ ] PM cập nhật backlog status
