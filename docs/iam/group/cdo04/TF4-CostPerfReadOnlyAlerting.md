# Permission Set: TF4-CostPerfReadOnlyAlerting

Tài liệu này chi tiết hóa quyền hạn của Permission Set `TF4-CostPerfReadOnlyAlerting`. Đây là tập hợp quyền phục vụ công tác quản lý tài chính đám mây (FinOps) và giám sát hiệu suất tài nguyên để tối ưu hóa chi phí trong hệ thống TF4.

## 📄 Nội dung Policy (JSON)

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "CostManagementAndAlerting",
            "Effect": "Allow",
            "Action": [
                "ce:Get*",
                "ce:Describe*",
                "ce:List*",
                "ce:CreateAnomalyMonitor",
                "ce:CreateAnomalySubscription",
                "ce:UpdateAnomalyMonitor",
                "ce:UpdateAnomalySubscription",
                "cur:DescribeReportDefinitions",
                "pricing:GetProducts",
                "pricing:Describe*",
                "budgets:ViewBudget",
                "budgets:ModifyBudget",
                "budgets:CreateBudget",
                "budgets:CreateNotification",
                "budgets:UpdateNotification",
                "budgets:CreateSubscriber",
                "budgets:UpdateSubscriber",
                "budgets:DeleteNotification",
                "budgets:DeleteSubscriber",
                "budgets:DescribeBudgetActionsForBudget",
                "billing:Get*",
                "billing:View*",
                "tax:Get*",
                "tax:List*",
                "organizations:DescribeOrganization"
            ],
            "Resource": "*"
        },
        {
            "Sid": "PerformanceOptimizationAndMonitoring",
            "Effect": "Allow",
            "Action": [
                "cloudwatch:Get*",
                "cloudwatch:List*",
                "cloudwatch:Describe*",
                "cloudwatch:PutMetricAlarm",
                "cloudwatch:PutDashboard",
                "cloudwatch:DeleteDashboards",
                "ec2:Describe*",
                "eks:ListClusters",
                "eks:DescribeCluster",
                "eks:ListNodegroups",
                "eks:DescribeNodegroup",
                "autoscaling:DescribeAutoScalingGroups",
                "elasticloadbalancing:DescribeLoadBalancers",
                "rds:Describe*",
                "rds:List*",
                "compute-optimizer:Get*",
                "compute-optimizer:Describe*",
                "trustedadvisor:Describe*",
                "support:DescribeTrustedAdvisor*",
                "pi:Get*",
                "pi:Describe*",
                "pi:List*",
                "savingsplans:Describe*",
                "dynamodb:Describe*",
                "elasticache:Describe*",
                "s3:GetStorageLens*",
                "s3:ListStorageLens*"
            ],
            "Resource": "*"
        },
        {
            "Sid": "AllowPortForwardingToApprovedBastion",
            "Effect": "Allow",
            "Action": [
                "ssm:StartSession"
            ],
            "Resource": [
                "arn:aws:ec2:us-east-1:511825856493:instance/i-072084d1cf0b2f1c9",
                "arn:aws:ssm:us-east-1::document/AWS-StartPortForwardingSession"
            ]
        },
        {
            "Sid": "AllowSessionDataChannelForOwnSessions",
            "Effect": "Allow",
            "Action": [
                "ssmmessages:OpenDataChannel"
            ],
            "Resource": [
                "arn:aws:ssm:us-east-1:511825856493:session/${aws:userid}-*"
            ]
        },
        {
            "Sid": "AllowManageOwnSessions",
            "Effect": "Allow",
            "Action": [
                "ssm:ResumeSession",
                "ssm:TerminateSession"
            ],
            "Resource": [
                "arn:aws:ssm:us-east-1:511825856493:session/${aws:userid}-*"
            ]
        },
        {
            "Sid": "AllowReadOnlySessionAndInstanceDiscovery",
            "Effect": "Allow",
            "Action": [
                "ssm:DescribeInstanceInformation",
                "ssm:DescribeSessions",
                "ssm:GetConnectionStatus",
                "ec2:DescribeInstances"
            ],
            "Resource": "*"
        }
    ]
}
```

---

## 🔍 Giải thích chi tiết Quyền hạn

Policy này gồm 6 Statements phục vụ mục đích kiểm soát chi phí, hiệu năng và cấp quyền truy cập cổng giám sát bảo mật qua SSM Tunnel:

### Statement 1: `CostManagementAndAlerting` (Quản lý & Cảnh báo Chi phí)

Nhóm quyền này cung cấp khả năng xem báo cáo hóa đơn, thiết lập ngân sách và cấu hình phát hiện chi phí tăng bất thường:

* **Cost Explorer (CE)**: Cho phép gọi `ce:Get*`, `ce:Describe*`, `ce:List*` để phân tích biểu đồ chi phí. Cho phép tạo và cập nhật các bộ giám sát bất thường (`CreateAnomalyMonitor`, `CreateAnomalySubscription`) để tự động thông báo khi chi phí tăng đột biến.
* **AWS Budgets**: Cho phép xem, tạo và chỉnh sửa cấu hình ngân sách (`budgets:ViewBudget`, `ModifyBudget`, `CreateBudget`), kèm theo các cấu hình gửi thông báo cho các bên liên quan (`CreateNotification`, `CreateSubscriber`).
* **Billing, Tax & Pricing**: Xem hóa đơn (`billing:Get*`, `View*`), thuế (`tax:Get*`, `List*`), giá sản phẩm AWS (`pricing:GetProducts`, `Describe*`) và thông tin AWS Organizations để phục vụ việc gom nhóm hóa đơn (Consolidated Billing).
* **Cost and Usage Report (CUR)**: Mô tả các cấu hình xuất báo cáo chi tiết về S3 (`cur:DescribeReportDefinitions`).

---

### Statement 2: `PerformanceOptimizationAndMonitoring` (Giám sát & Tối ưu Hiệu năng)

Nhóm quyền này cho phép theo dõi tài nguyên nhằm phát hiện các tài nguyên chạy quá tải hoặc dư thừa công suất (Under-utilized / Over-provisioned):

* **CloudWatch Dashboard & Alarms**: Cho phép thiết lập các biểu đồ giám sát hiệu năng (`PutDashboard`, `DeleteDashboards`) và cấu hình cảnh báo ngưỡng tài nguyên (`PutMetricAlarm`).
* **Hạ tầng chính (EKS, EC2, ASG, ELB, RDS, DynamoDB, ElastiCache)**: Quyền chỉ đọc thông tin cấu hình và trạng thái của các tài nguyên này để phân tích dung lượng sử dụng thực tế.
* **AWS Compute Optimizer & Trusted Advisor**: 
  * Quyền xem các khuyến nghị tối ưu hóa tài nguyên từ Compute Optimizer (`compute-optimizer:Get*`) như: khuyến nghị đổi kích thước instance EC2, Auto Scaling, EBS.
  * Xem khuyến nghị về bảo mật, hiệu năng, chi phí của AWS Trusted Advisor (`trustedadvisor:Describe*`, `support:DescribeTrustedAdvisor*`).
* **AWS Performance Insights (PI)**: Lấy dữ liệu phân tích sâu hiệu suất database RDS (`pi:Get*`, `Describe*`).
* **Savings Plans**: Kiểm tra các gói cam kết chiết khấu chi phí (`savingsplans:Describe*`).
* **S3 Storage Lens**: Phân tích dung lượng, xu hướng sử dụng và cấu hình bảo mật của các S3 bucket trên diện rộng (`s3:GetStorageLens*`, `ListStorageLens*`).

---

### Statement 3: `AllowPortForwardingToApprovedBastion` (Cấp quyền mở SSM Port Forward)
* **Hành động**: `ssm:StartSession`
* **Tài nguyên**: Giới hạn ở Bastion Host `arn:aws:ec2:us-east-1:511825856493:instance/i-072084d1cf0b2f1c9` và tài liệu SSM Port-Forwarding chuẩn `arn:aws:ssm:us-east-1::document/AWS-StartPortForwardingSession`.
* **Mô tả**: Cho phép thiết lập đường truyền cổng vận hành (Grafana, Jaeger, Locust, Alertmanager) về localhost của máy cá nhân. Quyền này tuyệt đối **không** cho phép mở phiên shell tương tác (không cấp `SSM-SessionManagerRunShell` hay `AWS-StartSSHSession`).

### Statement 4: `AllowSessionDataChannelForOwnSessions` (Mở kênh truyền dữ liệu)
* **Hành động**: `ssmmessages:OpenDataChannel`
* **Tài nguyên**: Giới hạn ở session ID được định danh theo User ID hiện tại của chính người tạo (`session/${aws:userid}-*`).
* **Mô tả**: Cho phép thiết lập kênh truyền dữ liệu bảo mật hai chiều thông qua SSM.

### Statement 5: `AllowManageOwnSessions` (Quản trị phiên kết nối cá nhân)
* **Hành động**: `ssm:ResumeSession`, `ssm:TerminateSession`
* **Tài nguyên**: Giới hạn ở session ID của chính người dùng đó (`session/${aws:userid}-*`).
* **Mô tả**: Cho phép người dùng tự khôi phục phiên kết nối khi bị rớt mạng (`ResumeSession`) và đóng sạch session để dọn dẹp sau khi kiểm thử xong (`TerminateSession`).

### Statement 6: `AllowReadOnlySessionAndInstanceDiscovery` (Tra cứu thông tin phiên & Trạng thái Bastion)
* **Hành động**: `ssm:DescribeInstanceInformation`, `ssm:DescribeSessions`, `ssm:GetConnectionStatus`, `ec2:DescribeInstances`
* **Tài nguyên**: `*` (áp dụng toàn cục để tra cứu).
* **Mô tả**: Quyền kiểm tra trạng thái Online của Bastion host trong danh sách SSM và xem các phiên kết nối đang hoạt động.

---
[⬅️ Quay lại nhóm CDO04](README.md) | [🏡 Quay lại trang chủ IAM Docs](../../README.md)
