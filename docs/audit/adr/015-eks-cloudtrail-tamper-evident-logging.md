# ADR-015: Hệ thống Log kiểm toán bất biến (Tamper-Evident) và cơ chế Forensic cho Mandate-04

Trạng thái: Đã chấp nhận
Ngày: 2026-07-15
Người phụ trách: CDO-07
Jira liên quan: AUDIT-CDO07-MANDATE04-FORENSIC-FRAMEWORK
PR liên quan: N/A

## Bối cảnh

Theo yêu cầu của **Ban Kiểm toán & Tuân thủ (Mandate-04)**, đội TF4 phải cung cấp giải pháp ghi vết hoạt động toàn diện và chống chối bỏ (Tamper-Evident). Ban kiểm toán yêu cầu:
1. **Ghi vết đầy đủ:** Nhật ký hoạt động tầng cluster (EKS Control Plane Audit log) và tầng cloud (AWS CloudTrail) cùng change trail của cơ sở hạ tầng.
2. **Bản ghi toàn tin (Tamper-Evident):** Log không thể bị sửa, ghi đè hoặc xóa bởi bất kỳ ai, kể cả quản trị viên hệ thống (Operator/Admin) hay tài khoản Root.
3. **Quy về danh tính con người:** Mọi hành động lớn hoặc hoạt động on-call phải được gán về danh tính cá nhân cụ thể, không sử dụng tài khoản dùng chung.
4. **Diễn tập Forensic:** Khả năng truy vết và dựng lại timeline sự cố thô dạng JSON (ai làm gì, khi nào) trong thời gian giới hạn dưới 10 phút.
5. **Ràng buộc chi phí:** Giải pháp bảo mật cao nhưng phải nằm trong giới hạn ngân sách $300/tuần của TF4.

## Quyết định

Để giải quyết triệt để các yêu cầu trên, đội CDO-07 đã thống nhất và triển khai kiến trúc hạ tầng kiểm toán sau:

1. **Bật CloudTrail Multi-Region & Log File Validation:**
   - Kích hoạt CloudTrail ở chế độ Multi-region.
   - Bật tính năng **Log File Validation** để tự động tạo ra các file digest chứa mã hash SHA-256 kèm chữ ký điện tử RSA định kỳ mỗi giờ, giúp phát hiện ngay lập tức mọi hành vi sửa đổi log thô.
2. **Bật EKS Control Plane Logging & Stream qua Kinesis Data Firehose:**
   - Bật toàn bộ các luồng log của EKS: `api`, `audit`, `authenticator`, `controllerManager`, `scheduler`.
   - Cấu hình **CloudWatch Subscription Filter** để stream log EKS API Server thời gian thực thông qua **Kinesis Data Firehose (KDF)** đổ trực tiếp về S3.
3. **Bảo vệ log bất biến bằng S3 Object Lock (Compliance Mode):**
   - Lưu trữ toàn bộ CloudTrail log và EKS audit log trên S3 bucket bảo mật `tf4-cdo07-audit-logs`.
   - Kích hoạt **S3 Object Lock** ở chế độ **Compliance Mode** với thời gian bảo lưu (retention) là **90 ngày**. Trong thời gian này, log là bất biến: không một ai (kể cả Hacker, Administrator, AWS Root Account hay AWS Support) có thể chỉnh sửa, ghi đè hoặc xóa log.
4. **Phân tách nhiệm vụ (Separation of Duties) qua IAM Policy:**
   - Chặn quyền Delete log đối với nhóm Operator và Platform Admins bằng chính sách `Explicit Deny` trên các action: `s3:DeleteObject*`, `s3:DeleteObjectVersion*`, `logs:DeleteLogGroup*`, `logs:DeleteLogStream*`, `cloudtrail:StopLogging`, `cloudtrail:UpdateTrail`.
5. **Định danh qua AWS SSO / IAM Identity Store:**
   - Không sử dụng tài khoản dùng chung. Mọi nhân sự on-call và quản trị viên sử dụng AWS Single Sign-On (SSO) cá nhân (ví dụ: `hung.hoangkim`, `ty.dinhvan`, `huan.huynh`) để tương tác, lưu vết rõ danh tính thực tế trong log.

## Các phương án đã cân nhắc

