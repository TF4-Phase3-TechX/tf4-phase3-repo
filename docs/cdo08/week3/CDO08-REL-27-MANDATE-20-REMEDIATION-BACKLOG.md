# CDO08-REL-27 — Mandate 20 Remediation Backlog

| Thuộc tính | Giá trị |
|---|---|
| Task | CDO08-REL-27 — Create remediation backlog for failed or residual gaps |
| Owner tổng | Hải (PM) + Nguyên (Tech Lead) |
| Ngày lập | 2026-07-24 UTC |
| Nguồn findings | Requirement matrix, ADR results addendum, recovery runbook |
| Trạng thái Mandate hiện tại | **FAIL / NOT READY TO CLOSE** |

## 1. Quy tắc quản lý backlog

- Mọi `FAIL`, `PARTIAL` hoặc `NOT RUN` của Mandate 20 phải có item và owner.
- Item chỉ được đóng khi có verification evidence dưới `docs/cdo08/week3/`.
- Tạo remediation không tự biến FAIL thành PASS.
- Không sửa target RPO/RTO sau khi biết actual result.
- Không đóng gap bằng screenshot cấu hình nếu acceptance yêu cầu runtime command/output.
- Priority chỉ thay đổi khi Hải và Nguyên ghi lý do và UTC timestamp.

Priority:

- `P0`: chặn final verdict/đóng Mandate hoặc có nguy cơ mất accounting/order data.
- `P1`: không chặn bước drill đầu tiên nhưng chặn vận hành lặp lại/an toàn.
- `P2`: residual risk hoặc cần quyết định business.

## 2. Backlog tổng hợp

| ID | Finding/gap | Priority | Owner | Trạng thái | Next action | Verification/điều kiện đóng |
|---|---|---|---|---|---|---|
| M20-REM-01 | ADR target RPO/RTO và cadence chưa ký | **P0** | Hải + Nguyên | Open | Review target, cadence, retention và scope; ký trước drill | ADR có tên Hải/Nguyên, UTC timestamp, revision/commit; target không đổi sau drill |
| M20-REM-02 | Chưa có isolated RDS accounting PITR drill | **P0** | Nguyên + DB Operator | Not Run | Chọn timestamp trước corruption, restore instance cô lập, export/restore accounting và validate | Timestamped AWS command/output, actual RPO/RTO, integrity/sequence/missing/duplicate PASS |
| M20-REM-03 | Chưa có MSK Connect → S3 archive cho `orders` | **P0** | Nguyên + Streaming Operator | Open | Thiết kế/deploy S3 sink với encryption, cadence ≤ signed RPO và retention đã ký | Connector `RUNNING`; object coverage/cadence/encryption/retention evidence; induced event xuất hiện đúng archive |
| M20-REM-04 | Chưa có approved MSK archive replay tool/contract | **P0** | Streaming Operator + Accounting Owner | Open | Chốt schema/manifest, ordering, idempotency và isolated replay workflow | Replay range hoàn tất; count reconcile; lag 0; missing/duplicate không giải thích = 0 |
| M20-REM-05 | IAM deletion separation và negative-delete chưa đạt | **P0** | Security + Nguyên | Open | Thu hẹp CI/operator delete permission; tách privileged delete approver; thêm explicit deny/protection phù hợp | Normal operator delete thử trả `AccessDenied`; privileged workflow có approval và CloudTrail evidence |
| M20-REM-06 | Chưa có witnessed end-to-end restore/replay drill | **P0** | Hải + Nguyên | Not Run | Lên lịch mentor/witness; chạy controlled loss → restore/replay → validation → cleanup | Timeline có witness, account/cluster context, actual RPO/RTO và signed verdict |
| M20-REM-07 | Validation accounting chưa có final evidence | **P0** | DB Operator + Accounting Owner | Not Run | Chuẩn hóa query/check cho row count, checksum, FK, sequence, aggregate, missing/duplicate | Validation report PASS trước/sau replay, query + output + UTC timestamp |
| M20-REM-08 | Chưa có cleanup/cost evidence của drill | **P1** | Recovery Lead | Not Run | Tag toàn bộ temporary resources, đặt cleanup deadline, xóa sau approval | Delete output; source/archive không đổi; không còn resource theo `RunId`; chi phí/thời lượng được ghi |
| M20-REM-09 | Chưa chứng minh connector ổn định trong recovery window | **P1** | Streaming Operator | Open after REM-03 | Theo dõi delivery error, task restart, archive freshness và alert | Không unexplained delivery gap trong observation window; alert test PASS; runbook có escalation |
| M20-REM-10 | Inventory có thể bỏ sót resource tạo ngoài Terraform do quyền scan giới hạn | **P1** | Platform/Infra + Nguyên | Open | Chạy inventory lại bằng read-only inventory role đủ quyền | Timestamped full account/region inventory; mọi stateful store được map hoặc có signed carve-out |
| M20-REM-11 | RDS/other store actual RPO/RTO chưa được ghi vào ADR | **P0** | Evidence Recorder + Nguyên | Blocked by drill | Sau drill, điền actual vào cột riêng và link evidence; không sửa target | Mỗi store có actual, PASS/FAIL, root cause nếu fail và evidence path |
| M20-REM-12 | Final verdict chưa được Hải/Nguyên ký | **P0** | Hải + Nguyên | Blocked by REM-01–11 | Review evidence pack, residual risks và verdict | Hải + Nguyên ký final result với UTC timestamp và evidence-pack commit/version |
| M20-REM-13 | Cart write-through persistence chưa có business decision | **P2 — Needs Decision** | Hải + Cart Owner + Nguyên | Needs Decision | Xác nhận cart là reconstructable hay phải persist/write-through | Decision record có business rationale; nếu required, tạo implementation + restore verification task |

