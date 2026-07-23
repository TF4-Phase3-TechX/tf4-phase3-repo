# CDO08-REL-22 MSK Orders S3 Archive Evidence

**Owner:** Hoàng Nam  
**Team:** CDO08  
**Task:** CDO08-REL-22  
**Subtask:** Provision encrypted S3 archive for MSK orders  
**Ngày ghi nhận:** 2026-07-23  

Tài liệu này ghi lại evidence cho S3 archive destination của MSK topic `orders`. Evidence không chứa secret, credential hoặc payload dữ liệu production.

---

## 1. Output Của Subtask

Subtask này cần tạo ra các output sau:

- S3 bucket/prefix riêng cho archive event `orders`.
- Encryption, versioning và lifecycle theo ADR.
- Public access block.
- Bucket policy ngăn normal operator xóa archive.
- Naming/partition convention để connector có thể ghi dữ liệu theo topic/thời gian và REL-25 có thể replay.

Kết luận hiện tại:

| Hạng mục | Trạng thái | Evidence chính |
| --- | --- | --- |
| Bucket riêng | PASS | `tf4-msk-orders-archive-511825856493-us-east-1` |
| Prefix riêng | PASS | `orders/` |
| Versioning | PASS | `Status=Enabled` |
| Encryption | PASS | `SSEAlgorithm=AES256` |
| Public access block | PASS | 4 cấu hình public access đều `true` |
| Lifecycle 7/35 ngày | PASS | transition 7 ngày sang `STANDARD_IA`, expiration 35 ngày |
| Normal operator delete guard | PASS | Bucket policy deny delete object/version trong `orders/*` |
| Partition convention | PASS | `orders/topic=orders/year=YYYY/month=MM/day=DD/hour=HH/` |

---

## 2. Terraform Apply Outputs

Sau khi PR hạ tầng được merge và CD apply thành công, Terraform output ghi nhận:

```text
msk_orders_archive_bucket_arn = "arn:aws:s3:::tf4-msk-orders-archive-511825856493-us-east-1"
msk_orders_archive_bucket_name = "tf4-msk-orders-archive-511825856493-us-east-1"
msk_orders_archive_partition_convention = "orders/topic=orders/year=YYYY/month=MM/day=DD/hour=HH/"
msk_orders_archive_prefix = "orders/"
```

Kết luận:

- Archive bucket đã được tạo bằng Terraform.
- Prefix reserved cho MSK orders archive là `orders/`.
- Partition convention đã được xuất qua Terraform output để subtask MSK Connect dùng lại.

---

## 3. Versioning

Lệnh kiểm tra:

```powershell
aws s3api get-bucket-versioning `
  --bucket tf4-msk-orders-archive-511825856493-us-east-1 `
  --profile tf4
```

Output:

```json
{
    "Status": "Enabled"
}
```

Kết luận: bucket đã bật versioning.

---

## 4. Public Access Block

Lệnh kiểm tra:

```powershell
aws s3api get-public-access-block `
  --bucket tf4-msk-orders-archive-511825856493-us-east-1 `
  --profile tf4
```

Output:

```json
{
    "PublicAccessBlockConfiguration": {
        "BlockPublicAcls": true,
        "IgnorePublicAcls": true,
        "BlockPublicPolicy": true,
        "RestrictPublicBuckets": true
    }
}
```

Kết luận: bucket chặn public access ở cả 4 lớp.

---

## 5. Encryption

Lệnh kiểm tra:

```powershell
aws s3api get-bucket-encryption `
  --bucket tf4-msk-orders-archive-511825856493-us-east-1 `
  --profile tf4
```

Output:

```json
{
    "ServerSideEncryptionConfiguration": {
        "Rules": [
            {
                "ApplyServerSideEncryptionByDefault": {
                    "SSEAlgorithm": "AES256"
                },
                "BucketKeyEnabled": false,
                "BlockedEncryptionTypes": {
                    "EncryptionType": [
                        "SSE-C"
                    ]
                }
            }
        ]
    }
}
```

Kết luận: bucket có server-side encryption mặc định bằng `AES256`.

---

## 6. Lifecycle 7/35 Ngày

Lệnh kiểm tra:

```powershell
aws s3api get-bucket-lifecycle-configuration `
  --bucket tf4-msk-orders-archive-511825856493-us-east-1 `
  --profile tf4
```

Output chính:

