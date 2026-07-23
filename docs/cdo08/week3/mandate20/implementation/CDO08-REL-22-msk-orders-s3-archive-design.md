# CDO08-REL-22 MSK Orders S3 Archive Design

**Owner:** Hoàng Nam
**Team:** CDO08
**Task:** CDO08-REL-22
**Subtask:** Provision encrypted S3 archive for MSK orders
**Ngày cập nhật:** 2026-07-23

Tài liệu này ghi lại thiết kế S3 archive đích cho topic MSK `orders`. Subtask này chỉ tạo đích lưu trữ bền vững ngoài MSK; MSK Connect S3 Sink Connector và kiểm chứng record thật thuộc các subtask tiếp theo.

---

## 1. Mục Tiêu

MSK không có snapshot/backup native tương đương RDS PITR. Vì vậy topic `orders` cần một archive ngoài cluster để có thể replay khi mất cluster hoặc topic.

Đích archive được provision bằng Terraform:

| Field                  | Value                                                          |
| ---------------------- | -------------------------------------------------------------- |
| Bucket                 | `tf4-msk-orders-archive-511825856493-us-east-1`                |
| Prefix                 | `orders/`                                                      |
| Partition convention   | `orders/topic=orders/year=YYYY/month=MM/day=DD/hour=HH/`       |
| Retention              | 35 ngày                                                        |
| Short-term access tier | 7 ngày đầu ở `STANDARD`                                        |
| Long-term access tier  | Sau ngày 7 transition sang `STANDARD_IA` tới khi hết retention |

---

## 2. Security Controls

Bucket được cấu hình:

- Không public access.
- Object ownership `BucketOwnerEnforced`.
- Versioning enabled.
- Default server-side encryption `AES256`.
- Deny non-TLS request.
- Deny operator role thường xóa object/version trong prefix `orders/`.
- Deny operator role thường thay đổi bucket policy, encryption, versioning, lifecycle hoặc delete bucket.

Role chạy Terraform apply không nằm trong nhóm operator bị deny để mọi thay đổi hạ tầng vẫn đi qua quy trình IaC review. Break-glass/root path chỉ dùng khi có sự cố nghiêm trọng.

---

## 3. Lifecycle

Lifecycle rule áp dụng cho prefix `orders/`:

| Rule                              | Value                         |
| --------------------------------- | ----------------------------- |
| Transition                        | Sau 7 ngày sang `STANDARD_IA` |
| Expiration                        | Sau 35 ngày                   |
| Noncurrent version expiration     | Sau 35 ngày                   |
| Abort incomplete multipart upload | Sau 1 ngày                    |

Ý nghĩa:

- 7 ngày đầu giữ ở `STANDARD` để replay/validate nhanh sau sự cố gần.
- Tổng retention 35 ngày đáp ứng nhu cầu lưu dài hơn cho audit hoặc lỗi phát hiện muộn.
- Không giữ vô hạn để tránh cost tăng không kiểm soát.

---

## 4. Connector Contract Cho Subtask 3

MSK Connect S3 Sink Connector ở subtask tiếp theo cần ghi vào:

```text
s3://tf4-msk-orders-archive-511825856493-us-east-1/orders/topic=orders/year=YYYY/month=MM/day=DD/hour=HH/
```

Yêu cầu connector:

- Topic source: `orders`.
- Flush cadence: không vượt quá 15 phút để khớp RPO.
- Payload phải giữ được order ID, timestamp và dữ liệu cần replay.
- IAM role connector chỉ cần quyền put/list/read tối thiểu trên bucket/prefix này.
- Error handling/DLQ sẽ được định nghĩa ở subtask deploy connector.

---

## 5. Out Of Scope

Subtask này chưa thực hiện:

- Chưa deploy MSK Connect Connector.
- Chưa produce marker orders.
- Chưa chứng minh object S3 chứa record thật.
- Chưa đo delivery latency.
- Chưa chạy replay.

Các phần trên thuộc subtask deploy connector và validate archive completeness.
