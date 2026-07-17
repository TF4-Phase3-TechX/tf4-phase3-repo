# CDO04 — Yêu cầu phối hợp liên nhóm cho các vấn đề Persistent Storage

## 1. Bối cảnh

Trong quá trình chuẩn bị cho Directive #2 — chịu tải flash sale 200 concurrent users trong 15 phút, CDO04 đã phát hiện hai vấn đề có thể làm acceptance run không hợp lệ hoặc làm mất evidence cần thiết cho mentor và CDO07 tái kiểm.

Hai vấn đề này không chỉ thuộc Performance & Cost mà còn liên quan trực tiếp đến Reliability, Telemetry và Auditability. Vì vậy CDO04 cần yêu cầu phối hợp từ CDO08 và CDO07.

---

## 2. Issue 1 — Jaeger đang lưu trace hoàn toàn trong RAM

### Hiện trạng

Jaeger hiện sử dụng memory storage:

```text
storage.type=memory
MEMORY_MAX_TRACES=25000
```

Với tải flash sale 200 users trong 15 phút, số lượng trace có thể vượt giới hạn lưu trong memory. Trace đầu bài test có nguy cơ bị ghi đè trước khi test kết thúc.

Nếu tăng `MEMORY_MAX_TRACES` và cấp thêm nhiều RAM cho Jaeger thì:

- Tăng áp lực memory lên worker node.
- Tăng nguy cơ OOMKilled.
- Làm tăng cost.
- Vẫn mất toàn bộ trace nếu Jaeger pod restart.
- Không giải quyết được retention và auditability lâu dài.

### Ảnh hưởng đến Directive #2

Issue này ảnh hưởng trực tiếp đến:

- Evidence trace đầu, giữa và cuối test.
- Phân tích bottleneck.
- Telemetry continuity.
- CDO07 independent verification.
- Mentor re-check.
- Cost và node headroom trong acceptance run.

Nếu không có phương án retention/persistence rõ ràng, acceptance run có thể bị đánh dấu `BLOCKED` dù SLO đạt.

### Yêu cầu CDO04 gửi đến CDO08 và CDO07

#### CDO08 — Owner chính

CDO08 cần:

- Xác nhận Jaeger version và storage backend hiện tại.
- Chọn hoặc triển khai persistent trace backend phù hợp.
- Bảo đảm OTel Collector vẫn gửi trace liên tục.
- Cấu hình secret/credential đúng cách.
- Xác định retention/TTL.
- Xác định sampling policy.
- Chuẩn bị rollback plan.
- Xác nhận private access vào Jaeger vẫn hoạt động.

#### CDO07 — Verifier

CDO07 cần:

- Xác minh trace đầu, giữa và cuối test còn truy vấn được.
- Kiểm tra redaction dữ liệu nhạy cảm.
- Xác minh evidence vẫn tái kiểm được sau test.
- Xác nhận retention phù hợp với acceptance requirement.
- Review raw trace evidence và remaining risk.

#### CDO04 — Support

CDO04 sẽ:

- Ước tính trace volume.
- Đánh giá performance impact.
- Đánh giá cost impact.
- Xác định acceptance requirement.
- Kiểm tra storage solution không làm vượt budget hoặc gây regression.

### Phân công

```text
Owner: CDO08
Support: CDO04, CDO07
Reviewer/Verifier: CDO07
```

---

## 3. Issue 2 — PostgreSQL chưa có persistent storage

### Hiện trạng

PostgreSQL hiện chưa có PVC/data volume rõ ràng và có nguy cơ đang lưu dữ liệu trên ephemeral filesystem hoặc `emptyDir`.

Nếu pod bị recreate, reschedule hoặc rollout, dữ liệu runtime có thể bị mất.

Ngoài ra PostgreSQL đã từng bị:

```text
OOMKilled
Exit code: 137
Memory limit: 100Mi
```

Phần OOM cần CDO04/Infra xử lý resource riêng. Tuy nhiên phần persistent storage cần phối hợp với CDO08 và CDO07 vì liên quan Reliability và Auditability.

### Ảnh hưởng đến Directive #2

Issue này ảnh hưởng đến:

- Tính nhất quán của dataset giữa các lần test.
- Khả năng mentor chạy lại acceptance test.
- So sánh before/after remediation.
- Dữ liệu order/accounting/review.
- Tính tái lập của kết quả.
- Risk mất dữ liệu khi pod restart trong test window.

Nếu acceptance run cần giữ dữ liệu giữa các lần chạy, PostgreSQL PVC là prerequisite bắt buộc.

### Yêu cầu CDO04 gửi đến CDO08 và CDO07

#### CDO08 — Owner chính

CDO08 cần:

- Kiểm tra workload type hiện tại.
- Kiểm tra volume và volumeMount.
- Xác nhận `PGDATA` path.
- Chọn StorageClass phù hợp.
- Tạo và mount PVC.
- Chuẩn bị migration/backup plan.
- Chuẩn bị rollback plan.
- Test pod recreation và data persistence.
- Xác nhận PostgreSQL Ready sau rollout.

#### CDO07 — Support/Verifier

CDO07 cần:

- Xác minh dữ liệu cần giữ phục vụ audit/evidence.
- Kiểm tra dữ liệu còn tồn tại sau pod recreation.
- Xác minh mentor rerun dùng cùng dataset hoặc có reset procedure rõ.
- Review evidence, timestamp và remaining risk.

#### CDO04 — Support

CDO04 sẽ:

- Đánh giá storage cost.
- Đánh giá performance impact.
- Chạy smoke test browse/cart/checkout sau thay đổi.
- Xác định điều kiện acceptance run.
- Kiểm tra persistence solution không làm vượt budget.

### Phân công

```text
Owner: CDO08
Support: CDO04, CDO07
Reviewer: CDO04 hoặc CDO07 tùy acceptance
```

---

## 4. Các đầu ra CDO04 cần nhận

### Từ CDO08

- Jaeger persistent storage design hoặc temporary mitigation đã được phê duyệt.
- Retention/TTL và sampling policy.
- Jaeger storage deployment evidence.
- PostgreSQL PVC/StorageClass/PGDATA configuration.
- Migration và rollback plan.
- Pod recreation test result.
- Cost impact của storage solution.

### Từ CDO07

- Trace retention verification.
- Redaction verification.
- Data persistence verification.
- Evidence path và UTC timestamp.
- Kết luận `PASS` / `FAIL` / `BLOCKED`.
- Remaining risk.

---

## 5. Gate trước acceptance run

CDO04 chỉ chạy acceptance test chính thức khi:

```text
Jaeger trace đầu/giữa/cuối có thể được giữ hoặc export an toàn
AND Jaeger không còn nguy cơ mất toàn bộ evidence khi pod restart
AND PostgreSQL persistence requirement đã được xác nhận
AND PVC/data persistence đã pass nếu dữ liệu cần giữ
AND cost impact đã được ghi nhận
AND CDO07 có thể tái kiểm evidence
```

Nếu chưa đạt, trạng thái là:

```text
BLOCKED — cross-team storage dependency not ready
```

---

## 6. Kết luận

CDO04 đang gặp hai issue cần phối hợp liên nhóm:

```text
1. Jaeger lưu trace trong RAM
2. PostgreSQL chưa có persistent storage
```

CDO08 là owner chính vì hai vấn đề thuộc telemetry/storage/reliability.

CDO07 tham gia với vai trò auditability và verifier.

CDO04 cung cấp yêu cầu performance/cost, kiểm tra impact và chỉ chạy acceptance run khi các dependency đã được bàn giao rõ ràng.
