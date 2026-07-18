# Event Catalog: Active Threat Detection

Tài liệu này định nghĩa danh sách các sự kiện (events) AWS bị liệt kê vào nhóm "nguy hiểm", cần giám sát theo thời gian thực theo yêu cầu của Mandate 11. Các sự kiện này được cấu hình bắt trực tiếp bằng AWS EventBridge từ log của CloudTrail.

Nhằm tối ưu chi phí và giới hạn của hệ thống AWS, các sự kiện được chia làm 2 nhóm Rule riêng biệt trên EventBridge.

---

## Định nghĩa Mức độ Cảnh báo (Severity Levels)

Bảng dưới đây định nghĩa phân loại mức độ nghiêm trọng được gắn nhãn bởi Lambda `audit-security-slack-alerts` trước khi gửi lên Slack.

| Mức độ (Severity) | Định nghĩa & Tính chất | Mục tiêu Phản ứng (SLA) | Ví dụ Hành vi |
| :--- | :--- | :--- | :--- |
| 🔴 **CRITICAL** | Hành vi đe dọa sự tồn vong của hệ thống giám sát (làm mù), che giấu dấu vết, hoặc kiểm soát đặc quyền tối thượng (Root/Cluster Admin). | **Ngay lập tức.** Báo động toàn team, On-call Engineer và Security Lead phải can thiệp ngay. Cần báo cáo C-level. | `StopLogging`, Root `ConsoleLogin`, EKS `CreateAccessEntry` |
| 🟠 **HIGH** | Hành vi mở rộng tấn công (leo thang đặc quyền), tạo backdoor, hoặc phơi bày dữ liệu nhạy cảm ra bên ngoài. | **Trong vòng 15 phút.** On-call Engineer tự tiến hành đánh giá (Triage), cách ly và thu hồi đặc quyền hoặc rotate credentials. | `CreateAccessKey`, `GetSecretValue`, Ingress `0.0.0.0/0` |

---

## 1. Nhóm Sự kiện Chỉ Đọc (Read-Only Sensitive Events)
*Được bắt bởi Rule: `cloudtrail_alerts_readonly_sensitive` (với đặc quyền `ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS` để không bị EventBridge drop).*

- **`GetSecretValue` (SecretsManager)**
- **`GetParameter`, `GetParameters`, `GetParametersByPath` (SSM Parameter Store)**
  - **Vì sao nguy hiểm:** Bất kỳ nỗ lực nào đọc Secret từ nguồn không xác định đều có thể dẫn đến rò rỉ thông tin đăng nhập database, API keys, hoặc private keys. Hành động kéo secret nhạy cảm này phải bị báo động ngay lập tức nếu xuất phát từ ngoài luồng ứng dụng chính.

---

## 2. Nhóm Sự kiện Ghi (Write-Only Sensitive Events)
*Được bắt bởi Rule: `cloudtrail_alerts_writeonly_sensitive` (sử dụng state `ENABLED` mặc định).*

### A. AWS CloudTrail (Xóa dấu vết - Evasion)
- **`StopLogging`, `DeleteTrail`, `UpdateTrail`, `PutEventSelectors`**
  - **Vì sao nguy hiểm:** Cực kỳ nguy hiểm. Kẻ tấn công luôn cố gắng "làm mù" hệ thống giám sát bằng cách tắt ghi log hoặc thu hẹp phạm vi log (loại bỏ ReadOnly events) trước khi thực hiện các hành vi phá hoại. Hành vi này kích hoạt báo động `CRITICAL`.

### B. AWS Config (Phá hoại kiểm toán - Audit Destruction)
- **`DeleteConfigurationRecorder`**
  - **Vì sao nguy hiểm:** Hành vi xóa lịch sử thay đổi cấu hình hạ tầng, làm khó quá trình điều tra pháp y (forensic) và đánh giá tuân thủ. Kích hoạt báo động `CRITICAL`.

### C. AWS IAM & Signin (Chiếm đoạt & Leo thang đặc quyền - Privilege Escalation)
- **`ConsoleLogin` (Tài khoản Root)**
  - **Vì sao nguy hiểm:** Tài khoản Root AWS có quyền tối thượng và không bao giờ nên được dùng trong vận hành hàng ngày. Bất kỳ lần đăng nhập nào cũng là một báo động `CRITICAL`.
- **`CreateAccessKey`, `AttachRolePolicy`, `PutRolePolicy`, `CreateUser`, `CreateRole`, `UpdateAssumeRolePolicy`**
  - **Vì sao nguy hiểm:** Dấu hiệu rõ nhất của việc kẻ tấn công đang leo thang đặc quyền để kiểm soát toàn bộ hệ thống hoặc tạo backdoor (duy trì quyền truy cập - Persistence) bằng cách sinh Access Key mới hoặc sửa Trust Policy (`UpdateAssumeRolePolicy`).

### D. Hạ tầng Mạng & Lưu trữ (Phơi bày dữ liệu - Data Exposure)
- **`AuthorizeSecurityGroupIngress` (EC2)**
  - **Vì sao nguy hiểm:** Mở cổng mạng (VD: SSH 22, RDP 3389) ra toàn bộ Internet. Note: Lambda sẽ lọc và chỉ báo động nếu Ingress rule mở ra `0.0.0.0/0` hoặc `::/0` (toàn cầu).
- **`PutBucketPolicy`, `PutBucketAcl` (S3)**
  - **Vì sao nguy hiểm:** Rủi ro làm rò rỉ dữ liệu quan trọng ra bên ngoài. Note: Lambda sẽ lọc và chỉ báo động nếu cấp quyền public.

### E. Dịch vụ Kubernetes (EKS)
- **`CreateAccessEntry`, `AssociateAccessPolicy`**
  - **Vì sao nguy hiểm:** Cấp quyền trực tiếp vào EKS cluster. Kẻ tấn công có thể dùng nó để chiếm quyền điều khiển toàn bộ cluster mà không cần phải chạm vào ConfigMap cũ. Kích hoạt báo động `CRITICAL`.

---

## 3. Cơ chế Giảm nhiễu (Allowlisting)
Để tránh "cảnh báo rác" (alert fatigue) khiến đội ngũ bảo mật bỏ lỡ cảnh báo thật, hệ thống áp dụng cơ chế giảm nhiễu trực tiếp tại Lambda:
- **Lọc theo Actor (CI/CD):** Nếu ARN của `actor` có chứa chuỗi `role/tf4-github-actions`, Lambda sẽ chủ động bỏ qua (log lại vào CloudWatch nhưng không bắn thông báo Slack). Các thao tác từ pipeline CI/CD được coi là an toàn và đã được rà soát từ source code.
- **Lọc theo Cấu hình chi tiết:** Như đã nêu ở trên (Chỉ báo động S3 / SG khi thực sự mở public). Mọi cảnh báo lọt ra Slack đều được đính kèm nhãn `Noise check: ❌ Không khớp allowlist → cảnh báo thật`.
