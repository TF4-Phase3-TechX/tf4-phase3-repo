# [AUDIT-004] [Task] Yêu cầu triển khai CloudTrail/S3 Log Bucket và cấp quyền Read-Only cho nhóm Audit CDO07

**Trạng thái**: TO DO
**Người yêu cầu (Reporter)**: Nhóm CDO07 (Audit)
**Người thực hiện (Assignee)**: Nhóm CDO08 (Admin SSO / Platform)
**Độ ưu tiên (Priority)**: P0 (Blocker cho việc nghiệm thu Task 5)

## 1. Mục đích
Để nhóm CDO07 (Audit) có thể thực hiện kiểm chứng và nghiệm thu hệ thống CloudTrail được ghi nhận an toàn vào Amazon S3 (theo yêu cầu của Task 5), nhóm cần DevOps thực thi cấu hình IaC đã viết sẵn và cấp quyền đọc (Read-Only) cụ thể đối với hai dịch vụ này.

## 2. Yêu cầu triển khai hạ tầng (Action 1 for CDO08)
Đội Audit đã soạn sẵn cấu hình Terraform cho CloudTrail và S3 Log Bucket (có cấu hình chặn public access và bật S3 Versioning) tại file:
*   [cloudtrail.tf](../../../infra/terraform/cloudtrail.tf)

Vui lòng chạy `terraform apply` để deploy tài nguyên này lên tài khoản AWS của TF4.
*   **Tên S3 Bucket lưu log sinh ra:** `tf4-cloudtrail-logs-bucket-<ACCOUNT_ID>`
*   **Tên CloudTrail sinh ra:** `tf4-general-cloudtrail`

## 3. Chi tiết các quyền IAM cần có (Action 2 for CDO08)
Sau khi deploy xong, vui lòng bổ sung đoạn policy (Inline Policy hoặc cập nhật Permission Set của CDO07) trên AWS IAM Identity Center để nhóm Audit có quyền truy cập vào bucket và cấu hình CloudTrail vừa tạo:

**Nhóm 1: Quyền trên Amazon S3 (Nghiệm thu Bucket & Log)**
- `s3:GetBucketVersioning`: Để kiểm tra xem S3 bucket chứa log đã được bật tính năng Versioning (Enabled) hay chưa.
- `s3:ListBucket`: Để liệt kê các đối tượng (log files) bên trong bucket -> Xác nhận có log mới sinh ra.
- `s3:GetObject`: Để đọc nội dung log file (nếu cần xem chi tiết cấu trúc log CloudTrail bên trong).
- `s3:GetBucketLocation`: Giúp S3 Console xác định được Region của bucket khi truy cập qua giao diện web.
- `s3:ListAllMyBuckets` *(Tùy chọn)*: Cho phép nhìn thấy danh sách các bucket trong giao diện AWS Console để dễ điều hướng.

**Nhóm 2: Quyền trên AWS CloudTrail (Kiểm chứng hoạt động của Trail)**
- `cloudtrail:ListTrails` & `cloudtrail:DescribeTrails`: Để xem danh sách các Trail đã cấu hình và cấu hình chi tiết của chúng (ghi vào bucket nào, có multi-region không).
- `cloudtrail:GetTrailStatus`: Để xem Trail đó đang ở trạng thái hoạt động (IsLogging: true) hay đã bị tắt.
- `cloudtrail:GetEventSelectors`: Để kiểm tra xem Trail đang ghi nhận các sự kiện gì (Management events, Data events).

## 4. IAM Policy tham khảo
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AuditS3LogsReadOnly",
            "Effect": "Allow",
            "Action": [
                "s3:GetBucketVersioning",
                "s3:ListBucket",
                "s3:GetObject",
                "s3:GetBucketLocation"
            ],
            "Resource": [
                "arn:aws:s3:::tf4-cloudtrail-logs-bucket-*",
                "arn:aws:s3:::tf4-cloudtrail-logs-bucket-*/*"
            ]
        },
        {
            "Sid": "AuditS3ConsoleNavigation",
            "Effect": "Allow",
            "Action": [
                "s3:ListAllMyBuckets"
            ],
            "Resource": "*"
        },
        {
            "Sid": "AuditCloudTrailRead",
            "Effect": "Allow",
            "Action": [
                "cloudtrail:ListTrails",
                "cloudtrail:DescribeTrails",
                "cloudtrail:GetTrailStatus",
                "cloudtrail:GetEventSelectors"
            ],
            "Resource": "*"
        }
    ]
}
```

## 5. Tiêu chí nghiệm thu (Definition of Done)
- [ ] Code Terraform tại [cloudtrail.tf](../../../infra/terraform/cloudtrail.tf) được apply thành công trên môi trường AWS.
- [ ] Team CDO08 xác nhận đã cập nhật Permission Set cho nhóm CDO07.
- [ ] Thành viên nhóm CDO07 truy cập được AWS CloudTrail Console và S3 Console tại bucket `tf4-cloudtrail-logs-bucket-*` mà không gặp lỗi `Access Denied`.
- [ ] CDO07 hoàn tất việc kiểm chứng CloudTrail logs.

## 6. Ước tính chi phí (Cost Estimation)
Việc kích hoạt AWS CloudTrail và lưu log vào S3 phát sinh chi phí như sau:
- **AWS CloudTrail (Management Events)**: Bản copy đầu tiên (first copy) ghi nhận các sự kiện quản lý (Management Events) là **miễn phí** trên mỗi tài khoản AWS. Do trail này chỉ ghi nhận Management Events nên chi phí kích hoạt CloudTrail là **$0.00/tháng**.
- **Amazon S3 Storage (Lưu trữ logs)**:
  - Giá lưu trữ Standard: ~$0.023 / GB / tháng.
  - S3 Versioning: Chỉ phát sinh dung lượng khi có thao tác chỉnh sửa/ghi đè. Do các file log CloudTrail được ghi mới hoàn toàn theo cấu trúc cây thư mục tuần tự (không ghi đè file cũ), S3 Versioning sẽ không làm nhân đôi dung lượng lưu trữ.
  - Dung lượng log ước tính cho cụm demo/sandbox: < 1 GB / tháng.
  - Chi phí lưu trữ: **Nằm trong khoảng < $0.05 - $0.10 / tháng (Gần như bằng không)**.

**Tổng chi phí dự kiến**: **~$0.00 - $0.10 / tháng** (Hoàn toàn nằm gọn trong ngân sách $300/tuần của TF4).


