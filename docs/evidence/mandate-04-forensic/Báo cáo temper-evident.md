# BÁO CÁO RÀ SOÁT KIỂM TOÁN VÀ CẤU HÌNH LOGS TAMPER-EVIDENT

**Mặt trận:** Task Force 4 (TF4) · Dự án XBrain

- **Thời điểm thực hiện:** 21:30 (UTC+7) · Ngày 15/07/2026
- **Người rà soát:** Đinh Văn Ty
- **Trạng thái:** ✅ Hoàn tất rà soát & Đạt tiêu chuẩn kiểm toán

---

# I. KẾT QUẢ RÀ SOÁT CHI TIẾT (AUDIT FINDINGS)

Qua quá trình rà soát độc lập và thực thi các kịch bản đối soát an toàn thông tin tại cụm tài nguyên khu vực **us-east-1**, đội **Audit CDO-07** ghi nhận kết quả như sau:

## 1. Rà soát phân quyền IAM Groups (`docs/iam/group/xxxx/TF4`)

### Kết quả kiểm tra

Đã tiến hành quét toàn bộ các **Policy Documents** áp dụng cho các IAM Group vận hành trong thư mục cấu hình hạ tầng `docs/iam/group/xxxx/TF4`.

### Kết luận an toàn

Không phát hiện bất kỳ lỗ hổng phân quyền dư thừa nào.

Toàn bộ các tài khoản **Operator/On-call** thuộc nhóm này đều bị giới hạn nghiêm ngặt:

- Không sở hữu quyền quản trị S3 ở mức cao nhất (`s3:*`).
- Không có quyền xóa đối tượng:
  - `s3:DeleteObject`
  - `s3:DeleteObjectVersion`
- Không có quyền can thiệp các chính sách xóa trên toàn bộ hệ thống S3 Bucket của dự án.
- Quyền hạn của đội vận hành tuân thủ chặt chẽ nguyên lý **Least Privilege** (Quyền hạn tối thiểu).

---

## 2. Cấu hình bảo vệ kho log tập trung (Audit Storage Protection)

Để đảm bảo bản ghi log hoàn toàn **chống chối bỏ (Non-Repudiation)** và **không thể bị can thiệp** bởi bất kỳ tác nhân nào (kể cả quản trị viên hệ thống), các kho lưu trữ log cốt lõi đã được cấu hình như sau:

### S3 Bucket lưu CloudTrail & EKS Control Plane Logs

- Đã kích hoạt **S3 Object Lock**
- Chế độ:
  - **COMPLIANCE Mode**
- Thời gian lưu giữ:
  - **90 ngày**

### Tính chất bất biến (Immutability)

Trong vòng **90 ngày** kể từ khi log được ghi xuống:

- Không một ai (bao gồm Root AWS, Administrator hoặc kẻ tấn công đã chiếm đặc quyền) có thể:
  - sửa đổi;
  - ghi đè;
  - xóa các file log.

### Log File Validation

AWS CloudTrail đã bật **Log File Validation**, sử dụng:

- Thuật toán băm **SHA-256**
- Chữ ký điện tử (Digital Signature)

Qua đó bảo đảm phát hiện ngay lập tức mọi thay đổi trái phép đối với cấu trúc file log khi thực hiện kiểm chứng.

---

# II. BẰNG CHỨNG CẤU HÌNH (POLICY & ARCHITECTURE EVIDENCE)

Dưới đây là các tài liệu cấu hình thực tế (**Raw Code & Policy Documents**) được trích xuất trực tiếp từ hệ thống làm bằng chứng nghiệm thu cho **Directive #4**.

---

## 1. Bằng chứng chính sách IAM Group (Chặn quyền xóa của Operator)

Đoạn trích xuất chính sách bảo vệ áp dụng cho các IAM Group tại:

```text
docs/iam/group/xxxx/TF4
```

Quy định rõ việc chặn mọi quyền can thiệp vào hệ thống Audit Logs.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOperatorBasicReadWrite",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::tf4-cdo07-audit-logs",
        "arn:aws:s3:::tf4-cdo07-audit-logs/*"
      ]
    },
    {
      "Sid": "ExplicitDenyOperatorDeleteAndTamper",
      "Effect": "Deny",
      "Action": [
        "s3:DeleteObject",
        "s3:DeleteObjectVersion",
        "s3:PutBucketPolicy",
        "s3:PutLifecycleConfiguration",
        "cloudtrail:DeleteTrail",
        "cloudtrail:StopLogging",
        "cloudtrail:UpdateTrail"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## 2. Bằng chứng cấu hình S3 Object Lock Compliance Mode (Terraform)

Bằng chứng khai báo tài nguyên **S3 Bucket** lưu trữ log kiểm toán tập trung được khóa cứng bằng chế độ **Compliance (90 ngày)**.

```terraform
resource "aws_s3_bucket" "audit_logs" {
  bucket        = "tf4-cdo07-audit-logs"
  force_destroy = false # Chặn hành vi hủy bucket từ Terraform

  object_lock_enabled = true # Kích hoạt Object Lock
}

resource "aws_s3_bucket_object_lock_configuration" "audit_lock" {
  bucket = aws_s3_bucket.audit_logs.id

  rule {
    default_retention {
      mode = "COMPLIANCE" # Không thể bypass bởi Admin/Root
      days = 90           # Thời gian lưu giữ theo yêu cầu kiểm toán
    }
  }
}
```

---

## 3. Bằng chứng cấu hình CloudTrail Log File Validation

Đoạn trích cấu hình AWS CloudTrail chứng minh tính năng **Log File Validation** đang được bật.

```json
{
  "TrailList": [
    {
      "Name": "tf4-audit-trail",
      "S3BucketName": "tf4-cdo07-audit-logs",
      "IncludeGlobalServiceEvents": true,
      "IsMultiRegionTrail": true,
      "LogFileValidationEnabled": true,
      "HasCustomEventSelectors": true
    }
  ]
}
```

> **Bằng chứng:** `LogFileValidationEnabled = true` xác nhận tính năng xác thực toàn vẹn file log đã được kích hoạt thành công.

---

# III. KẾT LUẬN & CAM KẾT TUÂN THỦ (AUDIT STATEMENT)

Dựa trên các bằng chứng rà soát thực tế nêu trên, tôi — **Đinh Văn Ty**, đại diện nhóm **Kiểm toán CDO-07** thuộc **Task Force 4**, xin cam kết:

- ✅ Toàn bộ hạ tầng ghi vết (Audit Logging Infrastructure) của TF4 đã đạt trạng thái **Tamper-Evident** ở mức độ cao nhất (**Compliance Level**).
- ✅ Đội ngũ vận hành (**Operator/On-call**) hoàn toàn không có khả năng sửa đổi hoặc tự xóa dấu vết các hành động của mình trong suốt quá trình thử nghiệm và vận hành hệ thống.
- ✅ Hệ thống sẵn sàng tiếp nhận các bài kiểm tra **Digital Forensics**, **Incident Response** và **Audit Verification** trực tuyến từ Ban Kiểm toán và các Mentor.