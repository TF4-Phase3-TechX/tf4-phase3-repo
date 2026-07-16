# ADR-015: Runtime Hardening bằng Admission Policy-as-Code (ValidatingAdmissionPolicy)

**Ngày:** 2026-07-16
**Trạng thái:** Proposed (chờ review Nguyên + tf4-leads)
**Người quyết định:** CDO-08 (Security + Reliability) — Quân
**Người review:** Nguyên (CDO-08), tf4-leads
**Pillar liên quan:** Security, Operational Excellence, Cost Optimization
**Source:** `deploy/admission/sec11-runtime-hardening-vap.yaml`, `docs/cdo08/week2/CDO08-SEC-11-runtime-hardening-admission-plan.md`
**Refs:** MANDATE-05 (Runtime Hardening), CDO08-SEC-11, SEC-09 (#233), image pin (#235)

---

## 1. Bối cảnh (Context)

Mandate-05 yêu cầu chặn manifest nguy hiểm **ngay lúc apply** (không rà tay): container chạy root, image tag trôi (`latest`/untagged), thiếu resources requests/limits. Trước task này cluster **không có** admission policy nào (không Kyverno/Gatekeeper/VAP). Cluster là EKS **1.34** — `ValidatingAdmissionPolicy` (VAP) đã GA từ 1.30.

Hệ thống đang **production** (khách thật), namespace `techx-tf4` dùng chung cho cả 4 team TF4; observability ở `techx-observability`. Không có namespace riêng cho CDO-08.

---

## 2. Quyết định (Decision)

**Dùng native Kubernetes `ValidatingAdmissionPolicy` (VAP)** — không cài Kyverno/Gatekeeper.

- **4 policy CEL** cho 3 yêu cầu hardening (req 1 tách 2 policy): `sec11-no-root-containers`, `sec11-drop-all-capabilities`, `sec11-no-mutable-image-tag`, `sec11-resources-required`. Match `pods`, `operations: [CREATE, UPDATE]`, `failurePolicy: Fail`.
- **Scope qua namespace label** allow-list `techx.io/policy-scope: enforced` (chỉ `techx-tf4`, `techx-observability`) — không đụng `kube-system`/add-on.
- **Deploy độc lập** tại `deploy/admission/sec11-runtime-hardening-vap.yaml`, **KHÔNG** nhúng vào `techx-corp-chart/templates/` (chart cài 2 release → cluster-scoped object bị render 2 lần → ownership conflict).

**Lý do chọn VAP** (tradeoff đầy đủ ở plan §3): cluster 1.34 đã đủ (GA); zero chi phí hạ tầng thêm (đúng ràng buộc Mandate-05 "không dựng thêm service"); ít điểm lỗi hơn webhook engine; nhu cầu hiện tại chỉ là validate field Pod spec — không cần mutate/generate.

---

## 3. Luật nào ENFORCE, luật nào AUDIT — và vì sao (bắt buộc theo Mandate-05)

| Luật | Trạng thái tuần này | Lý do | Điều kiện flip `Deny` |
|---|---|---|---|
| **resources-required** | Audit | Runtime đã 0 vi phạm (verify cluster §2.1), nhưng theo quyết định "chưa deny ngay" → chờ review | Review tf4-leads |
| **no-mutable-image-tag** | Audit | 0 vi phạm sau khi #235 pin busybox init → `1.36.1` | Review tf4-leads (blocker busybox đã hết) |
| **no-root-containers** | Audit | SEC-09 (#233) đang rollout `runAsNonRoot`; còn ~12 service chưa cập nhật trên cluster | #233 rollout xong + full sweep = 0 |
| **drop-all-capabilities** | Audit | Như trên (`capabilities.drop: [ALL]` theo cùng nhịp #233) | #233 rollout xong + full sweep = 0 |

**Cả 4 luật để `[Audit, Warn]` trên production** (không chặn workload nào). Bật `[Deny]` **chỉ** trong namespace cô lập `techx-admission-test` để mentor apply manifest vi phạm và thấy **reject thật** (thỏa Mandate-05 "tận mắt thấy bị từ chối") mà không đụng production.

> **Nửa sau của Mandate-05** ("cluster không còn workload vi phạm") **chưa đạt tuần này**: non-root/capabilities còn vi phạm ở các service đang chờ #233 rollout. Nêu thẳng, không claim vượt thực tế.

---

## 4. Cắt chuyển Audit → Enforce (không chặn nhầm đồ thật)

1. Apply 4 policy + 8 binding (4 production Audit + 4 demo Deny).
2. Theo dõi vi phạm qua **metric API server** `apiserver_validating_admission_policy_check_total` → Prometheus/Alertmanager (plan §6.2) — audit-mode không tạo Event, phải dùng metric/audit-log.
3. Flip từng luật `[Audit, Warn]` → `[Deny]` khi điều kiện §3 thỏa, sau dry-run `helm template ... | kubectl apply --dry-run=server` không reject + thông báo tf4-leads.
4. Rollback: patch `validationActions` về `[Audit, Warn]` (hiệu lực ngay), hoặc `kubectl delete -f` cả file.

---

## 5. Trạng thái verify

- ✅ YAML hợp lệ: 12 document (4 policy + 8 binding), mọi `policyName` của binding trỏ đúng policy tồn tại; `kubectl create --dry-run=client` pass cả 12.
- ⚠️ **Chưa** server-side dry-run (role hiện tại `TF4-SecReliabilityReadOnlyAudit` là read-only, không `create` được VAP) → **CEL compilation + schema validation server-side phải chạy bởi account có quyền create trước khi apply/merge**. Đây là bài học từ REL-09 (không chốt code mà chưa build/dry-run thật).

---

## 6. Rủi ro (Known Risks)

| Risk | Mitigation |
|---|---|
| Flip `Deny` khi SEC-09 chưa rollout xong → chặn service chưa cập nhật | Điều kiện §3 (sweep=0) + dry-run trước flip |
| `failurePolicy: Fail` + CEL lỗi runtime → chặn mọi request khớp | CEL dùng optional-chaining `?.`/`orValue` tránh truy cập field vắng; alert `error_type!="no_error"` (§6.2) |
| opensearch/otel-collector (subchart) có thể không tuân non-root theo thiết kế | Xác nhận #233 phủ, nếu không thì ghi exception qua `objectSelector` (plan §5.4) |
| Enforce trên `techx-tf4` ảnh hưởng cả 4 team | Thông báo tf4-leads trước mỗi lần flip |

---

## 7. Tham chiếu (References)

- `docs/cdo08/week2/CDO08-SEC-11-runtime-hardening-admission-plan.md` — plan chi tiết
- `deploy/admission/sec11-runtime-hardening-vap.yaml` — manifest 4 policy + 8 binding
- `docs/cdo08/week2/sec11-test-manifests/` — manifest test cho mentor
- MANDATE-05 — Runtime Hardening
- SEC-09 (#233) — remove root/privilege gaps; #235 — pin runtime images
