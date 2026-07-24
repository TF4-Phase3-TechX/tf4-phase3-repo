# CDO08-REL-21 - Tổng kết RPO/RTO ADR (Draft)

**Mandate:** [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md) - Directive #20, yêu cầu #2
**Owner:** Nguyên (Techlead) / phối hợp PM Hải
**Trạng thái:** Draft - ADR chưa ký. Input đã đủ (dựa trên [CDO08-REL-20-summary.md](../scan/CDO08-REL-20-summary.md)), còn thiếu bước drill thật (REL-26) trước khi ký chính thức.

## Đọc theo thứ tự này

| # | Tài liệu | Đọc để biết gì |
|---|---|---|
| 1 | [CDO08-REL-21-rpo-rto-matrix.md](CDO08-REL-21-rpo-rto-matrix.md) | Con số RPO/RTO đề xuất cho từng store, rationale, nguồn tham khảo (AWS Well-Architected) |
| 2 | [CDO08-REL-21-backup-policy-matrix.md](CDO08-REL-21-backup-policy-matrix.md) | Cadence/retention thật map từ RPO ở trên, kiểm tra không mâu thuẫn |
| 3 | [CDO08-REL-21-adr-draft.md](CDO08-REL-21-adr-draft.md) | ADR đầy đủ (scope, encryption, drill scenario, người ký) - **chưa ký** |
| 4 | [../review-requests/CDO08-REL-21-REVIEW-REQUEST-RPO-RTO-PROCESS.md](../review-requests/CDO08-REL-21-REVIEW-REQUEST-RPO-RTO-PROCESS.md) | Quy trình 5 bước (draft → sửa gap → test → điều chỉnh → ký) để trình PM, kèm nguồn đã verify |

## Quyết định đã chốt (Techlead)

- **MSK `orders` (GAP-02):** đầu tư MSK Connect + S3 Sink Connector, RPO 15 phút - không chấp nhận rủi ro mất event. Chi tiết + lý do: xem [CDO08-REL-20-gap-register.md](../scan/CDO08-REL-20-gap-register.md).
- **RDS `accounting` (GAP-06):** tách sang instance riêng, không còn chung với `catalog`/`reviews`. Chi tiết + lý do: xem gap register.

## Còn thiếu trước khi ký

1. Triển khai 2 quyết định trên (GAP-02, GAP-06).
2. Xử lý GAP-01 (IAM quá quyền).
3. Chạy drill thật (GAP-03/REL-26) - đo số thật, so với target trong matrix.
4. Điền tên người approve xoá backup (mục 5 của ADR draft).
5. Ký tên (Nguyên + Hải) ở mục 8 của ADR draft, đổi trạng thái đầu file từ DRAFT sang SIGNED.
