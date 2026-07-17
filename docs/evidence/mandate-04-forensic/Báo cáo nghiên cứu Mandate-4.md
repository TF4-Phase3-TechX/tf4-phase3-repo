# 📑 BÁO CÁO TỔNG HỢP NGHIÊN CỨU & TRIỂN KHAI HẠ TẦNG KIỂM TOÁN (MANDATE 4)

**Mặt trận:** Task Force 4 (TF4) · Dự án XBrain  
**Người thực hiện:** Đinh Văn Ty (CDO-07 Auditability)  
**Đối tượng gửi:** Mentor & Ban Quản trị Dự án TF4  
**Ngày cập nhật:** 15/07/2026  
**Trạng thái Hạ tầng:** HOÀN THÀNH TRIỂN KHAI (Vá 100% lỗ hổng cấu hình trước hạn)

---

## I. BỐI CẢNH & THÁCH THỨC ĐỀ BÀI (MANDATE ĐẶT RA)

Trong khuôn khổ **Directive #4 (Forensic Audit Challenge)**, yêu cầu trọng tâm không nằm ở việc hệ thống vận hành ổn định, mà nằm ở khả năng **chứng minh sự thật**:
1. **Truy vết không thể chối bỏ:** Bất kỳ hành động vận hành (On-call), thay đổi cấu hình hạ tầng hay can thiệp flag tính năng đều phải được ghi vết tường tận (Ai làm, khi nào, nội dung gì).
2. **Kháng can thiệp tuyệt đối (Tamper-Evident):** Chứng minh dữ liệu log kiểm toán được bảo vệ độc lập, không thể bị chỉnh sửa hoặc xóa bỏ bởi bất kỳ ai, kể cả tài khoản có đặc quyền Admin cao nhất.
3. **Forensic tại chỗ:** Đội ngũ audit phải bốc được bằng chứng thô dạng JSON để dựng lại timeline sự cố trong thời gian giới hạn trước mặt Mentor.

---

## II. NỘI DUNG NGHIÊN CỨU & PHÂN TÍCH KIẾN TRÚC CỐT LÕI

### 1. Phân tích giải pháp lưu trữ bất biến: S3 Object Lock (Compliance Mode)
Để giải quyết bài toán "kháng can thiệp từ nội bộ", tôi đã tiến hành nghiên cứu sâu về các chế độ khóa dữ liệu của AWS:
* **Hạn chế của Governance Mode:** Chế độ này vẫn cho phép các tài khoản có quyền IAM đặc biệt (`s3:BypassGovernanceRetention`) hoặc tài khoản Root AWS thực hiện ghi đè/xóa file log trước hạn bảo lưu. Do đó không đạt tiêu chuẩn kiểm toán gắt gao.
* **Sự vượt trội của Compliance Mode:** Khi kích hoạt chế độ này, một hàng rào vật lý cứng được thiết lập. Log sau khi ghi xuống S3 sẽ hoàn toàn bất tử. Không một ai — kể cả hacker chiếm quyền Root Admin tối cao hay chính AWS Support — có thể sửa đổi hoặc xóa bỏ các bản ghi này trong suốt thời gian retention (đã được cấu hình cứng là **90 ngày**).

### 2. Thiết lập cơ chế phòng thủ đa tầng (Anti-Tampering)
Nhằm đảm bảo dữ liệu log không thể bị can thiệp bởi bất kỳ tác nhân nào, hệ thống phân quyền mới đã được tái cấu trúc:
* **Phân tách nhiệm vụ (Separation of Duties):** Phân định ranh giới tuyệt đối giữa đội Vận hành (CDO-08) và đội Kiểm toán (CDO-07). Nhóm vận hành hạ tầng bị chặn đứng toàn bộ quyền sửa/xóa đối tượng và cấu hình log thông qua chính sách `Explicit Deny`.
* **Bảo vệ EKS Control Plane Logging:** Log của K8s API Server mặc định đổ về CloudWatch Logs (vốn không có Object Lock vật lý). Do đó, tôi đã kích hoạt tính năng **Deletion Protection** trên CloudWatch để chặn đứng hoàn toàn các API xóa Log Group từ phía Admin/Operator. Mọi hành vi cố tình tắt Deletion Protection đều bị CloudTrail ghi vết và kích hoạt EventBridge bắn cảnh báo thời gian thực về Slack/Discord của nhóm Audit.