## 3. Chi tiết remediation

### M20-REM-01 — Ký target RPO/RTO và cadence

**Finding:** ADR nguồn vẫn `DRAFT - CHƯA KÝ`; các target 15 phút/1 giờ cho accounting và 15 phút/2 giờ cho MSK mới là đề xuất.

**Evidence:**

- [`../week2/mandate20/adr/CDO08-REL-21-adr-draft.md`](../week2/mandate20/adr/CDO08-REL-21-adr-draft.md)
- [`../week2/mandate20/adr/CDO08-REL-21-rpo-rto-matrix.md`](../week2/mandate20/adr/CDO08-REL-21-rpo-rto-matrix.md)

**Next action:**

1. Hải xác nhận business loss tolerance và cost/effort.
2. Nguyên xác nhận cadence/retention có khả năng đạt target.
3. Chốt scope từng store và carve-out trước drill.
4. Hai owner ký tên, UTC timestamp và commit/version.

**Close when:** signed baseline tồn tại trước timestamp bắt đầu drill. Nếu target được đổi sau drill, item không được đóng.

### M20-REM-02 — Chạy shared-RDS accounting PITR drill

**Finding:** RDS có PITR nhưng chưa có `restore-db-instance-to-point-in-time` evidence về mốc trước corruption.

**Evidence:**

- [`../../../infra/terraform/rds.tf`](../../../infra/terraform/rds.tf)
- [`CDO08-REL-27-MANDATE-20-REQUIREMENT-EVIDENCE-MATRIX.md`](CDO08-REL-27-MANDATE-20-REQUIREMENT-EVIDENCE-MATRIX.md)
- [`CDO08-REL-27-SHARED-RDS-PITR-ACCOUNTING-MSK-REPLAY-RUNBOOK.md`](CDO08-REL-27-SHARED-RDS-PITR-ACCOUNTING-MSK-REPLAY-RUNBOOK.md)

**Next action:** thực thi runbook trên restore instance private/cô lập; không cutover production trong drill.

**Close when:** evidence có account `511825856493`, region `us-east-1`, source/restore IDs, selected PITR UTC, start/end timestamps, validation PASS, actual RPO/RTO và cleanup.

### M20-REM-03 — Triển khai MSK Connect/S3 archival

**Finding:** runtime event flow đã ở MSK, nhưng repo chưa có S3 sink/archive evidence; broker retention không phải backup.

