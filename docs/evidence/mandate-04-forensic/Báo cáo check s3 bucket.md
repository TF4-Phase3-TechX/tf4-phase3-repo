# BÁO CÁO KIỂM TRA & KHẮC PHỤC CẤU HÌNH BẢO MẬT S3 LOG BUCKETS

**Mặt trận:** Task Force 4 (TF4) · Dự án XBrain

- **Người thực hiện:** Đinh Văn Ty (CDO-07 Auditability)
- **Thời gian kiểm tra:** Ngày 13/07/2026
- **Thời gian hoàn tất khắc phục:** Ngày 15/07/2026
- **Trạng thái:** ✅ **HOÀN THÀNH (100% Đạt tiêu chuẩn an toàn kiểm toán)**

---

# I. HIỆN TRẠNG TRƯỚC KHI KHẮC PHỤC

**(Khảo sát ngày 13/07/2026)**

Vào ngày **13/07/2026**, đội **Audit CDO-07** đã tiến hành rà soát cấu hình bảo mật chuyên sâu đối với toàn bộ các **S3 Buckets** chịu trách nhiệm lưu trữ dữ liệu log kiểm toán (bao gồm **AWS CloudTrail** và **EKS Control Plane Logging**) tại khu vực **`us-east-1`**.

Kết quả khảo sát ban đầu ghi nhận một số lỗ hổng bảo mật ở các tiêu chí cốt lõi như sau:

| S3 Log Bucket | Object Lock (Compliance) | Bucket Versioning | Encryption at Rest (SSE) | Trạng thái đánh giá |
| :--- | :---: | :---: | :---: | :--- |
| `tf4-cdo07-audit-logs` | ❌ Chưa bật | ✅ Đã bật | ❌ Chưa bật | **KHÔNG ĐẠT** (Rủi ro chối bỏ & lộ lọt dữ liệu log) |

## Chi tiết các phát hiện (Findings)

### 1. Thiếu Object Lock

Việc chưa kích hoạt **S3 Object Lock** khiến các file log có nguy cơ:

- Bị ghi đè.
- Bị xóa bỏ hoàn toàn.
- Bị chỉnh sửa bởi các tài khoản có quyền `write/delete` (bao gồm cả Operator).

### 2. Thiếu Encryption at Rest

Dữ liệu log chưa được mã hóa khi lưu trữ trên hạ tầng AWS, chưa đáp ứng yêu cầu về:

- **Data-at-Rest Security**
- Bảo vệ dữ liệu nhạy cảm khi lưu trữ.

### 3. Điểm đạt

Tính năng **Bucket Versioning** đã được kích hoạt từ trước, cho phép lưu giữ các phiên bản của đối tượng.

---

# II. QUÁ TRÌNH XỬ LÝ & KHẮC PHỤC SỰ CỐ (TIMELINE)

## Ngày 13/07/2026 — Phát hiện & Lưu vết

Ngay sau khi phát hiện các lỗi cấu hình:

- Ghi nhận đầy đủ hiện trạng.
- Tạo các ticket khẩn trên Jira.
- Gửi yêu cầu phối hợp xử lý (Action Items) tới đội vận hành hạ tầng **CDO-08**.
- Thống nhất phương án cấu hình lại bằng Terraform.

---

## Ngày 14/07/2026 — Xây dựng cấu hình an toàn

Đội kỹ thuật tiến hành:

- Xây dựng Terraform bổ sung:
  - **S3 Object Lock**
  - **Compliance Mode (90 ngày)**
- Kích hoạt mã hóa phía máy chủ (**Server-side Encryption**).
- Thử nghiệm cấu hình trước khi triển khai.

---

## Ngày 15/07/2026 — Triển khai & Nghiệm thu

Thực hiện:

```bash
terraform apply
```

Sau khi triển khai, tiến hành rà soát độc lập (Double-check) vào lúc:

> **21:30 ngày 15/07/2026**

Kết quả xác nhận:

