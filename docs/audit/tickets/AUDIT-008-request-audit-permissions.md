# [Permissions] Yêu cầu bổ sung quyền đọc cho Audit Profile (AUDIT-008)

## 1. Tóm tắt vấn đề
Trong quá trình audit các dịch vụ AWS, profile `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882` (dùng bởi CDO07) bị thiếu một số quyền `Read` và `List` quan trọng dẫn đến việc không thể thu thập đủ evidence (bằng chứng) cho báo cáo kiểm toán. 

## 2. Chi tiết các quyền đang thiếu (Missing Permissions)

### 2.1. AWS CloudTrail
- Hành động bị từ chối: `cloudtrail:ListEventDataStores`
- Lý do: Bị lỗi `is not authorized to perform: cloudtrail:ListEventDataStores`. Quyền này cần thiết để liệt kê và kiểm toán các Event Data Stores trong CloudTrail Lake (phục vụ việc lưu trữ và truy vấn event nâng cao).

### 2.2. Amazon EKS
- Hành động bị từ chối: `eks:ListClusters`, `eks:DescribeCluster`
- Lý do: Lệnh `aws eks list-clusters` trả về `AccessDeniedException`. Cần quyền này để liệt kê các cluster hiện có và xem metadata cấu hình mạng (CIDR, endpoint public/private) nhằm phục vụ công việc audit EKS (AUD-05).

## 3. Yêu cầu hành động cho DevOps (CDO08)
Vui lòng cập nhật policy/role của SSO Permission Set `TF4-AuditReadOnlyAndAnalyze` bằng cách thêm các quyền sau vào policy:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowAuditCloudTrailLakeAndEKS",
            "Effect": "Allow",
            "Action": [
                "cloudtrail:ListEventDataStores",
                "cloudtrail:GetEventDataStore",
                "eks:ListClusters",
                "eks:DescribeCluster"
            ],
            "Resource": "*"
        }
    ]
}
```

## 4. Tiêu chí nghiệm thu (DoD)
- DevOps apply thành công cập nhật cấu hình IAM/SSO Permission Set bằng Terraform.
- Audit team chạy thành công các lệnh `aws cloudtrail list-event-data-stores` và `aws eks list-clusters` mà không bị `AccessDenied`.
