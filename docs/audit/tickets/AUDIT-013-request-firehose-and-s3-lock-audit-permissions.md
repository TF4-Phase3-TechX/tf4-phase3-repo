# [AUDIT-013] Yêu cầu bổ sung quyền verify Amazon Data Firehose và S3 Object Lock cho EKS logs

**Trạng thái**: TO DO  
**Người yêu cầu (Reporter)**: Hoàng + Ty - Nhóm CDO07 (Audit)  
**Người thực hiện (Assignee)**: Nhóm CDO08 (Security/SSO/IAM)  
**Nhóm phối hợp**: Nhóm CDO04 (Observability/Platform)  
**Độ ưu tiên (Priority)**: P0 (Blocker verification EKS logs tamper protection)  
**Epic**: Mandate-04 / Auditability - forensic audit, log integrity, change trail

---

## 1. Bối cảnh (Context)

Để giải quyết rủi ro root account hoặc admin có quyền cao có thể xóa trực tiếp log của EKS Control Plane trong CloudWatch Logs, nhóm CDO07 đã cấu hình giải pháp stream logs gần real-time sang S3 bucket độc lập được bảo vệ bởi **S3 Object Lock COMPLIANCE 90 ngày**:
- Logs được stream từ CloudWatch Logs `/aws/eks/techx-tf4-cluster/cluster` qua **Amazon Data Firehose** (`tf4-eks-audit-logs-firehose`) về S3 bucket `tf4-eks-audit-logs-511825856493`.
- Bucket S3 được cấu hình bật `Object Lock COMPLIANCE mode` trong 90 ngày (WORM), ngăn chặn mọi hành vi xóa/sửa logs kể cả từ root account.

Để Hoàng và Ty có thể kiểm chứng cấu hình này hoạt động đúng theo các checklist trong Mandate 04, profile SSO `TF4-AuditReadOnlyAndAnalyze` cần được bổ sung các quyền đọc cấu hình hạ tầng mới này.

---

## 2. Yêu cầu quyền từ CDO08 (The What)

Nhóm CDO08 vui lòng bổ sung các quyền sau vào Permission Set `TF4-AuditReadOnlyAndAnalyze`:

### 2.1 Amazon Data Firehose (Delivery Stream Verification)
- **`firehose:DescribeDeliveryStream`**: Kiểm tra trạng thái hoạt động (`ACTIVE`) và đích đến của delivery stream `tf4-eks-audit-logs-firehose`.
- **`firehose:ListDeliveryStreams`**: Liệt kê các streams để đối soát.

### 2.2 S3 Bucket (Object Lock & Policy Verification)
- **`s3:GetBucketObjectLockConfiguration` / `s3:GetObjectLockConfiguration`**: Xác minh Object Lock mode là `COMPLIANCE` và retention duration là `90` ngày.
- **`s3:GetBucketPolicy`**: Đọc bucket policy để xác nhận rule explicitly Deny operator xóa logs.
- **`s3:GetBucketVersioning`**: Xác nhận versioning đã bật (bắt buộc đối với Object Lock).
- **`s3:GetBucketLocation`**: Kiểm tra metadata bucket.
- **`s3:ListBucket` & **`s3:GetObject`**: Đọc và liệt kê danh sách file logs trong bucket `tf4-eks-audit-logs-511825856493` để xác thực log EKS đã được chuyển vào S3 thành công.

### 2.3 CloudWatch Logs & IAM Roles (Data Pipeline Verification)
- **`logs:DescribeSubscriptionFilters`**: Xác minh subscription filter của EKS log group đang trỏ chính xác về Firehose stream.
- **`iam:GetRole` / `iam:GetRolePolicy`**: Kiểm tra các policy gắn vào IAM roles `tf4-firehose-to-s3-role` và `tf4-cwl-to-firehose-role` để chắc chắn chúng tuân thủ nguyên tắc least-privilege.

---

## 3. Evidence lỗi hiện tại

Khi chạy lệnh kiểm tra cấu hình S3 Object Lock trên bucket EKS Logs bằng profile `TF4-AuditReadOnlyAndAnalyze`:

```bash
aws s3api get-object-lock-configuration \
  --bucket tf4-eks-audit-logs-511825856493 \
  --profile TF4-AuditReadOnlyAndAnalyze
```

Kết quả:
```text
An error occurred (AccessDenied) when calling the GetObjectLockConfiguration operation: Access Denied
```

Khi chạy lệnh kiểm tra trạng thái Firehose stream:

```bash
aws firehose describe-delivery-stream --delivery-stream-name tf4-eks-audit-logs-firehose \
  --profile TF4-AuditReadOnlyAndAnalyze
```

Kết quả:
```text
An error occurred (AccessDeniedException) when calling the DescribeDeliveryStream operation: User: arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_... is not authorized to perform: firehose:DescribeDeliveryStream on resource: arn:aws:firehose:us-east-1:511825856493:deliverystream/tf4-eks-audit-logs-firehose
```
