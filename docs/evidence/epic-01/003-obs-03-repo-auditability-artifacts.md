# EPIC-01 Evidence - OBS-03: Bộ artifact auditability của repo

CẬP NHẬT EVIDENCE

Nhóm thực hiện: CDO-07 Auditability

## Nội dung thay đổi

- Cập nhật `.github/CODEOWNERS` để ownership của các auditability artifacts rõ ràng hơn.
- Thêm template ADR tại `docs/audit/templates/ADR_TEMPLATE.md`.
- Thêm template runbook tại `docs/audit/templates/RUNBOOK_TEMPLATE.md`.
- Thêm template postmortem/COE tại `docs/audit/templates/POSTMORTEM_TEMPLATE.md`.
- Thêm thư mục đích để lưu ADR thật tại `docs/audit/adr/`.
- Thêm thư mục đích để lưu runbook thật tại `docs/audit/runbooks/`.
- Thêm thư mục đích để lưu postmortem/COE thật tại `docs/audit/postmortems/`.

## Kết quả hiện tại

- Repo đã có bộ template tái sử dụng cho quản lý thay đổi, phản ứng vận hành, và review sự cố/postmortem.
- Repo đã chỉ rõ nơi cần tạo tài liệu auditability thật sau khi copy từ template.
- CODEOWNERS đã có path ownership rõ ràng cho `docs/audit/**`, `docs/evidence/**`, và `.github/**`.
- OBS-03 đáp ứng mục tiêu docs/governance ở mức repo: có CODEOWNERS path coverage và có artifacts mẫu cho ADR/runbook/postmortem.
- Kiểm chứng runtime: N/A vì đây là thay đổi tài liệu/governance, không thay đổi runtime.
- Kiểm chứng trên GitHub: PR #46 đã được merge vào `main`.

## Vị trí evidence

- CODEOWNERS: `.github/CODEOWNERS`
- ADR template: `docs/audit/templates/ADR_TEMPLATE.md`
- Runbook template: `docs/audit/templates/RUNBOOK_TEMPLATE.md`
- Postmortem/COE template: `docs/audit/templates/POSTMORTEM_TEMPLATE.md`
- Thư mục ADR thật: `docs/audit/adr/README.md`
- Thư mục runbook thật: `docs/audit/runbooks/README.md`
- Thư mục postmortem/COE thật: `docs/audit/postmortems/README.md`
- PR đã merge: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/46
- Thư mục evidence: `docs/evidence/epic-01`

## Kiểm chứng

- Review file local:
  - `.github/CODEOWNERS`
  - `docs/audit/templates/ADR_TEMPLATE.md`
  - `docs/audit/templates/RUNBOOK_TEMPLATE.md`
  - `docs/audit/templates/POSTMORTEM_TEMPLATE.md`
  - `docs/audit/adr/README.md`
  - `docs/audit/runbooks/README.md`
  - `docs/audit/postmortems/README.md`
- Command kiểm tra trước khi commit:

```powershell
git status --short
git diff --stat
```

## Ghi chú / Follow-up

- Nếu team tạo GitHub group riêng cho CDO-07, cập nhật `.github/CODEOWNERS` để dùng group đó làm owner phù hợp.
- Khi dùng template để tạo tài liệu thật, đặt file trong đúng thư mục đích thay vì chỉnh trực tiếp file template.
