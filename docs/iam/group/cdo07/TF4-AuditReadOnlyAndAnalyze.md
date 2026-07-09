# Permission Set: TF4-AuditReadOnlyAndAnalyze

Tài liệu này chi tiết hóa quyền hạn của Permission Set `TF4-AuditReadOnlyAndAnalyze`. Đây là tập hợp quyền chuyên sâu phục vụ cho việc kiểm toán cấu hình, giám sát vết hoạt động (audit trail), xác minh chính sách bảo mật và truy xuất bằng chứng trong dự án TF4.

## 📄 Nội dung Policy (JSON)

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AuditTrailsAndLogsReadOnly",
            "Effect": "Allow",
            "Action": [
                "cloudtrail:LookupEvents",
                "cloudtrail:DescribeTrails",
                "cloudtrail:GetTrail",
                "cloudtrail:GetTrailStatus",
                "cloudtrail:GetEventSelectors",
                "cloudtrail:ListTrails",
                "cloudtrail:ListTags",
                "logs:Describe*",
                "logs:Get*",
                "logs:FilterLogEvents",
                "logs:StartQuery",
                "logs:StopQuery",
                "logs:GetQueryResults"
            ],
            "Resource": "*"
        },
        {
            "Sid": "IdentityAuditAndPolicyGeneration",
            "Effect": "Allow",
            "Action": [
                "iam:Get*",
                "iam:List*",
                "access-analyzer:Get*",
                "access-analyzer:List*",
                "access-analyzer:ValidatePolicy",
                "access-analyzer:StartPolicyGeneration",
                "access-analyzer:GetGeneratedPolicy"
            ],
            "Resource": "*"
        },
        {
            "Sid": "ConfigAuditAndSQLQuery",
            "Effect": "Allow",
            "Action": [
                "config:Describe*",
                "config:Get*",
                "config:List*",
                "config:SelectResourceConfig",
                "config:SelectAggregateResourceConfig"
            ],
            "Resource": "*"
        },
        {
            "Sid": "EvidenceBucketReadOnly",
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::tf4-evidence-log-bucket",
                "arn:aws:s3:::tf4-evidence-log-bucket/*"
            ]
        },
        {
            "Sid": "S3MetadataAudit",
            "Effect": "Allow",
            "Action": [
                "s3:GetBucketVersioning",
                "s3:GetBucketObjectLockConfiguration"
            ],
            "Resource": "*"
        },
        {
            "Sid": "OpenSearchAuditReadOnly",
            "Effect": "Allow",
            "Action": [
                "es:ListDomainNames",
                "es:DescribeElasticsearchDomain",
                "es:DescribeDomains"
            ],
            "Resource": "*"
        },
        {
            "Sid": "KMSAuditAndDecrypt",
            "Effect": "Allow",
            "Action": [
                "kms:Decrypt",
                "kms:DescribeKey",
                "kms:GetKeyPolicy",
                "kms:GetKeyRotationStatus"
            ],
            "Resource": "arn:aws:kms:us-east-1:511825856493:key/*"
        }
    ]
}
```

---

## 🔍 Giải thích chi tiết Quyền hạn

Policy này được cấu thành từ 7 Statements có tính chuyên môn hóa cao:

### 1. `AuditTrailsAndLogsReadOnly` (Nhật ký Audit & CloudTrail)
* **Hành động**: Các hàm liên quan đến CloudTrail và CloudWatch Logs.
* **Mô tả**: Cho phép kiểm tra trạng thái hoạt động của CloudTrail (`DescribeTrails`, `GetTrailStatus`), xem vết sự kiện thao tác API của tài khoản AWS (`LookupEvents`), và thực hiện truy vấn chuyên sâu log bằng CloudWatch Logs Insights.
* **Mục đích**: Truy tìm nguyên nhân sự cố hoặc hoạt động bất thường từ bất kỳ tài khoản/người dùng nào.

### 2. `IdentityAuditAndPolicyGeneration` (Kiểm toán định danh & Phân tích Policy)
* **Hành động**: IAM read APIs và IAM Access Analyzer.
* **Mô tả**: Quyền xem thông tin cấu hình IAM (người dùng, nhóm, vai trò). Đồng thời cho phép sử dụng AWS Access Analyzer để chạy các công cụ kiểm tra chính sách bảo mật (`ValidatePolicy`), bắt đầu tạo chính sách tối ưu hóa dựa trên lịch sử truy cập thực tế (`StartPolicyGeneration`, `GetGeneratedPolicy`).
* **Mục đích**: Thực thi quy tắc "đặc quyền tối thiểu" bằng cách phát hiện các policy quá rộng và tinh chỉnh chúng.

### 3. `ConfigAuditAndSQLQuery` (Lịch sử cấu hình tài nguyên)
* **Hành động**: AWS Config read/select APIs.
* **Mô tả**: Cho phép truy vấn cơ sở dữ liệu cấu hình tài nguyên của hệ thống qua AWS Config (`SelectResourceConfig`, `SelectAggregateResourceConfig`) sử dụng các câu lệnh SQL nâng cao.
* **Mục đích**: Theo dõi lịch sử thay đổi cấu hình hạ tầng theo thời gian và đánh giá mức độ tuân thủ quy chuẩn bảo mật.

### 4. `EvidenceBucketReadOnly` (Truy xuất bằng chứng lưu trữ)
* **Hành động**: `s3:GetObject`, `s3:ListBucket`
* **Tài nguyên**: S3 bucket `tf4-evidence-log-bucket` và toàn bộ các object con của nó.
* **Mô tả**: Cho phép liệt kê và tải xuống các tệp tin lưu trữ bằng chứng kiểm toán nằm trong bucket chuyên dụng của dự án.
* **Mục đích**: Trích xuất báo cáo, snapshot cấu hình hoặc log được lưu trữ dài hạn phục vụ đoàn kiểm toán độc lập.

### 5. `S3MetadataAudit` (Kiểm tra an toàn cấu hình S3)
* **Hành động**: `s3:GetBucketVersioning`, `s3:GetBucketObjectLockConfiguration`
* **Mô tả**: Xem trạng thái kích hoạt quản lý phiên bản (Versioning) và khóa bảo mật dữ liệu không cho phép xóa/ghi đè (Object Lock) trên toàn bộ S3.
* **Mục đích**: Đảm bảo các bucket lưu trữ quan trọng không bị mất mát dữ liệu hoặc giả mạo.

### 6. `OpenSearchAuditReadOnly` (Đọc cấu hình OpenSearch)
* **Hành động**: `es:ListDomainNames`, `es:DescribeElasticsearchDomain`, `es:DescribeDomains`
* **Mô tả**: Cho phép xem danh sách cấu hình và trạng thái của cụm Amazon OpenSearch / Elasticsearch.
* **Mục đích**: Xác định trạng thái của hệ thống tìm kiếm log tập trung.

### 7. `KMSAuditAndDecrypt` (Giải mã & Kiểm toán Khóa mã hóa)
* **Hành động**: `kms:Decrypt`, `kms:DescribeKey`, `kms:GetKeyPolicy`, `kms:GetKeyRotationStatus`
* **Tài nguyên**: Giới hạn trong các KMS Key thuộc tài khoản `511825856493` tại vùng `us-east-1` (`arn:aws:kms:us-east-1:511825856493:key/*`).
* **Mô tả**: Cho phép kiểm tra chính sách của khóa (Key Policy), trạng thái tự động xoay vòng khóa (Key Rotation). Đặc biệt cho phép hành động `kms:Decrypt` (Giải mã) nhằm cho phép các kiểm toán viên giải mã các tệp tin bằng chứng được mã hóa bằng các KMS Key này.
* **Mục đích**: Cho phép đọc các log hoặc tài liệu nén đã được mã hóa ở mức lưu trữ (Rest Encryption) khi tiến hành audit.

---
[⬅️ Quay lại nhóm CDO07](README.md) | [🏡 Quay lại trang chủ IAM Docs](../../README.md)