- ✅ Toàn bộ các lỗ hổng bảo mật cấu hình của **S3 Log Buckets** đã được khắc phục hoàn toàn.

---

# III. KẾT QUẢ SAU KHI KHẮC PHỤC

**(Cập nhật ngày 15/07/2026)**

Toàn bộ các S3 Buckets phục vụ công tác kiểm toán của TF4 hiện đã đáp ứng đầy đủ các yêu cầu bảo mật.

| S3 Log Bucket | Object Lock (Compliance) | Bucket Versioning | Encryption at Rest (SSE) | Trạng thái hiện tại |
| :--- | :---: | :---: | :---: | :--- |
| `tf4-cdo07-audit-logs` | ✅ Đã bật (90 ngày) | ✅ Đã bật | ✅ Đã bật (AES-256) | **HOÀN TOÀN ĐẠT CHUẨN** |

---

# IV. BẰNG CHỨNG CẤU HÌNH THỰC TẾ (CONFIGURATION EVIDENCE)

Dưới đây là đoạn mã Terraform đã được áp dụng để cấu hình S3 Bucket lưu trữ log kiểm toán.

```hcl
# 1. Khai báo S3 Bucket lưu trữ log kiểm toán
resource "aws_s3_bucket" "audit_logs" {
  bucket        = "tf4-cdo07-audit-logs"
  force_destroy = false # Ngăn chặn việc xóa bucket từ mã nguồn

  object_lock_enabled = true # BẮT BUỘC: Kích hoạt Object Lock vật lý
}

# 2. Cấu hình bảo lưu cứng bất biến (Object Lock)
resource "aws_s3_bucket_object_lock_configuration" "audit_lock" {
  bucket = aws_s3_bucket.audit_logs.id

  rule {
    default_retention {
      mode = "COMPLIANCE" # Chặn mọi quyền xóa kể cả Root Admin
      days = 90           # Thời gian lưu giữ theo yêu cầu kiểm toán
    }
  }
}

# 3. Cấu hình Bucket Versioning
resource "aws_s3_bucket_versioning" "audit_versioning" {
  bucket = aws_s3_bucket.audit_logs.id

  versioning_configuration {
    status = "Enabled"
  }
}

# 4. Cấu hình mã hóa dữ liệu lưu trữ (Encryption at Rest)
resource "aws_s3_bucket_server_side_encryption_configuration" "audit_encryption" {
  bucket = aws_s3_bucket.audit_logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256" # Mã hóa mặc định bằng AES-256
    }
  }
}
```

---

# V. ĐÁNH GIÁ TÍNH TOÀN VẸN & AN TOÀN HỆ THỐNG (AUDIT CONCLUSION)

Sau khi hoàn tất quá trình khắc phục, hệ thống đáp ứng các yêu cầu quan trọng sau:

## 1. Chống chối bỏ (Non-Repudiation)

Ngay cả khi kẻ tấn công hoặc kỹ sư vận hành chiếm được đặc quyền cao nhất:

- Không thể sửa đổi log.
- Không thể ghi đè log.
- Không thể xóa dữ liệu log trong thời gian **90 ngày** nhờ cơ chế **Object Lock (Compliance Mode)**.

---

## 2. An toàn dữ liệu (Data Confidentiality)

Toàn bộ dữ liệu log được mã hóa bằng chuẩn **AES-256** trước khi lưu xuống hệ thống lưu trữ vật lý của AWS, góp phần:

- Bảo vệ dữ liệu khi lưu trữ (Encryption at Rest).
- Giảm thiểu rủi ro rò rỉ thông tin ở cấp độ hạ tầng.

---

## 3. Mức độ sẵn sàng kiểm toán

Hệ thống Audit Logging của **Task Force 4** hiện đáp ứng đầy đủ các yêu cầu về:

- ✅ Log Integrity
- ✅ Data Protection
- ✅ Tamper Resistance
- ✅ Audit Readiness

Qua đó sẵn sàng phục vụ công tác đánh giá và kiểm toán trong **Mandate 4**.