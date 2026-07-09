# [IAM] Yêu cầu bổ sung quyền cho Audit Team Role (AUDIT-006)

## 1. Mục đích
Dựa trên kết quả rà soát thực tế, Role `TF4-AuditReadOnlyAndAnalyze` của nhóm Audit (CDO07) hiện vẫn còn thiếu một số quyền Read-Only để có thể thực thi đầy đủ các tác vụ nghiệm thu. 

Đặc biệt, việc thiếu quyền đọc `budgets`, `eks`, `rds` và các dịch vụ bảo mật khiến nhóm Audit bị "block" khi kiểm chứng các bằng chứng liên quan đến Kubernetes workload và Cost optimization.

## 2. Chi tiết quyền cần cấp thêm
Nhóm Audit đã cập nhật lại file Policy `docs/iam/group/cdo07/TF4-AuditReadOnlyAndAnalyze.md`. Các quyền bổ sung bao gồm:

**S3MetadataAudit (Cập nhật thêm):**
- `s3:GetEncryptionConfiguration`
- `s3:GetBucketPublicAccessBlock`

**ExtendedAuditReadOnly (Hoàn toàn mới):**
- `budgets:ViewBudget`
- `eks:DescribeCluster`
- `rds:DescribeDBInstances`
- `guardduty:ListDetectors`
- `securityhub:DescribeHub`

## 3. Yêu cầu hành động cho DevOps (CDO08)
- Nhờ team DevOps update file JSON định nghĩa Role của nhóm CDO07 theo như phiên bản MD mới nhất đã được nhóm Audit push lên.
- Chạy `terraform apply` để cấp bổ sung các quyền này.

## 4. Tiêu chí nghiệm thu (DoD)
- DevOps xác nhận đã apply Terraform.
- Audit Team thử chạy các lệnh AWS CLI đọc EKS, RDS và AWS Budgets thành công mà không bị AccessDenied.
