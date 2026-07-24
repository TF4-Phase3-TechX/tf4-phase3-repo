# CDO08-REL-27 — ADR Recovery Actual Results and Final Verdict

| Thuộc tính | Giá trị |
|---|---|
| Mandate | 20 — DR, backup và restore |
| ADR nguồn | [`../week2/mandate20/adr/CDO08-REL-21-adr-draft.md`](../week2/mandate20/adr/CDO08-REL-21-adr-draft.md) |
| Results addendum | CDO08-REL-27 |
| Owner | Hải (PM) + Nguyên (Tech Lead) |
| Ngày lập | 2026-07-24 UTC |
| Trạng thái | **PENDING SIGN-OFF — FAIL / NOT READY TO CLOSE** |

## 1. Quy tắc bất biến

Tài liệu này bổ sung kết quả thực tế cho ADR, không chỉnh sửa target RPO/RTO. Target bên dưới được chép nguyên trạng từ ADR nguồn và vẫn được ghi là **đề xuất/chưa ký**, đúng trạng thái của tài liệu nguồn tại ngày 2026-07-24.

Không được:

- đổi target sau drill để biến FAIL thành PASS;
- dùng `RDS available` làm điểm kết thúc RTO khi validation chưa xong;
- dùng migration restore/DMS hoặc MSK cutover làm PITR/replay drill evidence;
- điền số actual nếu không có timestamped drill evidence;
- ghi chữ ký thay Hải hoặc Nguyên.

Nếu Hải và Nguyên chốt target khác trước drill, phải tạo revision ADR được ký trước khi chạy; không sửa hồi tố target sau khi đã biết actual.

## 2. Target baseline được giữ nguyên

| Store / miền dữ liệu | Target RPO trong ADR nguồn | Target RTO trong ADR nguồn | Trạng thái target |
|---|---:|---:|---|
| RDS — schema `accounting` | 15 phút | 1 giờ | **Đề xuất — chưa ký** |
| MSK — topic `orders` | 15 phút | 2 giờ | **Đề xuất — chưa ký** |
| ElastiCache — `valkey-cart` | Không cam kết, chấp nhận mất toàn bộ | 30 phút | **Đề xuất — chưa ký** |
| RDS — schema `catalog` | N/A | Khoảng 10–15 phút | **Đề xuất — chưa ký** |
| RDS — schema `reviews` | 1 giờ | 2 giờ | **Đề xuất — chưa ký** |

Nguồn target: [`../week2/mandate20/adr/CDO08-REL-21-rpo-rto-matrix.md`](../week2/mandate20/adr/CDO08-REL-21-rpo-rto-matrix.md). Các số trên không phải actual result và chưa phải commitment business cho đến khi được ký.

## 3. Actual RPO/RTO và verdict theo store

| Store / miền dữ liệu | Target RPO | Actual RPO | RPO verdict | Target RTO | Actual RTO | RTO verdict | Store verdict |
|---|---:|---:|---|---:|---:|---|---|
| RDS `accounting` | 15 phút, chưa ký | **N/A — drill chưa chạy** | **FAIL / NOT RUN** | 1 giờ, chưa ký | **N/A — drill chưa chạy** | **FAIL / NOT RUN** | **FAIL** |
| MSK `orders` + S3 replay | 15 phút, chưa ký | **N/A — archive/replay chưa chứng minh** | **FAIL / NOT RUN** | 2 giờ, chưa ký | **N/A — drill chưa chạy** | **FAIL / NOT RUN** | **FAIL** |
| ElastiCache `valkey-cart` | Không cam kết | **N/A — drill chưa chạy** | **NOT ASSESSED** | 30 phút, chưa ký | **N/A — drill chưa chạy** | **FAIL / NOT RUN** | **FAIL** |
| RDS `catalog` | N/A | N/A | **NOT APPLICABLE** | Khoảng 10–15 phút, chưa ký | **N/A — rebuild drill chưa chạy** | **FAIL / NOT RUN** | **FAIL** |
| RDS `reviews` | 1 giờ, chưa ký | **N/A — drill chưa chạy** | **FAIL / NOT RUN** | 2 giờ, chưa ký | **N/A — drill chưa chạy** | **FAIL / NOT RUN** | **FAIL** |

`N/A — drill chưa chạy` không có nghĩa là đạt. Với final closure, mọi store trong committed scope phải có actual hoặc một carve-out được PM/Tech Lead ký trước drill.

## 4. Evidence và validation result

| Store/control | Implementation evidence | Drill/actual evidence | Validation | Kết quả |
|---|---|---|---|---|
| RDS backup/PITR | [`../../../infra/terraform/rds.tf`](../../../infra/terraform/rds.tf); retention 7 ngày, encrypted, private | Chưa có `restore-db-instance-to-point-in-time` output trong Week 3 | Chưa có integrity/sequence/missing/duplicate report sau PITR | **FAIL / NOT RUN** |
| Accounting recovery procedure | [`CDO08-REL-27-SHARED-RDS-PITR-ACCOUNTING-MSK-REPLAY-RUNBOOK.md`](CDO08-REL-27-SHARED-RDS-PITR-ACCOUNTING-MSK-REPLAY-RUNBOOK.md) | Chưa có run evidence | Runbook review only | **PASS — documentation; FAIL — execution** |
| MSK runtime flow | [`../week2/mandate8/evidence/REL-17-kafka-msk-cutover-evidence.md`](../week2/mandate8/evidence/REL-17-kafka-msk-cutover-evidence.md) | Không có S3 archive manifest/replay output | Cutover PASS nhưng replay chưa được test | **FAIL — DR replay** |
| Requirement coverage | [`CDO08-REL-27-MANDATE-20-REQUIREMENT-EVIDENCE-MATRIX.md`](CDO08-REL-27-MANDATE-20-REQUIREMENT-EVIDENCE-MATRIX.md) | Requirement #3/#4 `NOT RUN` | Overall `FAIL / NOT READY TO CLOSE` | **FAIL** |
| IAM deletion separation | Inventory ghi CI/apply role có quyền xóa backup | Chưa có negative-delete `AccessDenied` output | Chưa đạt separation of duties | **FAIL** |
| Cleanup | Runbook định nghĩa cleanup gate | Chưa có resource deletion output của drill | Chưa xác minh source/archive còn nguyên sau cleanup | **NOT RUN** |

