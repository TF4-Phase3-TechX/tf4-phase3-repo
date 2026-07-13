# Audit Runbooks

Thư mục này dùng để lưu các runbook vận hành thật cho các workflow liên quan đến auditability.

Khi tạo runbook mới, hãy copy mẫu từ `../templates/RUNBOOK_TEMPLATE.md`.

## Quy ước đặt tên

- `<system-or-process>-<action>.md`

## Khi nào cần tạo runbook

- Thao tác có tính lặp lại và mang tính vận hành.
- Reviewer hoặc người trực cần làm theo cùng một quy trình trong tương lai.
- Quy trình cần thu thập evidence, xác minh log, kiểm tra alert, hoặc phản ứng với sự cố auditability.

## Nội dung tối thiểu

- Owner và hướng escalation
- Điều kiện tiên quyết
- Quy trình từng bước
- Điều kiện rollback hoặc dừng thao tác
- Evidence cần thu thập
