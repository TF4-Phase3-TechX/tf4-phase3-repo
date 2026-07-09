# Permission Set: TF4-BaseReadOnly

Tài liệu này chi tiết hóa quyền hạn của Permission Set `TF4-BaseReadOnly`. Đây là tập hợp quyền chỉ đọc (ReadOnly) cơ bản đối với hạ tầng AWS được gán cho hầu hết các nhóm chức năng nhằm phục vụ mục đích giám sát và phát hiện lỗi cơ bản.

## 📄 Nội dung Policy (JSON)

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "BaseInfrastructureReadOnly",
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
                "logs:GetQueryResults",
                "tag:GetResources"
            ],
            "Resource": "*"
        }
    ]
}
```

---

## 🔍 Giải thích chi tiết Quyền hạn

Policy này chứa một Statement duy nhất có ID là `BaseInfrastructureReadOnly` với các nhóm quyền cụ thể sau:

### 1. Amazon EKS (Elastic Kubernetes Service)
* **Hành động**: `eks:Describe*`, `eks:List*`
* **Mô tả**: Cho phép liệt kê và xem thông tin chi tiết của EKS clusters, node groups, fargate profiles, add-ons, và các cấu hình liên quan.
* **Mục đích**: Giúp người dùng kiểm tra trạng thái hoạt động của Kubernetes clusters.

### 2. Amazon EC2 (Elastic Compute Cloud) & Auto Scaling
* **Hành động**: `ec2:Describe*`, `autoscaling:Describe*`
* **Mô tả**: Quyền xem danh sách các EC2 instances, security groups, subnets, VPCs, network interfaces, và các cấu hình Auto Scaling groups.
* **Mục đích**: Theo dõi hạ tầng máy chủ ảo và cơ chế tự động co giãn.

### 3. Elastic Load Balancing (ELB)
* **Hành động**: `elasticloadbalancing:Describe*`
* **Mô tả**: Quyền xem cấu hình và trạng thái của Application Load Balancers (ALB) và Network Load Balancers (NLB).
* **Mục đích**: Giám sát phân phối lưu lượng mạng đến các dịch vụ.

### 4. Amazon ECR (Elastic Container Registry)
* **Hành động**: `ecr:Describe*`, `ecr:List*`, `ecr:GetAuthorizationToken`
* **Mô tả**: Cho phép xem danh sách repositories, container images và lấy token xác thực (Authorization Token) để pull image từ ECR.
* **Mục đích**: Đảm bảo quyền kéo container image phục vụ deployment hoặc chạy thử nghiệm cục bộ.

### 5. Amazon CloudWatch & CloudWatch Logs
* **Hành động**: 
  * CloudWatch: `cloudwatch:Describe*`, `cloudwatch:Get*`, `cloudwatch:List*`
  * Logs: `logs:Describe*`, `logs:Get*`, `logs:FilterLogEvents`, `logs:StartQuery`, `logs:StopQuery`, `logs:GetQueryResults`
* **Mô tả**: Quyền xem metrics, dashboards, alarms trên CloudWatch. Đồng thời cho phép đọc log streams, tìm kiếm và truy vấn logs bằng CloudWatch Logs Insights.
* **Mục đích**: Theo dõi hiệu năng hệ thống, phát hiện và debug sự cố thông qua logs và metrics.

### 6. Resource Group Tagging API
* **Hành động**: `tag:GetResources`
* **Mô tả**: Cho phép lấy thông tin các tài nguyên dựa trên Tags (nhãn).
* **Mục đích**: Phục vụ việc phân loại và quản lý tài nguyên hệ thống.

---
[🏡 Quay lại trang chủ IAM Docs](README.md)