Expected runtime evidence root:

```text
docs/cdo08/week3/evidence/<RUN_ID>/
```

Actual chỉ được điền sau khi evidence pack có context, selected PITR, restore events, validation trước/sau replay, timeline, cleanup và verdict.

## 5. Root cause cho từng FAIL

| ID | FAIL | Root cause hiện tại | Tác động |
|---|---|---|---|
| RC-01 | Không có actual RPO/RTO | Witnessed restore drill chưa được thực hiện | Không chứng minh được target recovery có thể đạt |
| RC-02 | RDS PITR chưa được chứng minh | Có cấu hình PITR nhưng chưa chạy isolated point-in-time restore về trước corruption | Requirement #3 chưa đạt |
| RC-03 | MSK replay chưa được chứng minh | Repo chưa có MSK Connect S3 sink, archive contract hoặc approved replay tool evidence | Không có nguồn độc lập để replay khi mất topic/cluster |
| RC-04 | IAM negative-delete chưa đạt | Role CI/apply đang có quyền rộng; chưa có explicit deny/separate privileged delete role và runtime deny test | Operator/compromised automation có thể xóa backup |
| RC-05 | Target chưa có hiệu lực | ADR nguồn vẫn `DRAFT - CHƯA KÝ`; Hải và Nguyên chưa ký target/cadence | Không có baseline chính thức để đánh giá actual |
| RC-06 | Cleanup/validation chưa có | Drill chưa chạy nên chưa phát sinh validation và cleanup evidence | Chưa chứng minh restore an toàn, toàn vẹn và không để lại chi phí |

Các root cause trên phải được chuyển thành remediation item có priority, owner, next action, verification và evidence trong Subtask 4.

## 6. Final verdict

### Verdict hiện tại

**FAIL / NOT READY TO CLOSE MANDATE 20**

Lý do:

1. Target RPO/RTO và cadence chưa được Hải/Nguyên ký.
2. Chưa có RDS PITR drill về thời điểm trước sự cố.
3. Chưa có witnessed loss → restore/replay → validation → cleanup timeline.
4. Chưa có MSK/S3 archive và replay evidence.
5. Chưa có IAM negative-delete evidence.
6. Actual RPO/RTO chưa đo được nên không thể kết luận PASS.

Implementation evidence về RDS backup/encryption và MSK runtime cutover vẫn có giá trị, nhưng không đủ để đóng Mandate.

### Điều kiện đổi verdict

| Verdict mới | Điều kiện bắt buộc |
|---|---|
| `PASS` | Target được ký trước drill; mọi committed store đạt RPO/RTO; validation, replay, negative-delete và cleanup PASS; Hải + Nguyên ký final result |
| `CONDITIONAL PASS` | Chỉ dùng khi mọi requirement bắt buộc đạt và residual risk không làm sai target; mỗi risk có owner/due date và được Hải + Nguyên chấp nhận rõ |
| `FAIL` | Giữ nguyên nếu bất kỳ requirement bắt buộc, target hoặc validation nào FAIL/NOT RUN |

Không được dùng remediation backlog để tự động đổi một FAIL bắt buộc thành conditional pass.

## 7. Form cập nhật sau drill

Evidence Recorder thay đúng các ô `N/A — drill chưa chạy` bằng số đo từ evidence, không sửa cột target:

| Store | Corruption/cutoff UTC | Latest recovered record UTC | Actual RPO | Recovery start UTC | Usable + validated UTC | Actual RTO | PASS/FAIL | Evidence path |
|---|---|---|---:|---|---|---:|---|---|
| RDS `accounting` |  |  |  |  |  |  |  |  |
| MSK `orders` replay |  |  |  |  |  |  |  |  |
| ElastiCache `valkey-cart` |  |  |  |  |  |  |  |  |
| RDS `catalog` |  |  | N/A |  |  |  |  |  |
| RDS `reviews` |  |  |  |  |  |  |  |  |

RPO được tính từ cutoff/corruption đến bản ghi mới nhất được phục hồi liên tục. RTO kết thúc khi store/app usable và validation PASS, không kết thúc khi API restore vừa báo `available`.

## 8. Sign-off

### Target approval — phải ký trước drill

| Vai trò | Tên | Quyết định | UTC timestamp | Chữ ký/comment |
|---|---|---|---|---|
| PM | Hải | **Pending** |  |  |
| Tech Lead | Nguyên | **Pending** |  |  |

### Final result approval — ký sau khi actual/evidence hoàn tất

| Vai trò | Tên | Final verdict | Evidence-pack version/commit | UTC timestamp | Chữ ký/comment |
|---|---|---|---|---|---|
| PM | Hải | **Pending — current draft verdict is FAIL** |  |  |  |
| Tech Lead | Nguyên | **Pending — current draft verdict is FAIL** |  |  |  |
| Mentor/Witness |  | Pending |  |  |  |

Tài liệu chỉ chuyển sang `SIGNED` khi Hải và Nguyên tự xác nhận tên, UTC timestamp, final verdict và evidence-pack version. Nếu chưa ký, trạng thái bắt buộc vẫn là `PENDING SIGN-OFF`.
