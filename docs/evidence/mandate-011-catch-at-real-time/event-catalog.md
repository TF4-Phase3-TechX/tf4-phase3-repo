# Event Catalog: Active Threat Detection

Tài liệu này định nghĩa danh sách các sự kiện (events) AWS bị liệt kê vào nhóm "nguy hiểm", cần giám sát theo thời gian thực theo yêu cầu của Mandate 11.

## 1. Các sự kiện cốt lõi (Core Events)
- **`StopLogging` & `DeleteTrail` (CloudTrail):** Cực kỳ nguy hiểm. Kẻ tấn công luôn cố gắng "làm mù" hệ thống giám sát bằng cách tắt ghi log trước khi thực hiện các hành vi phá hoại.
- **`ConsoleLogin` (Root account):** Tài khoản Root AWS không bao giờ nên được dùng trong vận hành hàng ngày. Bất kỳ lần đăng nhập nào cũng là một báo động đỏ (Red Flag).
- **`AuthorizeSecurityGroupIngress`:** Rủi ro mở cổng mạng (VD: SSH 22, RDP 3389) ra toàn bộ Internet (`0.0.0.0/0`).
- **`PutBucketPolicy` & `PutBucketAcl` (S3):** Rủi ro Public Data Exposure. Làm rò rỉ dữ liệu quan trọng ra bên ngoài.
- **`DeleteConfigurationRecorder` (Config):** Hành vi "xóa dấu vết" cấu hình hạ tầng, làm khó quá trình điều tra pháp y (forensic).

## 2. Nhóm sự kiện IAM & Quyền (Identity)
- **`CreateAccessKey`, `AttachRolePolicy`, `PutRolePolicy`, `CreateUser`, `CreateRole`, `UpdateAssumeRolePolicy`:** 
  - **Vì sao nguy hiểm:** Sự thay đổi quyền IAM, đặc biệt là tạo Access Key mới hoặc nâng quyền (Privilege Escalation) là dấu hiệu rõ nhất của việc kẻ tấn công đang leo thang đặc quyền để kiểm soát toàn bộ hệ thống hoặc duy trì quyền truy cập (Persistence).

## 3. Nhóm sự kiện EKS (Kubernetes)
- **`CreateAccessEntry`, `AssociateAccessPolicy`:** 
  - **Vì sao nguy hiểm:** EKS Access Entries cho phép cấp quyền Cluster Admin cho các IAM Role/User bất kỳ. Kẻ tấn công có thể dùng nó để chiếm quyền điều khiển toàn bộ Kubernetes cluster mà không cần chạm vào `aws-auth` ConfigMap cũ.

## 4. Nhóm sự kiện Dữ liệu (Data Events)
- **`GetSecretValue` (SecretsManager) & `GetParameter`/`GetParameters` (SSM Parameter Store):**
  - **Vì sao nguy hiểm:** Bất kỳ nỗ lực nào đọc Secret từ nguồn không xác định đều có thể dẫn đến rò rỉ thông tin đăng nhập database, API keys (ví dụ Slack Webhook URL), hoặc private keys. Hành động kéo secret nhạy cảm này phải bị báo động ngay lập tức nếu xuất phát từ ngoài luồng ứng dụng chính.

## Cơ chế Giảm nhiễu (Allowlisting)
Để tránh "cảnh báo rác" (alert fatigue) khiến đội ngũ bảo mật bỏ lỡ cảnh báo thật, hệ thống áp dụng cơ chế giảm nhiễu tại Lambda:
- **Tự động lọc theo Actor:** Nếu `actor` có chứa chuỗi `role/tf4-github-actions`, hệ thống sẽ tự động bỏ qua (log lại sự kiện trong CloudWatch nhưng không bắn thông báo Slack). CI/CD được coi là an toàn và đã được rà soát code.
- **Tự động lọc theo Cấu hình (vd: Security Group):** Lambda sẽ chỉ báo động nếu Ingress rule mở ra `0.0.0.0/0` (toàn cầu). Những rule hẹp nội bộ sẽ không gây ồn.
