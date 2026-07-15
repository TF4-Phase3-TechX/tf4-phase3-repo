# Evidence kiểm toán IAM, Root và CloudTrail

## 1. Kiểm soát tài liệu

| Thuộc tính | Giá trị |
| --- | --- |
| Evidence ID | `TF4-CDO07-IAM-CLOUDTRAIL-20260715` |
| Trạng thái | **FAIL - Remediation Required** |
| Người thực hiện | Bá Huân - CDO07 Auditability |
| Thời điểm chốt evidence | 15/07/2026 18:03, múi giờ `Asia/Saigon` |
| Account / Region chính | `511825856493` / `us-east-1` |
| Permission Set | `TF4-AuditReadOnlyAndAnalyze` |
| AWS profile | `cdo07-tf4-auditreadonly` |
| Checklist | [`AUDIT_CHECKLIST.md`](../../audit/AUDIT_CHECKLIST.md) |

## 2. Mục tiêu

Kiểm tra sáu control:

1. Access Analyzer và role có dấu hiệu over-privileged.
2. Root account có được sử dụng trong 30 ngày hay không.
3. Temporary Bootstrap Access đang được khai báo hoặc active.
4. CloudTrail có ghi multi-region và đang giao log hay không.
5. Bucket CloudTrail có bật Versioning và immutability hay không.
6. Quyền truy cập bucket có đáp ứng least privilege hay không.

## 3. Phương pháp

- Chỉ sử dụng AWS CLI read-only và CloudWatch Logs Insights.
- Đọc analyzer/finding, role policy attachment, CloudTrail status, event selectors và S3 bucket controls.
- Tra Root bằng CloudTrail Event History trong cửa sổ `2026-06-15T10:38:04Z` đến `2026-07-15T10:38:04Z`.
- Dùng prefix thực tế trong bucket CloudTrail để xác định 5 Region đang có log.
- Không lưu `AccessKeyId`, session token hoặc raw CloudTrail payload vào Git.

CloudWatch log group chỉ có dữ liệu từ `2026-07-14T14:16:02Z`, nên truy vấn Logs Insights không được dùng làm nguồn duy nhất cho control Root 30 ngày.

## 4. IAM Access Analyzer

| Thuộc tính | Giá trị |
| --- | --- |
| Analyzer | `tf4-iam-analyzer` |
| Type | `ACCOUNT` |
| Status | `ACTIVE` |
| Active findings | 16 |
| Finding type đã kiểm tra | `ExternalAccess` |

Analyzer loại `ACCOUNT` phát hiện external/federated access, không đo action nào đã không được dùng. Ví dụ finding của `tf4-github-actions-terraform-apply` phản ánh OIDC principal `token.actions.githubusercontent.com`, action `sts:AssumeRoleWithWebIdentity`, không phải unused permission finding.

Lệnh `iam:GenerateServiceLastAccessedDetails` bị `AccessDenied`, do đó chưa có Access Advisor report đầy đủ cho toàn bộ role/action.

## 5. Role có quyền rộng

### 5.1. Terraform apply role

| Thuộc tính | Giá trị |
| --- | --- |
| Role | `tf4-github-actions-terraform-apply` |
| AWS managed policies | `IAMFullAccess`, `PowerUserAccess` |
| CloudTrail events quan sát được | 3.419 |
| Dịch vụ AWS đã quan sát | 12 |
| Cặp service/action đã quan sát | 104 |

Usage quan sát được tập trung ở EC2, S3, IAM, EKS, STS, KMS, Budgets, CloudWatch Logs, AWS Config, ECR, CloudTrail và Access Analyzer. `PowerUserAccess` cộng `IAMFullAccess` vẫn rộng hơn đáng kể so với tập API cần thiết của một Terraform pipeline cố định.

Kết luận: **FAIL - chưa least privilege**. Cần tạo customer-managed policy từ Terraform plan/apply thực tế, tách role theo workload và loại AWS managed policies rộng.

### 5.2. EKS admin/Bootstrap declarations

Terraform hiện khai báo 5 principal dùng `AmazonEKSClusterAdminPolicy` ở cluster scope:

| Principal | Ghi chú |
| --- | --- |
| `tf4-github-actions-eks-deploy` | Temporary bootstrap theo [`ADR-003`](../../audit/adr/003-github-actions-cluster-admin-bootstrap.md) |
| `tf4-github-actions-terraform-apply` | CI admin, chưa có deadline downscope rõ ràng |
| `TF4-Admin-BreakGlass` | Break-glass admin |
| `TF4-DeployOperator` | Operator admin |
| `TF4-SecurityIAMSSOManager` | Security/IAM admin |

