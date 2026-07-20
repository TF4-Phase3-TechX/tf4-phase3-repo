# Runbook: Xử lý sự cố bảo mật thời gian thực (Mandate 11)

Tài liệu này hướng dẫn các bước phản ứng nhanh (Incident Response) khi nhận được báo động bảo mật từ kênh Slack. Các cảnh báo này được hệ thống EventBridge bắt trực tiếp theo thời gian thực từ CloudTrail.

## Cam kết phát hiện (Time-To-Detect) & Chống nhiễu
- **Cam kết TTD:** `p95 < 60 giây`. 
- **Nơi đo lường:** Lambda publish `DetectionLatencySeconds` và `NotificationLatencySeconds` vào namespace `Mandate11/DetectionLatency`. Xem công thức và query tại [Cách tính TTD](mandate-11-time-to-detect-measurement.md); kết quả chạy thật được lưu riêng trong [Bằng chứng TTD](../../evidence/mandate-011-catch-at-real-time/time-to-detect-evidence.md).
- **Cơ chế chống nhiễu (Allowlist):** Lambda chỉ bỏ qua automation event khi khớp đồng thời actor, API và resource đã phê duyệt. Critical event luôn cảnh báo, kể cả khi actor là CI/CD hoặc agent nội bộ.

## 1. Phân loại mức độ (Severity) & Lý do

### 🔴 CRITICAL (Báo động Đỏ - Mức độ phá hoại cao / Che giấu dấu vết)
- **Sự kiện:** `StopLogging`, `DeleteTrail`, `UpdateTrail`, `PutEventSelectors`
  - *Vì sao CRITICAL:* Kẻ tấn công đang cố gắng tắt hệ thống giám sát hoặc thu hẹp phạm vi log (làm mù hệ thống) để che giấu các hoạt động độc hại tiếp theo.
- **Sự kiện:** `DeleteConfigurationRecorder`
  - *Vì sao CRITICAL:* Xóa lịch sử thay đổi cấu hình hạ tầng, cản trở việc truy vết và audit.
- **Sự kiện:** `ConsoleLogin` (với tài khoản `Root`)
  - *Vì sao CRITICAL:* Tài khoản Root có quyền tối thượng, việc sử dụng nó luôn vi phạm nguyên tắc bảo mật và tiềm ẩn rủi ro chiếm đoạt tài khoản toàn diện.
- **Sự kiện:** `CreateAccessEntry`, `AssociateAccessPolicy` (EKS)
  - *Vì sao CRITICAL:* Cấp quyền admin cluster trái phép (Kubernetes), mở đường cho việc chiếm quyền điều khiển toàn bộ cluster.

### 🟠 HIGH (Báo động Cam - Xâm phạm dữ liệu / Leo thang đặc quyền)
- **Sự kiện:** `CreateAccessKey`, `CreateUser`, `CreateRole`, `UpdateAssumeRolePolicy`, `AttachRolePolicy`
  - *Vì sao HIGH:* Kẻ tấn công đang leo thang đặc quyền, tạo backdoor (tài khoản phụ) hoặc sửa Trust Policy để có thể quay lại truy cập hệ thống sau này.
- **Sự kiện:** `GetSecretValue`, `GetParameter`, `GetParametersByPath`
  - *Vì sao HIGH:* Rủi ro rò rỉ thông tin nhạy cảm (API Keys, Database Passwords) đã thành hiện thực.
- **Sự kiện:** `AuthorizeSecurityGroupIngress` (mở port `0.0.0.0/0`), `PutBucketPolicy` (mở public S3)
  - *Vì sao HIGH:* Tài nguyên nội bộ bị phơi bày ra Internet.

---

## 2. Quy trình xử lý sự cố (Incident Response Flow)

