# IAM Strategy & Documentation

Tài liệu này ghi nhận chiến lược IAM hiện tại để phục vụ công tác Audit.

## 1. Chiến lược chung (RBAC)
- [Điền mô tả: ví dụ áp dụng nguyên tắc Least Privilege, mọi quyền cấp qua IAM Group...]

## 2. Các Role Quan Trọng
| Role Name | Scope/Service | Quyền hạn chính | Ghi chú |
|-----------|---------------|-----------------|---------|
| `eks-node-role` | EKS Worker Nodes | ECR Read, CNI policy, CloudWatch Write | Yêu cầu xem xét quyền CloudWatch Write có bị over-privileged không. |
| [Tên Role] | [Scope] | [Quyền] | |

## 3. Temporary Bootstrap Access (Quyền cấp tạm thời)
Ghi nhận bất kỳ quyền truy cập tạm thời nào được cấp trong quá trình triển khai ban đầu:
- **Tài khoản/Role**: [Mô tả]
- **Lý do**: [Mô tả]
- **Thời hạn (Ngày thu hồi)**: [YYYY-MM-DD]
