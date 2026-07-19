# Permission Set: TF4-SecReliabilityReadOnlyAudit

Tài liệu này chi tiết hóa quyền hạn của Permission Set `TF4-SecReliabilityReadOnlyAudit` được gán cho người dùng **nguyen**. Đây là tập hợp quyền phục vụ công tác giám sát bảo mật hạ tầng chuyên sâu và đánh giá độ tin cậy của toàn bộ hệ thống dự án TF4.

## 📄 Nội dung Policy (JSON)

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "InfrastructureReliabilityReadOnly",
            "Effect": "Allow",
            "Action": [
                "eks:Describe*",
                "eks:List*",
                "ec2:Describe*",
                "elasticloadbalancing:Describe*",
                "autoscaling:Describe*",
                "ecr:Describe*",
                "ecr:List*",
                "ecr:GetAuthorizationToken",
                "cloudwatch:Describe*",
                "cloudwatch:Get*",
                "cloudwatch:List*",
                "logs:Describe*",
                "logs:Get*",
                "logs:FilterLogEvents",
                "logs:StartQuery",
                "logs:StopQuery",
                "logs:GetQueryResults"
            ],
            "Resource": "*"
        },
        {
            "Sid": "SecurityAssessmentAndAuditTools",
            "Effect": "Allow",
            "Action": [
                "iam:Get*",
                "iam:List*",
                "access-analyzer:Get*",
                "access-analyzer:List*",
                "access-analyzer:ValidatePolicy",
                "secretsmanager:ListSecrets",
                "secretsmanager:DescribeSecret",
                "kms:ListKeys",
                "kms:DescribeKey",
                "securityhub:Get*",
                "securityhub:List*",
                "guardduty:Get*",
                "guardduty:List*",
                "wafv2:Get*",
                "wafv2:List*",
                "acm:DescribeCertificate",
                "acm:ListCertificates"
            ],
            "Resource": "*"
        },
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

Policy này gồm 6 Statements phục vụ cho khía cạnh Hạ tầng Tin cậy (Infrastructure Reliability), Đánh giá An toàn thông tin (Security Assessment), và các quyền quản trị định danh được gom từ `TF4-SecurityIAMSSOManager`:

### Statement 1: `InfrastructureReliabilityReadOnly` (Độ tin cậy hạ tầng - ReadOnly)

Nhóm quyền này tương tự `TF4-BaseReadOnly`, cho phép người dùng giám sát toàn diện tình trạng sức khỏe và tính sẵn sàng của hạ tầng:

* **Amazon EKS & EC2**: Liệt kê và mô tả chi tiết thông số của Kubernetes clusters, instances, vpc, subnets, và autoscaling.
* **Elastic Load Balancing (ELB)**: Theo dõi cân bằng tải để phát hiện hiện tượng quá tải hoặc tắc nghẽn traffic.
* **Amazon ECR**: Lấy authorization token và mô tả thông tin repositories để xác minh phiên bản container images đang chạy.
* **CloudWatch & Logs**: Phân tích chuyên sâu log hệ thống, theo dõi dashboards, biểu đồ và metric để đánh giá độ tin cậy và phản hồi sự cố.

---

### Statement 2: `SecurityAssessmentAndAuditTools` (Công cụ đánh giá bảo mật)

Nhóm quyền này cho phép đội ngũ bảo mật cấu hình, theo dõi và đánh giá mức độ an toàn thông tin (Security posture) của toàn bộ tài khoản AWS mà không được quyền thay đổi cấu hình thực tế:

* **IAM & Access Analyzer**: Đọc cấu hình phân quyền (`iam:Get*`, `iam:List*`) và kiểm tra tính hợp lệ của policy bằng Access Analyzer (`ValidatePolicy`), giúp phát hiện các cấu hình phân quyền sai lệch hoặc vi phạm chính sách bảo mật.
* **Secrets Manager & KMS**: Cho phép xem danh sách các secrets và mô tả các key mã hóa (`kms:DescribeKey`, `kms:ListKeys`) nhằm đánh giá mức độ tuân thủ quy tắc quản lý khóa mật mã và quản lý mật khẩu. *Lưu ý: Không được cấp quyền lấy giá trị secret hoặc giải mã dữ liệu.*
* **AWS Security Hub & GuardDuty**: Theo dõi các cảnh báo bảo mật, các mối đe dọa trực tuyến đã phát hiện trên hệ thống Cloud (`securityhub:Get*`, `guardduty:Get*`).
* **AWS WAFv2**: Xem thông tin cấu hình tường lửa ứng dụng web (`wafv2:Get*`, `wafv2:List*`) để xác định hệ thống có được bảo vệ chống lại các lỗ hổng OWASP Top 10 hay không.
* **AWS Certificate Manager (ACM)**: Đọc thông tin và trạng thái của các chứng chỉ SSL/TLS (`acm:DescribeCertificate`) nhằm tránh tình trạng chứng chỉ hết hạn gây gián đoạn dịch vụ.

---

### Statement 3: `IAMManagement` (Quản trị toàn diện IAM)
* **Hành động**: `iam:*`
* **Mô tả**: Cấp quyền quản trị toàn phần đối với AWS Identity and Access Management (IAM). Cho phép thực thi mọi thao tác: tạo, chỉnh sửa, xóa người dùng (Users), nhóm (Groups), vai trò (Roles), chính sách phân quyền (Policies), khóa truy cập (Access Keys), cấu hình MFA, v.v.

---

### Statement 4: `SSOAndIdentityStoreManagement` (Quản trị AWS IAM Identity Center & Identity Store)
* **Hành động**: `sso:*`, `sso-directory:*`, `identitystore:*`
* **Mô tả**: Quyền quản trị toàn phần đối với AWS SSO (IAM Identity Center), thư mục đăng nhập SSO và Identity Store của AWS.

---

### Statement 5: `EKSAccessEntryManagement` (Quản lý lối truy cập Amazon EKS)
* **Hành động**: Các hành động đối với EKS Access Entry và liên kết Access Policy.
* **Mô tả**: Cho phép cấu hình các "Access Entries" trên Amazon EKS và phân phối quyền hạn truy cập của người dùng vào sâu bên trong Kubernetes Cluster.

---

### Statement 6: `OrganizationsReadOnly` (Đọc thông tin AWS Organizations)
* **Hành động**: `organizations:DescribeOrganization`, `organizations:List*`
* **Mô tả**: Quyền chỉ đọc thông tin cấu trúc tổ chức doanh nghiệp AWS Organizations để xác định sơ đồ cấu trúc tài khoản.

---
[⬅️ Quay lại thông tin user nguyen](README.md) | [🏡 Quay lại trang chủ IAM Docs](../../README.md)
