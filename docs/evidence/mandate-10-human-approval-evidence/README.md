# MANDATE-10 — Bằng chứng phê duyệt con người

**Người phụ trách:** Nguyễn Phú Triệu (CDO-07 Auditability)
**Phạm vi:** Human Approval Evidence và kiểm tra branch protection
**Thời điểm thu thập bằng chứng:** 2026-07-21
**Nhánh nguồn:** `main`

Thư mục này chứa bằng chứng kiểm toán độc lập, chỉ đọc cho sub-task Human
Approval Evidence của MANDATE-10. Bộ bằng chứng chứng minh được:

```text
Commit SHA
  -> Pull Request tương ứng
  -> PR đã merge vào main
  -> reviewer nào đã APPROVED trước khi merge
  -> branch protection của main
```

## Danh mục file

| Thành phần | Mục đích |
|---|---|
| `HUMAN-APPROVAL-AUDIT-REPORT.md` | Báo cáo kiểm toán bằng tiếng Việt |
| `HUMAN-APPROVAL-RECORD.json` | Bản ghi có cấu trúc của PR, approval và branch protection |
| `RUNBOOK.md` | Quy trình tái kiểm tra trực tiếp trên GitHub bằng `gh api` |
| `images/H2-01-commit-to-pr.png` | Đối chiếu commit Provenance với PR #443 đã merge |
| `images/H2-02-pr-approval-reviewers.png` | Hai review có trạng thái `APPROVED` trước khi merge |
| `images/H2-03-main-branch-protection.png` | Kiểm tra ruleset `main` và phát hiện status checks chưa cấu hình |

## Kết quả chính

- PR #443 đã merge vào `main`.
- Commit Provenance `a93093665767a27c40b71e6597b10c1ce20dd702` khớp với
  merge commit của PR.
- Có hai approval trước thời điểm merge: `NamHoang4268` và `Remmusss`.
- Ruleset `main` đang active, yêu cầu 2 approvals và code-owner review.
- Required status checks chưa được cấu hình; đây là finding để gửi Security/
  DevOps xử lý, Audit không tự thay đổi branch protection.

## Phạm vi và giới hạn

Đây là bằng chứng Human Approval độc lập, không thay đổi workflow, branch
protection, workload production hoặc cấu hình triển khai. Các ảnh P1 của
Provenance Chain được quản lý trong folder riêng
`mandate-10-provenance-chain`.
