# ADR-005: Bật EKS Control Plane Logging (api, audit, authenticator)

**Ngày:** 2026-07-08
**Trạng thái:** Accepted — Implemented
**Người quyết định:** CDO-04 (Infrastructure Owner: Huy Hoàng) — theo yêu cầu của CDO-07 (AUDIT-001)
**Người review:** CDO-07 (Audit)
**Pillar liên quan:** Auditability
**Terraform file:** `infra/terraform/eks.tf`

---

## 1. Bối cảnh (Context)

Kubernetes EKS Control Plane tạo ra các loại log quan trọng cho audit:

| Log type | Nội dung |
|---|---|
| `api` | API server request/response, bao gồm cả kubectl commands |
| `audit` | Mọi action lên Kubernetes API (create/delete/get resource, đọc Secret...) |
| `authenticator` | Quá trình xác thực IAM → K8s identity |
| `controllerManager` | (optional) Hoạt động của controller |
| `scheduler` | (optional) Scheduling decisions |

Mặc định, EKS **không bật** Control Plane Logging. Không có log = không thể audit được "ai đã làm gì với cluster".

---

## 2. Quyết định (Decision)

**Bật 3 log type bắt buộc cho EKS cluster `techx-tf4-cluster`:**

```hcl
# infra/terraform/eks.tf
cluster_enabled_log_types = ["api", "audit", "authenticator"]
```

**Kết quả thực tế:**
- CloudWatch Log Group: `/aws/eks/techx-tf4-cluster/cluster` — retention 90 ngày.
- Log streams: `kube-apiserver-audit-*`, `kube-apiserver-*`, `authenticator-*`.

**Không bật:** `controllerManager`, `scheduler` — **quyết định có chủ đích, không phải thiếu sót.**

Confirmed bởi CDO-07 (Đinh Văn Ty, 2026-07-10):
> "cái ni không phải là lỗi nha, vì phân tích hiện tại cho thấy 2 cái này chưa quá quan trọng và cũng như nếu dùng sẽ tăng chi phí → đẩy lên các tuần sau mới làm"

Chi phí ước tính nếu bật thêm: ~$5-10/tuần. Defer sang Week 2+ khi có runtime evidence cần thiết.

---

## 3. Lý do (Rationale)

| Lý do | Giải thích |
|---|---|
| Audit requirement | CDO-07 cần trace "ai đã chạy `kubectl delete pod`", "ai đã đọc Secret" |
| Security | Phát hiện unauthorized kubectl access |
| Incident investigation | Khi BTC inject incident, cần biết thay đổi gì xảy ra ở K8s layer |
| Compliance | AUDIT-001 ticket từ CDO-07 — P0 Blocker cho công tác kiểm toán |
| Cost acceptable | 3 log types: ~$1-2.50/tháng — nằm trong budget |

---

## 4. Cách sử dụng (How to Use)

**CDO-07 query log trong CloudWatch Log Insights:**

```sql
-- Tìm tất cả DELETE actions
fields @timestamp, @message
| filter @logStream like /kube-apiserver-audit/
| filter verb = "delete"
| sort @timestamp desc
| limit 50
```

```sql
-- Tìm ai đã đọc Secret
fields @timestamp, user.username, verb, objectRef.resource, objectRef.namespace
| filter @logStream like /kube-apiserver-audit/
| filter objectRef.resource = "secrets"
| sort @timestamp desc
```

```sql
-- Tìm actions của GitHub Actions role
fields @timestamp, verb, objectRef.resource, responseStatus.code
| filter @logStream like /kube-apiserver-audit/
| filter user.username like /tf4-github-actions/
| sort @timestamp desc
```

---

## 5. Chi phí (Cost Impact)

| Hạng mục | Ước tính |
|---|---|
| CloudWatch Log Ingestion | ~$0.50/GB |
| Ước tính volume (3 log types, cụm nhỏ/vừa) | 2-5 GB/tháng |
| Chi phí ước tính | ~$1.00-$2.50/tháng |
| Chi phí lưu trữ (90 ngày) | ~$0.03/GB/tháng × 5GB × 3 tháng ≈ $0.45 |

**Tổng: ~$1.50-3/tháng** — chấp nhận được trong budget $300/tuần.

---

## 6. Tham chiếu (References)

- `infra/terraform/eks.tf` — `cluster_enabled_log_types` config
- `docs/audit/tickets/AUDIT-001-enable-eks-logs.md` — Ticket yêu cầu gốc
- `docs/audit/DELEGATED_TASKS_P0.md` — Task 1.2
- ADR-001 — Separation of Duties (CDO-07 yêu cầu, CDO-04 thực thi)