| Phương án | Ưu điểm | Nhược điểm | Kết luận |
| --- | --- | --- | --- |
| **S3 Object Lock - Governance Mode** | Cho phép Admin có quyền đặc biệt bypass retention để dọn dẹp khi cần. | Không đáp ứng tiêu chí kiểm toán chống chối bỏ từ nội bộ (hacker chiếm quyền Admin vẫn xóa được). | **Từ chối** |
| **S3 Object Lock - Compliance Mode** | Khóa cứng vật lý, log hoàn toàn bất tử trong 90 ngày. Bảo vệ log tuyệt đối trước mọi đặc quyền. | Không thể rút ngắn thời gian retention một khi đã ghi (phải ước tính dung lượng và chi phí cẩn thận). | **Chấp nhận** |
| **Lưu log EKS trên CloudWatch Logs mặc định** | Đơn giản, dễ setup, không cần Firehose. | CloudWatch không có Object Lock vật lý chống xóa. Admin/Operator vẫn có thể xóa Log Group. | **Từ chối** (Chuyển sang stream về S3 Compliance) |
| **Stream Log qua KDF về S3 Compliance** | Log được "tẩu tán" khỏi CloudWatch ngay khi vừa sinh ra và khóa cứng tại S3. | Tăng thêm cấu hình KDF và CloudWatch filter. | **Chấp nhận** |

## Hệ quả

- **Tác động tích cực:** Vá 100% các lỗ hổng bảo mật log thô, vượt qua bài kiểm toán Mandate-04 xuất sắc với khả năng verify log integrity thông qua chữ ký số.
- **Đánh đổi:** 
  - Log lưu trữ trên S3 Compliance Mode sẽ không thể xóa trước hạn 90 ngày, tạo ra dung lượng tích lũy cố định.
  - Tăng cấu hình CloudWatch Subscription Filter & Kinesis Data Firehose stream.
- **Chi phí vận hành thực tế:**
  - Dựa trên workload thực tế (~170MB log/ngày), tổng chi phí log bảo mật (CloudWatch Ingestion + KDF + S3 Storage) ở region `us-east-1` là **~$0.64/tuần**, chỉ chiếm chưa đầy **1%** ngân sách tuần của TF4 ($300/tuần).
- **Rủi ro còn lại:** Cấu hình AWS Config để theo dõi cấu hình hạ tầng chỉ bật cho core resources nhằm tiết kiệm chi phí, chấp nhận không bao phủ toàn bộ các resource phụ.

## Kiểm chứng / Evidence

- **File evidence:** 
  - Cấu hình CloudTrail & EKS logs: [aud-17.1-cloudtrail-config.md](../../evidence/mandate-04-forensic/aud-17.1-cloudtrail-config.md)
  - Khóa bất biến S3: [aud-17.3-s3-object-lock-test.md](../../evidence/mandate-04-forensic/aud-17.3-s3-object-lock-test.md)
  - Thử nghiệm xóa log bị chặn: [aud-17.3-separation-test.md](../../evidence/mandate-04-forensic/aud-17.3-separation-test.md)
  - Log diễn tập Forensic thực tế (3/3 Scenarios Pass): [aud-17.2-drill-log.md](../../evidence/mandate-04-forensic/aud-17.2-drill-log.md)
  - Tracing identity: [aud-17.4-identity-mapping.md](../../evidence/mandate-04-forensic/aud-17.4-identity-mapping.md)
- **Đã kiểm chứng runtime:** Có (Đã diễn tập thành công 3 scenario truy vết với mentor trong thời gian trung bình 6 - 7 phút, dưới mức trần 10 phút).

## Rollback / Xem xét lại

Quyết định này là bắt buộc để duy trì trạng thái tuân thủ kiểm toán. Quyết định sẽ được xem xét lại nếu:
- Ngân sách lưu trữ S3 tích lũy tăng quá cao sau 60 ngày (cần xem xét giảm retention xuống 30 ngày nếu được kiểm toán cho phép).
- Có sự thay đổi về chính sách bảo mật hoặc dịch vụ logging của TechX Corp.

## Xác nhận

- Người phụ trách: CDO-07
- Reviewer: Ban quản trị dự án TF4
- Ngày: 2026-07-16