### 3. Đảm bảo Bản ghi toàn tin (Log Integrity) qua Kinesis Data Firehose
Để tối ưu hóa luồng dữ liệu và bịt lỗ hổng "xóa log trên CloudWatch sau khi bypass khóa", kiến trúc streaming thời gian thực đã được áp dụng:
* **Cơ chế hoạt động:** Tạo một **CloudWatch Subscription Filter** nhằm bắt trọn vẹn EKS Audit logs và đẩy trực tiếp sang **Kinesis Data Firehose (KDF)**. Firehose sẽ tự động gom cụm và streaming dữ liệu near real-time xuống **S3 Bucket bảo mật đã bật Compliance Mode 90 ngày**. Log được "tẩu tán" và khóa cứng ngay khi vừa sinh ra.
* **Xác thực toán học:** Tích hợp **CloudTrail Log File Validation** sử dụng thuật toán mã hóa SHA-256 kèm chữ ký điện tử. Bất kỳ hành vi sửa đổi tệp tin thô nào trên storage đều sẽ làm sai lệch chữ ký và lập tức bị phát hiện khi chạy lệnh kiểm chứng (`aws cloudtrail verify-trail`), đảm bảo tính toàn tin tuyệt đối trước Mentor.

---

## III. BÁO CÁO CHI PHÍ THỰC TẾ (REGION US-EAST-1)

Một phần quan trọng của nghiên cứu là đảm bảo giải pháp an toàn cao nhưng không làm ảnh hưởng đến giới hạn ngân sách **$300/tuần** của dự án. Dựa trên số liệu workload thực tế trong 8 ngày vừa qua (kích thước event trung bình **~150 KB**, dung lượng nạp **~170 MB/ngày**), chi phí chi tiết tại region `us-east-1` như sau:

* **Vượt qua bẫy chi phí ảo:** Do kích thước mỗi log event thực tế của hệ thống (~150 KB) lớn hơn rất nhiều so với ngưỡng tối thiểu 5 KB của Firehose, hệ thống hoàn toàn không bị ảnh hưởng bởi *Luật làm tròn 5KB (5KB Rounding Rule)* của AWS. Tiền được tính chính xác trên dung lượng thực tế.
* **Bảng bóc tách tài chính 8 ngày:**
  * CloudWatch Logs Ingestion ($0.50/GB): **$0.68**
  * Kinesis Data Firehose Processing ($0.025/GB): **$0.034**
  * S3 Storage & Object Lock ($0.023/GB/tháng): **~$0.015**
  * **Tổng chi phí thực tế cho 8 ngày:** **~$0.73** (Tương đương **~$0.64/tuần**)

> **Kết luận tài chính:** Chi phí vận hành toàn bộ luồng log bảo mật chỉ chiếm **chưa đầy 1%** tổng ngân sách tuần của TF4. Kiến trúc này đạt hiệu quả kinh tế cực kỳ cao, sẵn sàng phục vụ cho các đợt scale tải lớn tiếp theo.

---

## IV. LỊCH SỬ KHIỂM TRA & KẾT QUẢ KHẮC PHỤC HẠ TẦNG

* **Ngày kiểm tra (13/07/2026):** Tiến hành khảo sát hiện trạng hệ thống S3 Log Buckets. Kết quả phát hiện tất cả các bucket lưu log **đều chưa có Object Lock, chưa được bật Encryption at rest (SSE)**; duy nhất tính năng *Versioning* đã được bật. Ngay lập tức, tôi đã tạo ticket Jira yêu cầu đội hạ tầng xử lý gấp.
* **Ngày khắc phục (15/07/2026):** Team đã tiến hành vá lỗi hoàn toàn bằng cách cập nhật code Terraform. Qua đợt đối soát lại vào lúc **21:30 ngày 15/07/2026**, tôi xác nhận toàn bộ các S3 Log Buckets đã được trang bị đầy đủ: **Object Lock (Compliance Mode 90 ngày) + Versioning + Encryption at Rest (KMS/AES-256)**.

Hệ thống hạ tầng kiểm toán của TF4 hiện tại đã vào trạng thái **SẴN SÀNG (READY)** cho buổi forensic đánh giá trực tiếp từ Mentor.