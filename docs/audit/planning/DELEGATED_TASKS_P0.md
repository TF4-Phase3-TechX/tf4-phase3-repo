# Danh sách Task Ủy quyền cho Platform Team (Focus: Trụ Auditability)

Tài liệu này định nghĩa các yêu cầu (The What) từ Team Audit (CD007) chuyển giao cho Platform/DevOps Team để thực thi (The How). Team Audit sẽ dựa vào các mục "Nghiệm thu (Evidence)" để verify sau khi task hoàn thành.

## 1. [Task 1.1] Bật AWS CloudTrail + S3 Versioning
- **Mục tiêu Audit**: Đảm bảo lưu vết mọi hành động (API calls) can thiệp vào hạ tầng Cloud. S3 Versioning đảm bảo log không bị thay đổi/xóa (Immutability).
- **Yêu cầu cho Platform**: Provision bằng Terraform/IaC. Bật Versioning cho S3.
- **Audit Verify**: Team Audit vào S3 (quyền Read) tải file log về kiểm tra.

## 2. [Task 1.2] Bật Amazon CloudWatch Logs cho EKS
- **Mục tiêu Audit**: Lưu vết hoạt động của EKS Control Plane (API server, audit, authenticator).
- **Yêu cầu cho Platform**: Enable các log cần thiết cho EKS Cluster qua IaC.
- **Audit Verify**: Team Audit mở CloudWatch (quyền Read) và search thử 1 truy vấn log EKS.

## 3. [Task 3.1] Cấu hình OpenSearch Index State Management (ISM)
- **Mục tiêu Audit**: Đảm bảo có quy trình quản lý vòng đời log để log audit luôn có sẵn trong khoảng thời gian quy định (ví dụ 90 ngày) mà không làm đầy ổ cứng.
- **Yêu cầu cho Platform**: Tạo ISM policy.
- **Audit Verify**: Team Audit kiểm tra file cấu hình ISM (JSON).

## 4. [Task 3.2] Xây dựng Grafana Audit Dashboard
- **Mục tiêu Audit**: Tự động hóa việc soi các dấu hiệu bất thường về quyền truy cập thay vì đọc raw log.
- **Yêu cầu cho Platform**: Làm Dashboard track mã lỗi `401 Unauthorized` và `403 Forbidden`.
- **Audit Verify**: Team Audit sử dụng dashboard này hằng ngày để phát hiện truy cập trái phép.
