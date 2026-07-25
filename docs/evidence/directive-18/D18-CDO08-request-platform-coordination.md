# Yêu Cầu Phối Hợp Hạ Tầng & An Ninh: Triển Khai VPC Endpoints (D18-PLAT-01)

**Gửi:** CDO-08 (Reviewer / Infrastructure Security Manager)  
**Từ:** CDO-04 (Huy Hoàng - Platform Owner)  
**Mã Task:** `D18-PLAT-01` (Mandate 18 - Cost Beyond Compute)  
**Mục tiêu:** Thiết lập VPC Endpoints trong VPC `techx-vpc` để giảm thiểu traffic đi qua NAT Gateway, từ đó cắt giảm chi phí xử lý dữ liệu và truyền tải Cross-AZ của AWS Services.

---

## 1. Thiết Kế Đề Xuất (Proposed Design)

Chúng tôi đề xuất khởi tạo các VPC Endpoints sau trong private subnets của `techx-vpc`:

| AWS Service | Loại Endpoint | Tác động định tuyến & Private DNS |
|---|---|---|
| **S3** | `Gateway` | Tự động tạo route đi qua S3 Endpoint trong Private Route Tables. |
| **ECR API** | `Interface` | Tạo Network Interface (ENI) trong private subnets, Enable Private DNS. |
| **ECR DKR** | `Interface` | Tạo Network Interface (ENI) trong private subnets, Enable Private DNS. |
| **STS** | `Interface` | Tạo Network Interface (ENI) trong private subnets, Enable Private DNS. |
| **CloudWatch Logs (`logs`)** | `Interface` | Tạo Network Interface (ENI) trong private subnets, Enable Private DNS. |
| **SSM** | `Interface` | Tạo Network Interface (ENI) trong private subnets, Enable Private DNS. |
| **SSM Messages** | `Interface` | Tạo Network Interface (ENI) trong private subnets, Enable Private DNS. |
| **EC2 Messages** | `Interface` | Tạo Network Interface (ENI) trong private subnets, Enable Private DNS. |

---

## 2. Chi Tiết Ảnh Hưởng Hạ Tầng Dùng Chung (Shared Infrastructure Impact)

### A. Route Table & Network Routing
*   **Gateway Endpoint (S3):** Sẽ được liên kết trực tiếp với toàn bộ Route Tables của private subnets (`module.vpc.private_route_table_ids`). Không ảnh hưởng đến các Route Tables dùng chung hoặc route tables của public subnets.
*   **Interface Endpoints:** Không sửa đổi Route Tables. Việc định tuyến được thực hiện tự động qua DNS phân giải của Route 53 Resolver (Private DNS).

### B. Private DNS Resolution
*   **Kích hoạt Private DNS:** Tất cả các Interface Endpoints đều đặt `private_dns_enabled = true`.
*   **Tác động:** Khi Pod trong EKS hoặc Bastion host gọi dịch vụ AWS (ví dụ: `ecr.us-east-1.amazonaws.com`), DNS resolver nội bộ của VPC sẽ phân giải tên miền này về **Private IP của Interface Endpoint (ENI)** thay vì Public IP. Việc này hoàn toàn trong suốt và tự động, không yêu cầu thay đổi cấu hình hoặc code của ứng dụng.

### C. Security Group & Port Policy
Chúng tôi tạo mới một Security Group chuyên dụng cho VPC Endpoints: `aws_security_group.vpc_endpoints`.
*   **Inbound Rules:**
    *   Chỉ mở cổng **`443` (HTTPS)**.
    *   Nguồn (Source CIDR): Chỉ giới hạn trong dải mạng của VPC `var.vpc_cidr` (`10.0.0.0/16`).
*   **Outbound Rules:** Mặc định cho phép mọi lưu lượng (hoặc giới hạn cổng 443 đến AWS services).

---

## 3. Chính Sách Bảo Mật (Endpoint Policy)

Để đảm bảo không ảnh hưởng đến hoạt động bình thường của EKS và các ứng dụng khác:
*   Chúng tôi sử dụng **AWS default FullAccess policy** cho các endpoints trong đợt triển khai ban đầu:
    ```json
    {
      "Statement": [
        {
          "Action": "*",
          "Effect": "Allow",
          "Principal": "*",
          "Resource": "*"
        }
      ]
    }
    ```
*   *Lý do kỹ thuật:* EKS, OTel Collector, Fluent-Bit và SSM Agent có các IAM Roles riêng biệt (IRSA / Instance Profile) chịu trách nhiệm xác thực ở tầng IAM. Endpoint Policy mặc định cho phép các Roles này thực hiện cuộc gọi qua Endpoint một cách an toàn mà không bị chặn nhầm.

---

## 4. Kế Hoạch Đánh Giá & Xác Minh (Validation Plan)

Sau khi Terraform Apply thành công, chúng tôi sẽ thực hiện các bước xác minh sau và báo cáo kết quả:

1.  **Xác minh ECR Image Pull:** Thực hiện `kubectl rollout restart` cho một deployment stateless. Đảm bảo nodes vẫn có thể pull image từ ECR bình thường qua `ecr.dkr` endpoint.
2.  **Xác minh S3 Access:** Chạy lệnh `aws s3 ls` từ Bastion Host để kiểm tra kết nối qua S3 Gateway Endpoint.
3.  **Xác minh STS Token Exchange:** Kiểm tra logs của các pod đang sử dụng IRSA (IAM Roles for Service Accounts) để xác nhận việc lấy token từ STS thông qua STS Endpoint hoạt động ổn định.
4.  **Xác minh Telemetry Log Shipping:** Đảm bảo container logs và metrics vẫn được ship lên CloudWatch Logs thành công thông qua logs endpoint.
5.  **Xác minh Bastion/SSM Access:** Thử nghiệm thiết lập Session Manager kết nối vào Bastion host để chứng minh SSM endpoints hoạt động bình thường và không làm gián đoạn quyền truy cập vận hành.

---

## 5. Phản Hồi Từ CDO-08 (Reviewer Sign-off)

*Vui lòng xác nhận và phản hồi bằng cách để lại ý kiến hoặc chấp thuận dưới đây để chúng tôi tiến hành apply cấu hình trong cửa sổ thay đổi (Change Window) được phê duyệt.*

- [ ] **Chấp thuận thiết kế định tuyến Route Table**
- [ ] **Chấp thuận cấu hình Security Group (Port 443 từ VPC CIDR)**
- [ ] **Chấp thuận cấu hình Private DNS**
- [ ] **Không có xung đột hạ tầng dùng chung**

**Ý kiến đóng góp (nếu có):**
...