**Evidence:**

- [`../../../infra/terraform/msk.tf`](../../../infra/terraform/msk.tf)
- [`../week2/mandate8/evidence/REL-17-kafka-msk-cutover-evidence.md`](../week2/mandate8/evidence/REL-17-kafka-msk-cutover-evidence.md)

**Next action:**

1. Chốt topic, connector plugin/version, bucket/prefix và object format.
2. Bật encryption, versioning/immutability phù hợp, private access và retention.
3. Cấu hình flush cadence nhỏ hơn hoặc bằng signed RPO.
4. Giới hạn IAM connector chỉ được ghi đúng prefix; operator thường không được xóa archive.
5. Tạo freshness/delivery-failure alert.

**Close when:** một event có correlation ID được publish, xuất hiện trong S3 đúng cadence và có thể decode; connector/task health, object metadata, encryption, retention và IAM evidence đều PASS.

### M20-REM-04 — Chốt và kiểm thử MSK replay

**Finding:** chưa có replay tool/contract chứng minh ordering, schema và idempotency.

**Evidence:** mục 9 của [`CDO08-REL-27-SHARED-RDS-PITR-ACCOUNTING-MSK-REPLAY-RUNBOOK.md`](CDO08-REL-27-SHARED-RDS-PITR-ACCOUNTING-MSK-REPLAY-RUNBOOK.md).

**Next action:**

1. Tạo immutable manifest theo object version, partition và time range.
2. Chọn approved replay tool, giữ event key/original metadata.
3. Dry-run, sau đó replay vào topic và consumer group cô lập.
4. Enforce deterministic idempotency key.
5. Reconcile archived, accepted, rejected, duplicate và persisted totals.

**Close when:** isolated replay đạt lag 0, không thiếu range/partition, không unexplained duplicate, accounting integrity PASS và có command/output timestamp.

### M20-REM-05 — Tách quyền xóa backup

**Finding:** inventory ghi role CI/apply có quyền rộng, chưa có negative-delete evidence.

**Evidence:** [`../week2/mandate20/scan/CDO08-REL-20-stateful-store-inventory.md`](../week2/mandate20/scan/CDO08-REL-20-stateful-store-inventory.md).

**Next action:**

1. Lập danh sách RDS snapshot/automated backup, S3 archive và store backup actions cần bảo vệ.
2. Loại delete actions khỏi normal operator/CI role hoặc áp explicit deny/SCP/bucket policy phù hợp.
3. Tạo privileged break-glass/delete workflow với approver riêng.
4. Chạy negative test trên non-production protected object/snapshot.

**Close when:** normal operator nhận `AccessDenied`; CloudTrail ghi actor/action/resource/time; privileged path có approval và không làm mất evidence thật.

### M20-REM-06/07 — Witnessed drill và validation

**Finding:** chưa có controlled data loss, witness, actual measurement hoặc validation report.

**Next action:**

1. Hải mở drill và ghi witness/UTC T0.
2. Tạo corruption có kiểm soát trong isolated scope.
3. Thực hiện PITR và replay.
4. Xác minh row counts/checksum, FK/orphans, sequence, aggregate, missing/duplicate.
5. Ghi actual RPO/RTO và PASS/FAIL từng store.

**Close when:** mentor/witness, Hải và Nguyên xác nhận evidence pack; mọi FAIL có root cause và remediation, không bị xóa khỏi verdict.

### M20-REM-08 — Cleanup và cost control

**Finding:** chưa có drill nên chưa có cleanup proof.

**Next action:** dùng `RunId`/`AutoCleanupAfter` tags; lưu evidence trước khi xóa; xóa đúng restore RDS, validation DB, replay topic/group, runner, temp SG/secrets/dumps.

**Close when:** resource query theo run ID rỗng, source RDS vẫn `available`, production archive/topic không đổi và chi phí tạm được ghi.

### M20-REM-09 — Connector instability

**Finding:** chưa thể đánh giá vì connector chưa được chứng minh. Khi REM-03 triển khai, instability trở thành residual operational risk cần quan sát.

