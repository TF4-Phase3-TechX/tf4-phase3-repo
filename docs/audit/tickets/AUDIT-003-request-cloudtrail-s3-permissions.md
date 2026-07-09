# [AUDIT-003] [Task] Yêu cầu bổ sung quyền Read-Only (CloudTrail, S3) cho nhóm Audit CDO07

**Trạng thái**: TO DO
**Người yêu cầu (Reporter)**: Nhóm CDO07 (Audit)
**Người thực hiện (Assignee)**: Nhóm CDO08 (Admin SSO)
**Độ ưu tiên (Priority)**: P0 (Blocker cho việc nghiệm thu Task 5)

## 1. Mục đích
Để nhóm CDO07 (Audit) có thể thực hiện kiểm chứng và nghiệm thu hệ thống CloudTrail được ghi nhận an toàn vào Amazon S3 (theo yêu cầu của Task 5), nhóm cần được cấp thêm một số quyền đọc (Read-Only) cụ thể đối với hai dịch vụ này.

## 2. Chi tiết các quyền IAM cần có

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

## 3. Yêu cầu cấu hình (Action for CDO08)
Team DevOps (CDO08) vui lòng bổ sung đoạn policy (Inline Policy hoặc cập nhật Permission Set của CDO07) trên AWS IAM Identity Center với nội dung tham khảo sau:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AuditCloudTrailAndS3ReadOnly",
            "Effect": "Allow",
            "Action": [
                "s3:GetBucketVersioning",
                "s3:ListBucket",
                "s3:GetObject",
                "s3:GetBucketLocation",
                "s3:ListAllMyBuckets",
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
*(Ghi chú: Wildcard `Resource: "*"` là an toàn vì đây đều là các quyền Read/List).*

## 4. Tiêu chí nghiệm thu (Definition of Done)
- [ ] Team CDO08 xác nhận đã cập nhật Permission Set cho nhóm CDO07.
- [ ] Thành viên nhóm CDO07 truy cập được AWS CloudTrail Console và S3 Console mà không gặp lỗi `Access Denied`.
- [ ] CDO07 hoàn tất việc kiểm chứng CloudTrail logs.
