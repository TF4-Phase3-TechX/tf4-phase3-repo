# Permission Set: TF4-SecurityIAMSSOManager

Tài liệu này chi tiết hóa quyền hạn của Permission Set `TF4-SecurityIAMSSOManager` được gán cho người dùng **nguyen**. Đây là tập hợp quyền Quản trị cao cấp liên quan tới việc thiết lập danh tính, phân quyền người dùng và liên kết quyền hạn với cụm Kubernetes (EKS Cluster).

## 📄 Nội dung Policy (JSON)

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "IAMManagement",
            "Effect": "Allow",
            "Action": [
                "iam:*"
            ],
            "Resource": "*"
        },
        {
            "Sid": "SSOAndIdentityStoreManagement",
            "Effect": "Allow",
            "Action": [
                "sso:*",
                "sso-directory:*",
                "identitystore:*"
            ],
            "Resource": "*"
        },
        {
            "Sid": "EKSAccessEntryManagement",
            "Effect": "Allow",
            "Action": [
                "eks:CreateAccessEntry",
                "eks:UpdateAccessEntry",
                "eks:DeleteAccessEntry",
                "eks:DescribeAccessEntry",
                "eks:ListAccessEntries",
                "eks:AssociateAccessPolicy",
                "eks:DisassociateAccessPolicy",
                "eks:ListAssociatedAccessPolicies",
                "eks:DescribeCluster"
            ],
            "Resource": "*"
        },
        {
            "Sid": "SSMAndEC2Access",
            "Effect": "Allow",
            "Action": [
                "ssm:StartSession",
                "ssm:ResumeSession",
                "ssm:TerminateSession",
                "ssm:DescribeSessions",
                "ssm:GetConnectionStatus",
                "ssm:DescribeInstanceInformation",
                "ec2:DescribeInstances"
            ],
            "Resource": "*"
        },
        {
            "Sid": "OrganizationsReadOnly",
            "Effect": "Allow",
            "Action": [
                "organizations:DescribeOrganization",
                "organizations:List*"
            ],
            "Resource": "*"
        }
    ]
}
```

---

## 🔍 Giải thích chi tiết Quyền hạn

Policy này gồm 5 Statements quản trị quyền hạn và định danh:

### 1. `IAMManagement` (Quản trị toàn diện IAM)
* **Hành động**: `iam:*`
* **Tài nguyên**: `*`
* **Mô tả**: Cấp quyền quản trị toàn phần đối với AWS Identity and Access Management (IAM). Cho phép thực thi mọi thao tác: tạo, chỉnh sửa, xóa người dùng (Users), nhóm (Groups), vai trò (Roles), chính sách phân quyền (Policies), khóa truy cập (Access Keys), chứng chỉ SSH, cấu hình MFA, v.v.
* **Mục đích**: Chịu trách nhiệm thiết kế cấu trúc phân quyền và xử lý sự cố phân quyền trên toàn bộ tài khoản AWS.

### 2. `SSOAndIdentityStoreManagement` (Quản trị AWS IAM Identity Center & Identity Store)
* **Hành động**: `sso:*`, `sso-directory:*`, `identitystore:*`
* **Tài nguyên**: `*`
* **Mô tả**: Quyền quản trị toàn phần đối với AWS SSO (IAM Identity Center), thư mục đăng nhập SSO và Identity Store của AWS. Cho phép quản lý người dùng đăng nhập SSO, cấu hình gán Permission Sets cho các tài khoản con thuộc AWS Organizations.
* **Mục đích**: Vận hành và quản lý luồng đăng nhập một lần (Single Sign-On) cho doanh nghiệp.

### 3. `EKSAccessEntryManagement` (Quản lý lối truy cập Amazon EKS)
* **Hành động**:
  * Các hành động đối với Access Entry: `CreateAccessEntry`, `UpdateAccessEntry`, `DeleteAccessEntry`, `DescribeAccessEntry`, `ListAccessEntries`.
  * Các hành động liên kết Access Policy: `AssociateAccessPolicy`, `DisassociateAccessPolicy`, `ListAssociatedAccessPolicies`.
  * Mô tả cluster: `DescribeCluster`.
* **Tài nguyên**: `*`
* **Mô tả**: Cho phép cấu hình các "Access Entries" trên Amazon EKS. Tính năng này cho phép ánh xạ (map) trực tiếp các AWS IAM Roles hoặc SSO Users vào Kubernetes RBAC mà không cần sửa file `aws-auth` ConfigMap cũ của Kubernetes.
* **Mục đích**: Quản lý và phân phối quyền hạn truy cập của lập trình viên và quản trị viên vào sâu bên trong Kubernetes Cluster.

### 4. `SSMAndEC2Access` (Quản lý phiên SSM và tra cứu EC2)
* **Hành động**: `ssm:StartSession`, `ssm:ResumeSession`, `ssm:TerminateSession`, `ssm:DescribeSessions`, `ssm:GetConnectionStatus`, `ssm:DescribeInstanceInformation`, `ec2:DescribeInstances`
* **Tài nguyên**: `*`
* **Mô tả**: Cấp quyền sử dụng SSM Session Manager để kết nối và quản lý phiên làm việc trần máy chủ và Bastion Host. Scope `*` trên resource cho phép quản lý toàn bộ session trong account, phù hợp với vai trò Admin vận hành.
* **Mục đích**: Hỗ trợ kiểm tra tình trạng hạ tầng, xử lý sự cố và kiểm soát phiên SSM trong quá trình vận hành.

### 5. `OrganizationsReadOnly` (Đọc thông tin AWS Organizations)
* **Hành động**: `organizations:DescribeOrganization`, `organizations:List*`
* **Tài nguyên**: `*`
* **Mô tả**: Quyền chỉ đọc thông tin cấu trúc tổ chức doanh nghiệp AWS Organizations (danh sách các tài khoản AWS thành viên, cấu trúc Organizational Units - OUs).
* **Mục đích**: Xác định sơ đồ cấu trúc tài khoản để thực hiện phân phối Permission Sets trong SSO một cách chính xác.

---
[⬅️ Quay lại thông tin user nguyen](README.md) | [🏡 Quay lại trang chủ IAM Docs](../../README.md)
