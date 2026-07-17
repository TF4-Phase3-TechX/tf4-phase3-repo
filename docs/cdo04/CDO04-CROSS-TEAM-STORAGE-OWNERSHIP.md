# Phân công trách nhiệm cho các task Persistent Storage liên nhóm

## 1. Jaeger Persistent Trace Storage

### Mục tiêu

Thiết kế và triển khai persistent trace storage cho Jaeger để không phụ thuộc hoàn toàn vào memory storage, bảo đảm trace phục vụ acceptance run vẫn được giữ lại, truy vấn được và không mất khi pod restart.

### Phân công trách nhiệm

- **Owner chính:** CDO08 — Security & Reliability
- **Support:** CDO07 — Auditability, CDO04 — Performance & Cost
- **Reviewer/Verifier:** CDO07

### Lý do phân công

CDO08 chịu trách nhiệm chính vì task này liên quan trực tiếp đến:

- Telemetry pipeline.
- Jaeger storage backend.
- OTel connectivity.
- Secret và credential.
- Reliability khi pod restart.
- Private access vào Jaeger.
- Retention và availability của trace storage.

CDO07 hỗ trợ và xác minh các nội dung:

- Retention.
- Redaction dữ liệu nhạy cảm.
- Trace evidence đầu, giữa và cuối test window.
- Khả năng tái kiểm evidence.
- Auditability của trace và access.

CDO04 hỗ trợ các nội dung:

- Ước tính trace volume.
- Đánh giá performance impact.
- Đánh giá cost impact.
- Xác định acceptance requirement cho Directive #2.
- Kiểm tra storage mới không làm tăng latency hoặc vượt budget.

### Cách ghi trên Jira

```text
Owner: CDO08
Support: CDO07, CDO04
Reviewer/Verifier: CDO07
```

---

## 2. PostgreSQL Persistent Storage / PVC

### Mục tiêu

Bổ sung persistent storage cho PostgreSQL để dữ liệu không bị mất khi pod bị recreate, reschedule hoặc rollout, đồng thời bảo đảm dữ liệu phục vụ acceptance run và mentor rerun có thể được giữ lại nhất quán.

### Phân công trách nhiệm

- **Owner chính:** CDO08 — Reliability / Infrastructure
- **Support:** CDO04 — Performance & Cost, CDO07 — Auditability
- **Reviewer:** CDO04 hoặc CDO07 tùy mục tiêu nghiệm thu

### Lý do phân công

CDO08 chịu trách nhiệm chính vì task này liên quan trực tiếp đến:

- StatefulSet hoặc Deployment configuration.
- PersistentVolumeClaim.
- StorageClass.
- Volume mount.
- PGDATA path.
- Data persistence.
- Pod recreation.
- Migration và rollback.
- Reliability khi restart hoặc reschedule.

CDO07 hỗ trợ nếu dữ liệu PostgreSQL liên quan đến:

- Audit trail.
- Order hoặc accounting history.
- Evidence.
- Mentor rerun.
- Tính nhất quán của dữ liệu giữa các lần test.

CDO04 hỗ trợ các nội dung:

- Storage cost.
- Performance impact.
- Validation trước và sau thay đổi.
- Ảnh hưởng đến browse, cart, checkout.
- Điều kiện để acceptance run được xem là hợp lệ.