### Bước 1: Đánh giá nhanh (Triage) - *Phụ trách: On-call Engineer*
Khi thấy Alert nổ trên Slack, hãy trả lời 3 câu hỏi dựa trên thông tin hiển thị sẵn:
1. **Actor là ai?** (Tên user/role). Nếu là SSO role của team, hãy ping xác nhận có đang bảo trì không.
2. **Hành động là gì?** (Kiểm tra xem nó thuộc nhóm CRITICAL hay HIGH).
3. **Từ đâu?** (Source IP). Truy xuất IP đó xem có phải IP văn phòng hoặc VPN hợp lệ không.

### Bước 2: Điều tra chi tiết (Investigate) - *Phụ trách: On-call Engineer*
1. Bấm vào nút **"View in CloudTrail"** đính kèm trong tin nhắn Slack.
2. Kiểm tra Payload JSON của sự kiện:
   - Nếu là **IAM**: Xem Role/Access Key nào vừa được tạo hoặc Trust Policy nào vừa bị đổi.
   - Nếu là **Security Group / S3**: Xem port nào vừa bị mở, bucket nào bị gắn policy public.
   - Nếu là **Secrets Manager**: Xác định tên Secret bị đọc lén.
3. Tìm kiếm trong CloudTrail các hành động khác mà **cùng một Actor** đã thực hiện trong 24 giờ qua để xem mức độ lây lan.

### Bước 3: Cách ly & Xử lý (Containment)
Tùy thuộc vào bản chất sự kiện, thực hiện các biện pháp cách ly:

**A. Rò rỉ / Chiếm đoạt tài khoản Root (ConsoleLogin Root)** - *Phụ trách: Security Lead*
- Báo động ngay cho toàn team bảo mật.
- Đổi mật khẩu Root ngay lập tức.
- Kiểm tra và xóa bất kỳ Access Key nào của Root (nếu có).
- Bật lại hoặc thay đổi thiết bị MFA.
- Liên hệ AWS Support khẩn cấp nếu nghi ngờ tài khoản bị chiếm quyền hoàn toàn.

**B. Rò rỉ / Chiếm đoạt IAM User & Role** - *Phụ trách: Security Lead (On-call Engineer được quyền làm ngay nếu là sự kiện CRITICAL)*
- Vô hiệu hóa ngay lập tức Access Key hoặc User vừa được tạo.
- Đính kèm policy `AWSDenyAll` tạm thời vào Role/User bị nghi ngờ.
- Thu hồi (Revoke) các session SSO / STS hiện tại của Actor.

**C. Rò rỉ dữ liệu (Secrets / SSM)** - *Phụ trách: On-call Engineer*
- **Phải Rotate (Đổi) Secret đó ngay lập tức** ở cả phía AWS và phía dịch vụ thứ 3 (Slack, RDS, v.v.).

**D. Phá hoại hạ tầng / Xóa dấu vết (Trail Blinding)** - *Phụ trách: Security Lead*
- LƯU Ý: Mọi nỗ lực `StopLogging` hoặc `UpdateTrail` sẽ bị chặn bởi SCP (theo Mandate-12). Hãy kiểm tra CloudTrail:
  - Nếu kết quả trả về `AccessDenied`: Xác nhận SCP đã hoạt động tốt. Tiến hành điều tra Actor.
  - Nếu sự kiện thành công (Trail thực sự bị tắt): Bật lại ngay lập tức (`aws cloudtrail start-logging`) VÀ báo động khẩn cấp (Escalate) vì chốt chặn SCP đã thất bại.

### Bước 4: Khôi phục và Báo cáo (Recovery & Post-Mortem) - *Phụ trách: Security Lead + On-call Engineer*
- Gửi thông báo đến C-Level qua kênh `#security-incidents-execs`.
- Khôi phục lại hạ tầng theo cấu hình Terraform (chạy lại `terraform apply` nếu cấu hình bị can thiệp bằng tay).
- Ghi lại báo cáo sự cố (Post-Mortem), xác định nguyên nhân (Root Cause) vì sao kẻ tấn công lọt qua được và bổ sung các chốt chặn IAM chặt chẽ hơn.
