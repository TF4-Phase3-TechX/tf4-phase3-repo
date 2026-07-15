# 📝 ARCHITECTURE & COST RESTROSPECTIVE REVIEW REQUEST
**Dự án:** Task Force 4 · Mặt trận XBrain  
**Chủ đề:** Đánh giá luồng lưu trữ Audit Logs bất biến (Tamper-Evident) qua Kinesis Data Firehose  
**Người yêu cầu:** Đội CDO-07 (Auditability) & CDO-08 (Operational Excellence)  
**Trạng thái:** Chờ phê duyệt (Pending Review)  

---

## I. BỐI CẢNH & ĐỘNG LỰC HẠ TẦNG (CONTEXT & MANDATE)

Để đáp ứng nghiêm ngặt các yêu cầu kiểm toán trong **Directive #4 (Forensic Audit Challenge)**, hệ thống phải đảm bảo:
1. **Đường ghi vết toàn diện:** Lưu vết toàn bộ K8s Control Plane Audit Logs và AWS CloudTrail để phục vụ forensic tại chỗ khi có sự cố.
2. **Bản ghi toàn tin (Tamper-Evident):** Chứng minh log không thể bị sửa/xóa tùy tiện bởi bất kỳ ai, kể cả tài khoản có quyền Admin cao nhất.

### Tại sao bắt buộc sử dụng Kinesis Data Firehose?
Mặc dù EKS Control Plane logs mặc định được đẩy về **CloudWatch Logs**, dịch vụ này không hỗ trợ tính năng khóa cứng dữ liệu vật lý (Object Lock). Do đó, giải pháp tối ưu nhất là thiết lập một luồng chuyển tiếp dữ liệu thời gian thực:
* **CloudWatch Subscription Filter** sẽ bắt các event kiểm toán nhạy cảm.
* **Kinesis Data Firehose (KDF)** đóng vai trò là bộ truyền tải (Delivery Stream) trung gian, tự động gom cụm và streaming logs trực tiếp về **Amazon S3 Bucket**.
* Tại **S3 Bucket**, team kích hoạt **Object Lock ở chế độ COMPLIANCE Mode** để biến toàn bộ log thành bất biến, đáp ứng 100% tiêu chí kháng can thiệp của bài toán kiểm toán.

---

## II. PHÂN TÍCH CHI PHÍ THỰC TẾ DỰA TRÊN WORKLOAD 8 NGÀY QUA (COST ANALYSIS)

### 1. Thông số Workload đầu vào
* **Region triển khai:** `us-east-1` (N. Virginia).
* **Kích thước trung bình của 1 Log Event:** **~150 KB** *(Vượt xa ngưỡng tối thiểu 5KB của luật tính phí làm tròn Firehose, nên AWS sẽ tính tiền theo dung lượng thực tế, không bị đội chi phí ảo).*
* **Tần suất nạp vào CloudWatch Logs:** **~170 MB / ngày**.
* **Tổng lượng dữ liệu trong giai đoạn 8 ngày:** $170\text{ MB} \times 8\text{ ngày} = 1,360\text{ MB} \approx \mathbf{1.36\text{ GB}}$.

### 2. Bóc tách chi phí chi tiết (Đơn giá Region us-east-1)

| Dịch vụ | Đơn giá & Cách tính chi tiết tại us-east-1 | Chi phí 8 ngày qua |
| :--- | :--- | :--- |
| **1. CloudWatch Logs** | Phí thu nạp (Ingestion): **$0.50 / GB**<br>Dung lượng thô: $1.36\text{ GB}$ | $1.36 \times \$0.50 = \mathbf{\$0.68}$ |
| **2. Kinesis Data Firehose** | Phí xử lý dữ liệu: **$0.025 / GB**<br>Dung lượng xử lý: $1.36\text{ GB}$ | $1.36 \times \$0.025 = \mathbf{\$0.034}$ |
| **3. Amazon S3 (Standard)** | Phí lưu trữ: **$0.023 / GB / tháng**<br>Phí API PUT/WRITE: **$0.005 / 1,000 reqs** *(Do Firehose gom log thành buffer trước khi ghi nên số lượng requests cực nhỏ).* | **~$0.01** |
| **4. S3 Object Lock & Versioning** | Tính theo dung lượng lưu các phiên bản cũ bảo lưu cứng. | **~$0.005** |
| **TỔNG CỘNG** | **Chi phí vận hành luồng Audit Logs trong 8 ngày qua** | **~ $0.729** |