**Next action:** theo dõi connector/task state, restart count, delivery error, S3 object freshness và DLQ; tạo alert/escalation; chạy restart/recovery test.

**Close when:** observation window do Nguyên phê duyệt không có unexplained archive gap; induced failure phát alert và connector phục hồi mà không mất event.

### M20-REM-10 — Inventory completeness

**Finding:** một số AWS list/describe API từng bị từ chối; IaC review không thấy resource được tạo tay ngoài Terraform.

**Next action:** chạy lại inventory bằng read-only role có đủ `List/Describe/Get`; lưu account/region/timestamp và map mọi resource.

**Close when:** reviewer có thể truy vết service → store → backup/archive → owner → restore path cho toàn bộ revenue path và cluster state.

### M20-REM-11/12 — Actual results và final sign-off

**Finding:** actual chưa có và sign-off đang Pending.

**Evidence:** [`CDO08-REL-27-ADR-RECOVERY-ACTUAL-RESULTS-AND-FINAL-VERDICT.md`](CDO08-REL-27-ADR-RECOVERY-ACTUAL-RESULTS-AND-FINAL-VERDICT.md).

**Next action:** sau drill, điền actual/evidence/root cause; review final verdict; Hải ký business result, Nguyên ký technical result.

**Close when:** actual và target ở cột riêng, mỗi store có PASS/FAIL, mọi FAIL có remediation, chữ ký có UTC timestamp và evidence-pack commit/version.

### M20-REM-13 — Cart write-through persistence

**Trạng thái bắt buộc:** **Needs Decision / P2**.

**Finding:** ADR hiện xem Valkey cart là reconstructable và chấp nhận mất toàn bộ; chưa có business decision riêng về write-through persistence.

**Next action:**

1. Hải xác nhận mất cart có chấp nhận được không và trong bao lâu.
2. Cart Owner đánh giá write-through store, privacy, TTL, chi phí và restore semantics.
3. Nguyên ghi decision: `Accepted reconstructable` hoặc `Persistence required`.

**Close when:**

- Nếu `Accepted reconstructable`: ADR có rationale và chữ ký Hải/Nguyên.
- Nếu `Persistence required`: tạo implementation task, target RPO/RTO và restore drill riêng; không đóng item chỉ bằng decision miệng.

Item này không tự động chặn Mandate nếu signed scope xác nhận cart reconstructable, nhưng phải giữ `Needs Decision / P2` cho đến khi có quyết định.

## 4. Thứ tự thực hiện đề xuất

1. `M20-REM-01`: ký target/scope trước khi biết actual.
2. `M20-REM-03`, `M20-REM-04`, `M20-REM-05`: hoàn thiện archive/replay và deletion protection.
3. `M20-REM-02`, `M20-REM-06`, `M20-REM-07`: chạy witnessed PITR/replay drill và validation.
4. `M20-REM-08`, `M20-REM-10`: cleanup và đóng inventory evidence.
5. `M20-REM-11`, `M20-REM-12`: cập nhật actual và ký final verdict.
6. Theo dõi song song `M20-REM-09`; giữ `M20-REM-13` ở `Needs Decision / P2`.

## 5. Closure tracker

| ID | Jira/link | Due date | Verification evidence | Reviewer | Closed UTC |
|---|---|---|---|---|---|
| M20-REM-01 |  |  |  | Hải + Nguyên |  |
| M20-REM-02 |  |  |  | Nguyên |  |
| M20-REM-03 |  |  |  | Nguyên |  |
| M20-REM-04 |  |  |  | Accounting Owner |  |
| M20-REM-05 |  |  |  | Security |  |
| M20-REM-06 |  |  |  | Hải + Mentor |  |
| M20-REM-07 |  |  |  | Nguyên |  |
| M20-REM-08 |  |  |  | Recovery Lead |  |
| M20-REM-09 |  |  |  | Streaming Operator |  |
| M20-REM-10 |  |  |  | Platform/Infra |  |
| M20-REM-11 |  |  |  | Nguyên |  |
| M20-REM-12 |  |  |  | Hải + Nguyên |  |
| M20-REM-13 |  |  |  | Hải |  |