CloudTrail reconstruction cho thấy cả 5 principal trên có event `ListAssociatedAccessPolicies` thành công vào `2026-07-15T09:39:29Z`. Các association cluster-admin tương ứng đã được tạo trước đó và không thấy event gỡ/xóa sau lần association gần nhất. Đây là evidence gián tiếp cho thấy access entry tồn tại tại thời điểm CI kiểm tra.

CloudTrail cũng phát hiện các association ngoài Terraform:

| Principal | Lịch sử | Đánh giá |
| --- | --- | --- |
| Account Root | Từng được cấp cluster-admin, đã disassociate và delete ngày 09/07 | Đã cleanup |
| `cdo04-vinh` | Từng được cấp cluster-admin, đã disassociate và delete ngày 08/07 | Đã cleanup |
| `cdo04-an` | Được cấp view và cluster-admin ngày 14/07, chưa thấy event disassociate/delete sau đó | **FAIL - nghi ngờ unmanaged admin access** |

Profile Audit vẫn bị từ chối `eks:ListAccessEntries`, `eks:DescribeAccessEntry` và `eks:ListAssociatedAccessPolicies`. Vì vậy control này **FAIL / BLOCKED DIRECT CHECK** cho đến khi CDO08 xác minh `cdo04-an` và bổ sung ba quyền đọc để CDO07 lấy runtime inventory độc lập.

## 6. Root account trong 30 ngày

### 6.1. Kết quả

CloudTrail Event History xác nhận `userIdentity.type=Root` và ARN `arn:aws:iam::511825856493:root`.

| Region có log | Số Root events xác nhận |
| --- | ---: |
| `ap-southeast-1` | Tối thiểu 50 |
| `ap-southeast-2` | 1 |
| `us-east-1` | Tối thiểu 1.000 |
| `us-east-2` | 1 |
| `us-west-2` | 22 |
| **Tổng tối thiểu** | **1.074** |

Hai Region chạm giới hạn truy vấn nên tổng trên là cận dưới, không phải tổng tuyệt đối.

### 6.2. Sự kiện đại diện

| Event time UTC | Region | Event | Read-only | Event ID |
| --- | --- | --- | --- | --- |
| `2026-07-14T22:20:45Z` | `us-east-1` | `ecr:ListImages` | Có | `b85ce10a-4d50-4e1b-9ea5-0ff4242d8618` |
| `2026-07-14T21:39:01Z` | `us-east-1` | `secretsmanager:CreateSecret` | Không | `60538bbd-164f-4708-9aef-8d9a443755a5` |
| `2026-07-09T08:41:43Z` | `us-east-1` | `sso-directory:UpdatePassword` | Không | `b200090a-4e99-4820-a06e-379ea1dabc85` |

IAM account summary trả về:

- `AccountMFAEnabled=1`.
- `AccountAccessKeysPresent=1`.
- Root CLI events dùng root access key; key ID đã được loại bỏ khỏi evidence.

Kết luận: **FAIL - CRITICAL**. Root account đã được dùng cả cho thao tác đọc và ghi trong kỳ kiểm tra. CDO08/account owner cần điều tra owner, vô hiệu hóa hoặc xoay vòng root access key, chuyển automation sang IAM role và chỉ giữ Root cho break-glass.

## 7. CloudTrail multi-region

| Thuộc tính | Giá trị | Đánh giá |
| --- | --- | --- |
| Trail | `tf4-general-cloudtrail` | Ghi nhận |
| Home Region | `us-east-1` | Ghi nhận |
| IsLogging | `true` | **PASS** |
| IsMultiRegionTrail | `true` | **PASS** |
| IncludeGlobalServiceEvents | `true` | **PASS** |
| LogFileValidationEnabled | `true` | **PASS** |
| Latest S3 delivery error | Không có | **PASS** |
| Latest CloudWatch delivery error | Không có | **PASS** |
| Event selectors | Tất cả management events; không có data resources | **PASS trong management plane** |

Trail đáp ứng control đang hoạt động trên các Region trong phạm vi account nhờ `IsMultiRegionTrail=true`. Data events của S3/Lambda không nằm trong event selector hiện tại và phải được review riêng nếu MANDATE-04 yêu cầu audit data plane.

## 8. S3 CloudTrail bucket

Bucket: `tf4-cloudtrail-logs-bucket-511825856493`.