> **Nhận xét:** Mức chi phí thực tế hiện tại (**~$0.73 cho 8 ngày**) là cực kỳ tối ưu, chiếm tỷ trọng không đáng kể trong tổng ngân sách giới hạn **$300/tuần**. Hệ thống đang chạy rất đúng hướng và an toàn về mặt tài chính.

---

## III. CÁC GIẢI PHÁP TỐI ƯU CHI PHÍ TRONG TƯƠNG LAI (FUTURE COST OPTIMIZATIONS)

Mặc dù chi phí hiện tại đang rất thấp do lượng tải nền nhỏ, tuy nhiên trong tương lai khi hệ thống Storefront chạy Production thật hoặc chịu các đợt Load Test cực hạn, lượng log sinh ra có thể tăng gấp hàng trăm lần. Team đề xuất 3 giải pháp tối ưu chủ động sau:

### 1. Lọc nhiễu ở Tiền tuyến (CloudWatch Subscription Filter Pattern)
* **Giải pháp:** Không đẩy vô điều kiện 100% lượng log 170MB/ngày qua Firehose. Thiết lập **Subscription Filter Patterns** chỉ bắt các log mang tính kiểm toán cao (ví dụ: các lệnh `verb in ["create", "update", "patch", "delete"]`, hoặc hành động liên quan đến `ConfigMap`, `Secrets`, `flagd`).
* **Hiệu quả:** Dự kiến giảm thiểu **70%** dung lượng rác hệ thống chảy qua Firehose và lưu trên S3, bảo vệ túi tiền khi scaling hệ thống.

### 2. Nén dữ liệu chủ động tại Kinesis Firehose (Data Compression)
* **Giải pháp:** Cấu hình tính năng **Gzip hoặc Snappy compression** trực tiếp trên cấu hình Kinesis Data Firehose trước khi ghi file xuống S3.
* **Hiệu quả:** Giảm kích thước tệp tin lưu trữ trên S3 từ **5 đến 10 lần** so với định dạng JSON thô ban đầu, tối ưu hóa tối đa chi phí tích lũy dung lượng lâu dài.

### 3. Vòng đời Log ngắn hạn & Chuyển vùng Lưu trữ (S3 Lifecycle Rules)
* **Giải pháp:** Cấu hình thời gian bảo lưu (Retention) của S3 Object Lock ở mức tối thiểu **7 ngày** (vừa vặn cho một tuần vận hành kiểm toán). Đồng thời áp dụng Lifecycle Rule tự động xóa các phiên bản không còn hiện hành (Non-current versions) ngay khi hết hạn retention.
* **Hiệu quả:** Ngăn chặn việc phình to dung lượng bộ nhớ S3 qua các tuần, giữ mức chi phí lưu trữ cố định ở mức sàn thấp nhất.

---

## IV. ĐỀ XUẤT PHÊ DUYỆT (RECOMMENDATION FOR APPROVAL)

Mô hình **CloudWatch ➔ Kinesis Firehose ➔ S3 Compliance Bucket** chứng minh được hiệu năng xuất sắc về mặt bảo mật (Tamper-Evident tuyệt đối) và cực kỳ tiết kiệm chi phí thực tế tại `us-east-1`. 
Và cũng như đã nói ở bên trên, khi scale out thì vẫn đảm bảo chi phí rất tốt với đề bài đưa ra.

**[ ] Approved** **[ ] Rejected** **[ ] Requires Modification** *Ý kiến đóng góp từ Reviewer:*....................................................................................