```json
{
    "Rules": [
        {
            "ID": "orders-archive-7-day-standard-35-day-retention",
            "Filter": {
                "Prefix": "orders/"
            },
            "Status": "Enabled",
            "Transitions": [
                {
                    "Days": 7,
                    "StorageClass": "STANDARD_IA"
                }
            ],
            "Expiration": {
                "Days": 35
            },
            "NoncurrentVersionExpiration": {
                "NoncurrentDays": 35
            },
            "AbortIncompleteMultipartUpload": {
                "DaysAfterInitiation": 1
            }
        }
    ]
}
```

Kết luận:

- Rule lifecycle chỉ áp dụng cho prefix `orders/`.
- Object current version giữ ở `STANDARD` trong 7 ngày đầu.
- Sau 7 ngày chuyển sang `STANDARD_IA`.
- Object expire sau 35 ngày.
- Noncurrent version cũng expire sau 35 ngày.
- Incomplete multipart upload được dọn sau 1 ngày.

---

## 7. Bucket Policy Delete Guard

Lệnh kiểm tra:

```powershell
aws s3api get-bucket-policy `
  --bucket tf4-msk-orders-archive-511825856493-us-east-1 `
  --profile tf4 `
  --query Policy `
  --output text
```

Output chính có các statement:

```text
DenyInsecureTransport
DenyOperatorArchiveControlDeletion
DenyOperatorArchiveObjectDeletion
```

Các deny chính:

```text
DenyInsecureTransport:
- Action: s3:*
- Condition: aws:SecureTransport=false

DenyOperatorArchiveControlDeletion:
- s3:DeleteBucket
- s3:DeleteBucketPolicy
- s3:PutBucketPolicy
- s3:PutBucketPublicAccessBlock
- s3:PutBucketVersioning
- s3:PutEncryptionConfiguration
- s3:PutLifecycleConfiguration

DenyOperatorArchiveObjectDeletion:
- s3:DeleteObject
- s3:DeleteObjectTagging
- s3:DeleteObjectVersion
- Resource: arn:aws:s3:::tf4-msk-orders-archive-511825856493-us-east-1/orders/*
```

Kết luận:

- Bucket policy chặn request không dùng TLS.
- Normal operator roles không thể xóa archive object/version trong prefix `orders/*`.
- Normal operator roles không thể tự ý thay đổi các control bảo vệ bucket như lifecycle, encryption, versioning, public access block hoặc bucket policy.

---

## 8. Partition Convention

Partition convention đã ghi trong Terraform output và docs implementation:

```text
orders/topic=orders/year=YYYY/month=MM/day=DD/hour=HH/
```

Đường dẫn đầy đủ dự kiến cho MSK Connect S3 Sink:

```text
s3://tf4-msk-orders-archive-511825856493-us-east-1/orders/topic=orders/year=YYYY/month=MM/day=DD/hour=HH/
```

Ý nghĩa:

- Có prefix riêng cho orders archive.
- Có partition theo topic để mở rộng nếu cần thêm topic sau này.
- Có partition theo thời gian để replay theo khoảng sự cố và đo archive latency.

---

## 9. Current Object State

Lệnh kiểm tra:

```powershell
aws s3 ls s3://tf4-msk-orders-archive-511825856493-us-east-1/orders/ `
  --recursive `
  --profile tf4
```

Kết quả: không có object tại thời điểm kiểm tra.

Diễn giải:

- Đây là trạng thái hợp lý cho subtask này vì MSK Connect S3 Sink Connector chưa được deploy.
- Subtask tiếp theo sẽ cấu hình connector để ghi records thật vào bucket/prefix này.

---

## 10. Out Of Scope

Subtask này chưa thực hiện:

- Chưa deploy MSK Connect S3 Sink Connector.
- Chưa tạo IAM role cho connector.
- Chưa produce marker order.
- Chưa verify object chứa payload order thật.
- Chưa đo delivery latency/RPO 15 phút.
- Chưa chạy replay.

Các phần trên thuộc các subtask tiếp theo của REL-22.

---

## 11. Kết Luận

Subtask `Provision encrypted S3 archive for MSK orders` đã đạt acceptance criteria:

- Bucket private, encrypted và versioned.
- Lifecycle khớp ADR: 7 ngày đầu ở `STANDARD`, transition sang `STANDARD_IA`, retention tổng 35 ngày.
- Bucket policy ngăn normal operator xóa archive trong prefix `orders/*`.
- Naming/partition convention đã được ghi trong Terraform output và docs.
- Không thay đổi MSK cluster runtime, application workload hoặc production data.

