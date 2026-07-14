# [AUDIT-009] [Task] Yêu cầu CDO08 bật AWS Config Change Trail cho Task 2

**Trạng thái**: TO DO
**Người yêu cầu (Reporter)**: Nhóm CDO07 (Audit)
**Người thực hiện (Assignee)**: Nhóm CDO08 (Admin SSO / Platform)
**Độ ưu tiên (Priority)**: P0 - blocker cho Task 2 và Directive #4
**Account/Region**: `511825856493` / `us-east-1`

## 1. Mục đích

Bật AWS Config để CDO07 có thể soát xét Resource Timeline của hạ tầng lõi, đối chiếu thay đổi với CloudTrail, Jira/PR/ADR và trả lời được câu hỏi: ai thay đổi resource nào, khi nào và nội dung trước/sau khác nhau ra sao.

Ticket này phục vụ trực tiếp:

- Task 2 trong [`docs/audit/JIRA_TASKS.md`](../JIRA_TASKS.md): Soát xét thay đổi cấu hình hạ tầng qua AWS Config.
- [`docs/audit/AUDIT_CHECKLIST.md`](../AUDIT_CHECKLIST.md): mục AWS Config & Change Trace.
- [`DIRECTIVE #4`](../../requirements/mandates/MANDATE-04-auditability-tf4.md): dựng lại timeline thay đổi hạ tầng từ audit log/trace.

## 2. Hiện trạng đã xác minh ngày 14/07/2026

CDO07 đã kiểm tra bằng profile SSO `TF4-AuditReadOnlyAndAnalyze` tại `us-east-1`:

```text
ConfigurationRecorders=[]
ConfigurationRecordersStatus=[]
DeliveryChannels=[]
DeliveryChannelsStatus=[]
totalDiscoveredResources=0
ConfigRules=[]
RetentionConfigurations=[]
```

Các API `config:Describe*`, `config:Get*`, `config:List*` và `config:SelectResourceConfig` đều chạy thành công, không gặp `AccessDenied`. Kết luận: quyền đọc AWS Config của CDO07 đã đủ; blocker hiện tại là AWS Config chưa được triển khai.

## 3. Yêu cầu triển khai hạ tầng cho CDO08

CDO08 triển khai bằng Terraform, không setup thủ công trên Console:

1. Tạo IAM service role cho AWS Config và chỉ cấp quyền cần thiết.
2. Tạo `aws_config_configuration_recorder` tại `us-east-1`.
3. Dùng chế độ `CONTINUOUS` để giữ chi tiết từng thay đổi phục vụ forensic.
4. Tạo `aws_config_delivery_channel` ghi configuration history/snapshot vào S3.
5. Tạo `aws_config_retention_configuration` với retention tối thiểu 30 ngày.
6. Start recorder sau khi delivery channel sẵn sàng.
7. Bảo vệ S3 destination bằng encryption, versioning, public access block và `force_destroy = false`.
8. Operator triển khai thông thường không được có quyền xóa history của chính mình. Ưu tiên Object Lock Governance 30 ngày; nếu defer phải có ADR và compensating control được CDO07 review.

### Resource types cần record

Chỉ record các resource lõi dưới đây để giữ chi phí thấp:

```text
AWS::EKS::Cluster
AWS::EKS::Nodegroup
AWS::EKS::Addon
AWS::IAM::Role
AWS::EC2::VPC
AWS::EC2::SecurityGroup
AWS::EC2::Subnet
AWS::EC2::RouteTable
AWS::EC2::NetworkAcl
AWS::EC2::NatGateway
AWS::EC2::InternetGateway
AWS::S3::Bucket
AWS::CloudTrail::Trail
```

Không bật `all_supported = true` trong giai đoạn đầu. `AWS::Logs::LogGroup` không nằm trong danh sách resource type được AWS Config hỗ trợ nên không đưa vào recorder scope.

## 4. AWS Config Rules

Config Rules không phải blocker để CDO07 đọc Resource Timeline. Sau khi recorder ổn định, CDO08 có thể bổ sung bốn managed rules sau hoặc tạo ADR defer có cost note:

