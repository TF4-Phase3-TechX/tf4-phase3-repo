# CDO08-SEC-11 — Mentor PoC Incident Report & Remediation

**Ngày phát hiện:** 2026-07-20
**Người điều tra + vá:** Quân
**Liên quan:** `techx-corp-chart/templates/admission-hardening.yaml`, `admission-hardening-bindings.yaml` (Mandate-05 / CDO08-SEC-11)

---

## 1. Tóm tắt

Mentor dùng một account có quyền cao, `kubectl apply` **trực tiếp vào cluster** (không qua GitOps/PR — không có `ownerReferences`, có `kubectl.kubernetes.io/last-applied-configuration`), tạo 3 pod PoC trong namespace `techx-tf4`, label `poc: mandate05-lab`, thời điểm **2026-07-19 17:24:18Z – 17:42:51Z**. Cả 3 pod đều **pass được 4 luật admission `[Deny]` đang enforce** (`require-run-as-nonroot`, `disallow-mutable-image-tag`, `require-resource-limits`, `require-drop-all-capabilities`), sau đó khai thác đúng những gap nằm **ngoài phạm vi** 4 luật đó.

## 2. Chi tiết 3 pod

### 2.1 `poc-privileged` — `securityContext.privileged: true`

- Set đủ `runAsNonRoot: true`, `runAsUser: 1000`, `capabilities.drop: [ALL]` → **pass cả 4 luật**.
- Cũng set `privileged: true` — không luật nào kiểm tra field này.
- Script bên trong (giải mã từ `command`, base64): đếm số raw block device (`nvme`/`xvd`/`sd`/`dm-`/`loop`) thấy được trong `/dev`. Kết quả thật khi chạy: thấy được → in `"[!] RESULT: this container was admitted running in PRIVILEGED mode."`, giải thích: truy cập trực tiếp disk node, load được kernel module → tương đương root trên worker node → severity CRITICAL.

### 2.2 `poc-hostesc` — `hostNetwork: true` + `hostPID: true` + `hostPath: /` → `/host`

- Cũng đủ `runAsNonRoot`, `runAsUser: 1000`, `capabilities.drop: [ALL]`, `allowPrivilegeEscalation: false`, `seccompProfile: RuntimeDefault` → **pass cả 4 luật**.
- Không luật nào kiểm tra `hostNetwork`/`hostPID`/`hostPath` volume.
- Script thực hiện 2 đòn:
  - **Leg A:** gọi IMDS (`169.254.169.254`) qua `hostNetwork` → lấy được IAM role + credentials tạm thời **của chính EC2 worker node**.
  - **Leg B:** đọc `/host/etc/os-release`, `/host/etc/hostname`, đếm thư mục pod khác trong `/host/var/lib/kubelet/pods` qua hostPath mount `/` → xác nhận cô lập container-to-host vỡ hoàn toàn.

### 2.3 `poc-debug-target` + ephemeral container injected qua `kubectl debug`

- Pod gốc **hoàn toàn compliant**, pass cả 4 luật lúc CREATE.
- Sau đó có ephemeral container `debug-poc` bị inject vào (đúng nghĩa đen "**inject**" trong tin nhắn mentor) — đang `Running`, `uid=0/gid=0` (root), image `busybox:latest` (tag `:latest` — thứ `disallow-mutable-image-tag` lẽ ra phải cấm).
- Nguyên nhân: `matchConstraints.resourceRules` của cả 4 policy chỉ khai `resources: ["pods"]`, **không khai `pods/ephemeralcontainers"`** — request qua subresource này không bị bất kỳ policy nào match, nên không được validate.

## 3. Nguyên nhân gốc

4 luật hiện tại chỉ đúng 4 điều Mandate-05 liệt kê (non-root, drop-caps, tag cố định, resource limits) — **không phải pod security policy toàn diện**. Không policy nào kiểm tra `privileged`, `hostNetwork`/`hostPID`/`hostIPC`, hoặc match `pods/ephemeralcontainers`. Đây là giới hạn phạm vi đã biết trước (ghi trong plan gốc §1: "Không thuộc phạm vi: ..."), không phải lỗi cấu hình mới phát sinh.

## 4. Đã vá (nhánh `fix/admission-privileged-hostns-ephemeral`, chưa tạo PR)

### 4.1 Đóng gap ephemeral container (leg 2.3)

Thêm `"pods/ephemeralcontainers"` vào `matchConstraints.resourceRules.resources` của 3 policy: `require-run-as-nonroot`, `disallow-mutable-image-tag`, `require-drop-all-capabilities` — mỗi policy thêm 1 validation mới cho `object.spec.ephemeralContainers` (cùng logic effective-override như containers/initContainers đã có).

