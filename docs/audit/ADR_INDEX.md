# Architecture Decision Log (ADR Index)

Sổ xố ghi nhận các quyết định liên quan đến kiến trúc, bảo mật và vận hành hệ thống.

| Ngày Quyết Định | Tóm Tắt Quyết Định (The What) | Lý do chính (The Why) | Link chi tiết (ADR) |
|-----------------|-------------------------------|-----------------------|---------------------|
| 2026-07-08 | Tách biệt quyền Audit và Platform | Áp dụng Separation of Duties, Audit chỉ có quyền Read, mọi cấu hình qua Terraform | [ADR-001](./001-audit-platform-separation.md) |
| [Date] | [Quyết định] | [Lý do] | [Link] |

*Lưu ý: Bất kỳ thay đổi nào ảnh hưởng đến luồng bảo mật hoặc thiết kế hệ thống đều phải được ghi nhận vào đây và tạo một file ADR chi tiết trong folder `docs/audit/adr/`.*