```text
CLOUD_TRAIL_ENABLED
S3_BUCKET_PUBLIC_READ_PROHIBITED
S3_BUCKET_PUBLIC_WRITE_PROHIBITED
VPC_DEFAULT_SECURITY_GROUP_CLOSED
```

Không triển khai Conformance Pack trong ticket này để tránh tăng scope và chi phí trước hạn Directive #4.

## 5. Quyền CDO07 còn thiếu để đối chiếu độc lập

Quyền AWS Config read-only hiện đã đủ. Runtime đã xác nhận các quyền đối chiếu sau vẫn bị từ chối:

```text
eks:ListClusters
ec2:DescribeVpcs
ec2:DescribeSecurityGroups
```

Để đối chiếu đầy đủ các resource types được record, đề nghị bổ sung quyền read-only sau vào Permission Set `TF4-AuditReadOnlyAndAnalyze`:

```json
{
  "Effect": "Allow",
  "Action": [
    "eks:ListClusters",
    "eks:ListNodegroups",
    "eks:ListAddons",
    "eks:DescribeNodegroup",
    "eks:DescribeAddon",
    "ec2:DescribeVpcs",
    "ec2:DescribeSecurityGroups",
    "ec2:DescribeSubnets",
    "ec2:DescribeRouteTables",
    "ec2:DescribeNetworkAcls",
    "ec2:DescribeNatGateways",
    "ec2:DescribeInternetGateways",
    "s3:GetBucketPolicy",
    "s3:GetLifecycleConfiguration",
    "s3:GetObjectRetention"
  ],
  "Resource": "*"
}
```

Không cấp `config:Put*`, `config:Delete*`, `config:Start*`, `config:Stop*`, `s3:Delete*` hoặc `s3:BypassGovernanceRetention` cho CDO07.

## 6. Bài kiểm thử nghiệm thu

Sau khi deploy, CDO08 dùng DeployOperator SSO cá nhân tạo một thay đổi không ảnh hưởng chức năng, ví dụ thêm tag `audit-drill=task-2` vào VPC hoặc Security Group đã chọn. CDO08 cung cấp resource ID, thời gian và Jira/PR liên quan nhưng không cung cấp trước kết quả CloudTrail.

CDO07 phải độc lập:

1. Tìm resource trong AWS Config.
2. Lấy Resource Timeline trước/sau thay đổi.
3. Đối chiếu timestamp với CloudTrail `LookupEvents`.
4. Xác định SSO principal, event name, source IP và request parameters.
5. Kết luận `PASS` hoặc `FAIL` trong `AUDIT_CHECKLIST.md`.

## 7. Definition of Done

- [ ] Terraform PR tạo recorder, delivery channel, retention và S3 destination đã merge/apply thành công.
- [ ] Configuration recorder có `recording=true`.
- [ ] Delivery channel không có delivery error.
- [ ] `totalDiscoveredResources > 0` và có đủ resource lõi trong scope.
- [ ] CDO07 chạy được Resource Timeline/Advanced Query bằng profile Audit mà không gặp `AccessDenied`.
- [ ] CDO07 đối chiếu được một thay đổi kiểm thử với CloudTrail và truy ra người, thời gian, nội dung.
- [ ] Operator không thể xóa configuration history đang trong retention.
- [ ] `docs/audit/AUDIT_CHECKLIST.md` được cập nhật Pass/Fail và link evidence.
- [ ] Chi phí sau deploy được theo dõi và không vượt budget guardrail trong [`AWS_CONFIG_COST_ESTIMATE.md`](../AWS_CONFIG_COST_ESTIMATE.md).

## 8. Chi phí dự kiến

Scope hiện tại có khoảng 65 resource lõi. Continuous recording cùng bốn rules tùy chọn được ước tính khoảng `$0.89-$6.59/tháng`, tương đương `$0.21-$1.52/tuần`. Đề nghị phê duyệt guardrail tối đa `$10/tháng` (`~$2.30/tuần`). Công thức và giả định chi tiết nằm tại [`AWS_CONFIG_COST_ESTIMATE.md`](../AWS_CONFIG_COST_ESTIMATE.md).