Đã thêm thêm cả cho `require-digest-image-reference` (policy SEC-17, hiện chưa enforce ở namespace nào — không có blast radius) vì ephemeral container không bị K8s cấm set `image` theo digest (khác với `require-resource-limits` bên dưới).

**`require-resource-limits` — cố ý không thêm ephemeralcontainers.** Xác nhận qua `kubectl explain pod.spec.ephemeralContainers.resources`: *"Resources are not allowed for ephemeral containers. Ephemeral containers use spare resources already allocated to the pod."* — đây là giới hạn cứng của chính K8s API. Nếu thêm check `has(c.resources)...`, điều kiện không bao giờ pass được với bất kỳ ephemeral container nào → chặn luôn 100% `kubectl debug` hợp lệ, không chỉ hành vi lạm dụng. Không phải bỏ sót.

### 4.2 Đóng gap privileged + host namespace (leg 2.1, một phần leg 2.2)

Policy mới `disallow-privileged-and-host-access` (+ binding cùng tên, deny-list namespace giống 4 policy kia, `[Deny]` — enforce ngay, không staged như SEC-17):

```yaml
validations:
- expression: >
    !object.spec.?hostNetwork.orValue(false) &&
    !object.spec.?hostPID.orValue(false) &&
    !object.spec.?hostIPC.orValue(false)
  message: "Pod must not use hostNetwork, hostPID, or hostIPC."
- expression: >
    object.spec.containers.all(c, !c.?securityContext.?privileged.orValue(false))
  message: "Container must not run privileged."
# ... + initContainers, + ephemeralContainers cùng logic
```

### 4.3 Verify không phá vỡ workload thật đang chạy

Render lại toàn bộ 2 release thật (`techx-corp` namespace `techx-tf4`, `techx-observability` namespace `techx-observability`, đúng values file CI dùng):

```
helm template techx-corp ./techx-corp-chart -n techx-tf4 --set default.image.repository=... --set default.image.tag=preview -f deploy/values-app-stamp.yaml -f deploy/values-flagd-sync.yaml -f deploy/values-aio-llm.yaml
helm template techx-observability ./techx-corp-chart -n techx-observability -f deploy/values-observability.yaml
```

Kết quả: `privileged: true` / `hostNetwork: true` / `hostPID: true` / `hostIPC: true` — **0 chỗ nào dùng thật** trong cả 2 render. An toàn để enforce ngay `[Deny]`.

## 5. Gap `hostPath` — ĐÃ VÁ (chọn hướng 2 sau khi so sánh tradeoff)

**Ban đầu `hostPath` volume chưa bị cấm trong patch §4.** Lý do: render thật `techx-observability` cho thấy `opentelemetry-collector` (subchart, DaemonSet agent) có mount hợp lệ:

```yaml
volumes:
  - name: hostfs
    hostPath:
      path: /
volumeMounts:
  - name: hostfs
    mountPath: /hostfs
    readOnly: true
```

Đây là pattern chuẩn của OTel Collector host-metrics receiver — cần đọc `/proc`, `/sys`, disk usage của node. Nếu cấm `hostPath` tuyệt đối như dự định ban đầu, **sẽ chặn luôn DaemonSet này khi rollout/redeploy tiếp theo**, hỏng observability thật.

**Lưu ý quan trọng:** `readOnly: true` **không đóng được leg 2.2's Leg B** (`poc-hostesc` chỉ đọc dữ liệu — `/etc/os-release`, danh sách thư mục pod khác — không cần ghi) — cho phép "hostPath read-only" vẫn để lộ nguyên vẹn đường exfiltrate dữ liệu node/pod khác. Nên đây không phải chỗ có thể "vá nhẹ nhàng" — đã cân nhắc 3 hướng sau trước khi chọn (§5.1):

1. Chấp nhận rủi ro tạm thời (không cấm hostPath), ghi vào backlog riêng.
2. Cấm hostPath chỉ ở `techx-tf4` (namespace app, không có nhu cầu hostPath hợp lệ nào), giữ `techx-observability` ngoại lệ — cần binding riêng theo namespace thay vì dùng chung 1 binding cho cả 2.
3. Dùng `objectSelector` miễn trừ đúng DaemonSet `opentelemetry-collector-agent` (theo label), cấm hostPath cho mọi pod khác.

### 5.1 So sánh tradeoff 3 hướng