| Control | Giá trị | Đánh giá |
| --- | --- | --- |
| Versioning | `Enabled` | **PASS** |
| MFA Delete | `Disabled` | Ghi nhận |
| Object Lock | `COMPLIANCE`, 90 ngày | **PASS** |
| Public policy | `IsPublic=false` | **PASS** |
| Public Access Block | Bật đủ 4 thuộc tính | **PASS** |
| Encryption | KMS CMK, bucket key enabled | **PASS** |
| Insecure transport | Bucket policy deny `aws:SecureTransport=false` | **PASS** |
| CloudTrail write grant | Chỉ account prefix, có `AWS:SourceArn` và ACL condition | **PASS** |
| Operator delete exception | Terraform apply role được loại khỏi `DenyNonAdminDeleteObject` | **FAIL** |

Object Lock `COMPLIANCE` ngăn xóa version đang retention kể cả đối với Root hoặc principal rộng quyền. Tuy nhiên, `tf4-github-actions-terraform-apply` đang gắn `PowerUserAccess` và được bucket policy loại khỏi deny-delete. Điều này không đạt least privilege, đặc biệt sau khi retention hết hạn.

## 9. Kết luận tổng hợp

| Control | Kết quả |
| --- | --- |
| Access Analyzer hoạt động | **PASS**, nhưng finding cần review |
| Xác định role over-privileged | **FAIL - remediation required** |
| Root không được sử dụng trong 30 ngày | **FAIL - CRITICAL** |
| Temporary Bootstrap runtime inventory | **FAIL / BLOCKED DIRECT CHECK** |
| CloudTrail multi-region đang hoạt động | **PASS** |
| S3 Versioning/immutability | **PASS** |
| Bucket least privilege | **FAIL** |

## 10. Hành động bắt buộc

1. CDO08/account owner điều tra ngay các Root events, đặc biệt `CreateSecret` và `UpdatePassword`.
2. Vô hiệu hóa hoặc xoay vòng root access key; thay automation dùng Root bằng IAM/OIDC role.
3. Downscope `tf4-github-actions-terraform-apply` khỏi `IAMFullAccess` và `PowerUserAccess`.
4. Loại Terraform apply role khỏi ngoại lệ delete của CloudTrail bucket hoặc ghi rõ quy trình break-glass sau retention.
5. Downscope `tf4-github-actions-eks-deploy` theo deadline của ADR-003.
6. Xác minh và gỡ `cdo04-an` cluster-admin nếu không có approval/owner hợp lệ; đưa access entry cần giữ vào Terraform.
7. Bổ sung `eks:ListAccessEntries`, `eks:DescribeAccessEntry`, `eks:ListAssociatedAccessPolicies` cho profile Audit để nghiệm thu độc lập.
8. Cân nhắc `iam:GenerateServiceLastAccessedDetails` nếu CDO07 được giao ownership phân tích unused access.

## 11. Evidence index

| Evidence | Nội dung | Link |
| --- | --- | --- |
| `E-IAM-CT-01` | Runtime evidence đã chuẩn hóa, không chứa credential | [`004-iam-cloudtrail-controls-runtime-evidence.json`](004-iam-cloudtrail-controls-runtime-evidence.json) |
| `E-IAM-CT-02` | Access Analyzer Terraform | [`iam.tf`](../../../infra/terraform/iam.tf) |
| `E-IAM-CT-03` | EKS access declarations | [`eks-access-entries.tf`](../../../infra/terraform/eks-access-entries.tf) |
| `E-IAM-CT-04` | ADR temporary bootstrap | [`ADR-003`](../../audit/adr/003-github-actions-cluster-admin-bootstrap.md) |
| `E-IAM-CT-05` | CloudTrail/S3 controls Terraform | [`cloudtrail.tf`](../../../infra/terraform/cloudtrail.tf) |
| `E-IAM-CT-06` | Checklist Pass/Fail | [`AUDIT_CHECKLIST.md`](../../audit/AUDIT_CHECKLIST.md) |

## 12. Giới hạn

- Không lưu raw CloudTrail event vì payload có access key ID và các trường ngoài allowlist evidence.
- Tổng Root events là cận dưới do giới hạn 1.000 kết quả ở `us-east-1` và lỗi encoding khi phân trang `ap-southeast-1`.
- Profile Audit không có `ec2:DescribeRegions` hoặc `account:ListRegions`; danh sách Region được suy ra từ prefix hiện có trong bucket CloudTrail.
- CloudWatch log group mới có dữ liệu từ 14/07/2026 nên không đại diện đủ 30 ngày.
- Kết luận FAIL về Root không phụ thuộc các giới hạn trên vì nhiều event đã được xác minh trực tiếp là `userIdentity.type=Root`.

## 13. Phê duyệt

| Vai trò | Người xác nhận | Trạng thái | Ngày |
| --- | --- | --- | --- |
| Người lập evidence - CDO07 | Bá Huân | Hoàn thành | 15/07/2026 |
| CDO08 Security reviewer | Chờ điều tra/remediation | Pending | - |