| Tiêu chí | 1. Không cấm (backlog) | 2. Cấm theo namespace (loại `techx-observability`) | 3. Miễn trừ theo `objectSelector`/label |
|---|---|---|---|
| Đóng được leg 2.2 (Leg B — đọc filesystem node) ở `techx-tf4` | ✅ Không, vẫn mở nguyên | ✅ Có, đóng hoàn toàn ở `techx-tf4` | ✅ Có, đóng ở mọi pod không mang đúng label |
| Đóng được leg 2.2 ở `techx-observability` | ❌ Không | ❌ Không (cả namespace được miễn trừ, không chỉ 1 DaemonSet) | ⚠️ Về lý thuyết có, nhưng xem dòng dưới |
| Có bị spoof/giả mạo được không | N/A (không có luật để né) | Không thể spoof — namespace là biên giới RBAC thật, không phải field tự khai trong manifest | **Có** — label là dữ liệu do chính người tạo pod tự khai; bất kỳ ai có quyền `create pods` trong namespace được miễn trừ đều tự gắn được đúng label (`app.kubernetes.io/name: opentelemetry-collector`) lên pod độc hại của họ để né luật. Dùng `serviceAccountName` thay label cũng cùng vấn đề trừ khi có thêm RBAC hạn chế ai được dùng SA đó. |
| Độ phức tạp triển khai | Thấp nhất (không đổi gì) | Trung bình — cần tách binding riêng theo namespace thay vì 1 binding chung cho `techx-tf4` + `techx-observability` | Trung bình — thêm `objectSelector` vào binding, nhưng an toàn thật lại thấp hơn cả độ phức tạp bỏ ra |
| Phạm vi bị "hở" còn lại sau khi áp dụng | Toàn bộ (`techx-tf4` + `techx-observability`) | Chỉ `techx-observability` (biết rõ, có giới hạn) | Toàn bộ namespace được miễn trừ, **cộng thêm** bất kỳ pod nào tự gắn label giả trong namespace đó — phạm vi hở thực tế **rộng hơn** cách 2, dù nhìn code tưởng "chặt" hơn |
| Khuyến nghị | Chỉ tạm thời, phải có deadline theo dõi | **Khuyến nghị** — đơn giản, không spoof được, phạm vi hở rõ ràng và nhỏ | Không khuyến nghị dùng một mình — chỉ an toàn nếu kết hợp thêm RBAC chặn ai được tạo pod mang label/SA đó, tăng thêm độ phức tạp không tương xứng lợi ích |

### 5.2 Đã chọn hướng 2 — implement

Policy mới `disallow-hostpath-volumes` + binding riêng, dùng `append` để loại trừ thêm `techx-observability` chỉ cho đúng binding này (không đụng `$excludedNamespaces` dùng chung với 5 binding còn lại):

```yaml
# admission-hardening.yaml
- expression: >
    !object.spec.?volumes.orValue([]).exists(v, has(v.hostPath))
  message: "Pod must not mount a hostPath volume."
```

```yaml
# admission-hardening-bindings.yaml
metadata:
  annotations:
    techx.io/exception-note: "techx-observability excluded — otel-collector-agent DaemonSet needs hostPath:/ readonly for host metrics."
  name: disallow-hostpath-volumes-binding
spec:
  policyName: disallow-hostpath-volumes
  validationActions: [Deny]
  matchResources:
    namespaceSelector:
      matchExpressions:
      - key: kubernetes.io/metadata.name
        operator: NotIn
        values: {{ (append $excludedNamespaces "techx-observability") | toYaml | nindent 8 }}
```

**Verify lại toàn bộ 4 workload thật sau khi thêm** (không chỉ 2 như lần trước — bổ sung `argocd`/`external-secrets`):

| Namespace | `privileged`/`hostNetwork`/`hostPID`/`hostIPC` thật | `hostPath` thật |
|---|---|---|
| `techx-tf4` | 0 | 0 |
| `techx-observability` | 0 | 1 (otel-collector-agent — namespace được loại trừ, chấp nhận) |
| `argocd` | 0 | 0 |
| `external-secrets` | 0 | 0 |

**Rủi ro còn lại đã biết, chấp nhận có chủ đích:** `techx-observability` vẫn cho phép hostPath ở mọi pod trong namespace đó (không chỉ riêng `otel-collector-agent`) — nếu muốn thu hẹp thêm, có thể giới hạn path mount thật của `otel-collector-agent` (hiện là `/` — toàn bộ ổ đĩa gốc, rộng hơn mức cần) qua values override của subchart, nhưng đây là việc khác (chart config), không nằm trong policy CEL này.

## 6. Chưa làm — cần xác nhận thêm

- [ ] Chưa merge/apply lên cluster thật — chỉ mới `helm template` + render-check cục bộ.
- [ ] Chưa test `--dry-run=server` với chính 3 manifest PoC gốc để xác nhận bị Deny sau khi vá (cần build lại 3 manifest test tương đương, không dùng nguyên bản có `sleep infinity`).
- [ ] **3 pod PoC (`poc-privileged`, `poc-hostesc`, `poc-debug-target`) vẫn còn sống trên cluster** — chưa xoá, giữ làm bằng chứng chờ quyết định.
- [ ] Chưa tạo PR.
