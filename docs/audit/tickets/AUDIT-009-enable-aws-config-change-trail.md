# [AUDIT-009] [Task] Yêu cầu CDO08 bật AWS Config Change Trail cho Task 2

**Trạng thái**: TO DO
**Người yêu cầu (Reporter)**: Nhóm CDO07 (Audit)
**Người thực hiện (Assignee)**: Nhóm CDO08 (Admin SSO / Platform)
**Độ ưu tiên (Priority)**: P0 - blocker cho Task 2 và Directive #4
**Account/Region**: `511825856493` / `us-east-1`
**Phạm vi ownership của ticket**: AWS Config change trail và evidence Task 2

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

1. Ưu tiên dùng AWS Config service-linked role. Chỉ dùng custom IAM role khi có lý do được ghi rõ và vẫn tuân thủ least privilege.
2. Tạo S3 staging bucket nhận delivery trực tiếp từ AWS Config, bật SSE-S3 (`AES256`), versioning, Object Ownership `BucketOwnerEnforced`, public access block và `force_destroy = false`. Bucket này không được bật default Object Lock retention vì AWS Config không hỗ trợ delivery channel tới bucket có cấu hình đó.
3. Tạo riêng S3 WORM archive bucket ngay từ đầu với SSE-S3 (`AES256`), versioning, Object Ownership `BucketOwnerEnforced`, `object_lock_enabled = true`, default retention mode `COMPLIANCE` tối thiểu 30 ngày, public access block và `force_destroy = false`. Không dùng `GOVERNANCE` và không defer bằng ADR/compensating control.
4. Tạo IAM replication role và Same-Region Replication từ staging bucket sang WORM archive bucket. Chỉ cấp các quyền replication cần thiết trên đúng bucket/prefix; tắt delete-marker replication để thao tác xóa tại staging không che khuất bản archive. Replication rule phải hoạt động trước khi start recorder để mọi object AWS Config mới đều được sao chép và nhận default retention tại archive.
5. Cấu hình bucket policy theo separation of duties: AWS Config chỉ ghi prefix `aws-config/` ở staging; replication role chỉ đọc prefix này và ghi archive; operator không có quyền xóa object/version, sửa replication hoặc thay đổi/rút ngắn retention.
6. Tạo `aws_config_configuration_recorder` tại `us-east-1` với `recording_strategy.use_only = "INCLUSION_BY_RESOURCE_TYPES"` và chế độ `CONTINUOUS` cho danh sách bên dưới.
7. Tạo `aws_config_delivery_channel` trỏ vào staging bucket với `s3_key_prefix = "aws-config"` và `aws_config_retention_configuration` tối thiểu 30 ngày.
8. Bật S3 Replication metrics cho một replication rule và gửi sự kiện `s3:Replication:OperationFailedReplication` tới kênh cảnh báo hiện có của TF4. Không bật S3 Replication Time Control (RTC) để tránh chi phí không cần thiết.
9. Tạo `aws_config_configuration_recorder_status` với `is_enabled = true` và `depends_on` delivery channel để start recorder hoàn toàn bằng Terraform, không thao tác tay.
10. Kiểm tra recorder/delivery status không có lỗi; xác minh object thử nghiệm replicate thành công vào WORM archive và không có failed replication.

Tham chiếu kỹ thuật: [AWS Config không hỗ trợ delivery channel tới bucket có default Object Lock retention](https://docs.aws.amazon.com/config/latest/developerguide/manage-delivery-channel.html). Với S3 Replication, object nguồn không có retention sẽ nhận default retention của destination bucket: [What does Amazon S3 replicate?](https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication-what-is-isnot-replicated.html).

SSE-S3 là baseline của ticket để tránh KMS permission gap và giữ cost dự đoán được. Nếu platform bắt buộc SSE-KMS, CDO08 phải bổ sung `source_selection_criteria` cho KMS-encrypted objects, `replica_kms_key_id`, quyền KMS tối thiểu cho replication role và cập nhật cost trước khi apply: [Replicating encrypted objects](https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication-config-for-kms-objects.html).

### Resource types cần record

Chỉ record các resource lõi dưới đây để giữ chi phí thấp nhưng vẫn đủ chuỗi bằng chứng cho Directive #4:

```text
AWS::EKS::Cluster
AWS::EKS::Nodegroup
AWS::EKS::Addon
AWS::IAM::Role
AWS::IAM::InstanceProfile
AWS::IAM::Policy
AWS::IAM::OIDCProvider
AWS::EC2::Instance
AWS::EC2::NetworkInterface
AWS::EC2::Volume
AWS::EC2::LaunchTemplate
AWS::EC2::VPC
AWS::EC2::SecurityGroup
AWS::EC2::Subnet
AWS::EC2::RouteTable
AWS::EC2::NetworkAcl
AWS::EC2::NatGateway
AWS::EC2::InternetGateway
AWS::AutoScaling::AutoScalingGroup
AWS::SSM::Document
AWS::SSM::ManagedInstanceInventory
AWS::S3::Bucket
AWS::S3::BucketPolicy
AWS::CloudTrail::Trail
AWS::KMS::Key
AWS::ECR::Repository
AWS::DynamoDB::Table
AWS::Logs::LogGroup
AWS::Config::ConfigurationRecorder
AWS::AccessAnalyzer::Analyzer
AWS::ElasticLoadBalancingV2::LoadBalancer
AWS::ElasticLoadBalancingV2::Listener
AWS::ElasticLoadBalancingV2::TargetGroup
```

Trong đó, `AWS::EC2::Instance` là bắt buộc để Resource Timeline nhận diện đúng bastion target của sự kiện SSM `StartSession`. `AWS::IAM::InstanceProfile` và `AWS::IAM::Role` nối instance với quyền SSM; ENI, Security Group, Subnet và Route Table chứng minh đường mạng của bastion; Volume chứng minh cấu hình ổ đĩa mã hóa. `AWS::SSM::Document` theo dõi thay đổi document/session preference thuộc account; `AWS::SSM::ManagedInstanceInventory` chỉ phát sinh dữ liệu khi SSM Inventory được bật. `AWS::Logs::LogGroup` theo dõi cấu hình retention/KMS của EKS control-plane audit log. Nhóm ELBv2 cùng network resources giúp phát hiện thay đổi ảnh hưởng trạng thái public của storefront. `AWS::S3::BucketPolicy` và `AWS::Config::ConfigurationRecorder` giúp theo dõi thay đổi ngay trên đường lưu evidence.

Không bật `all_supported = true` trong giai đoạn đầu. Các global IAM resource types chỉ được record tại `us-east-1` để tránh duplicate configuration items nếu sau này TF4 bật Config ở Region khác. EKS Access Entry chưa có resource type AWS Config; thay đổi Access Entry phải truy từ CloudTrail và EKS audit log.

### Guardrail bắt buộc

- Không sửa, vô hiệu hóa hoặc thay đổi cấu hình `flagd` trong phạm vi ticket này.
- Không thay đổi trạng thái public của storefront hoặc trạng thái private của Grafana, Jaeger, Argo CD và các cổng vận hành.
- Chỉ thay đổi AWS Config, hai S3 buckets phục vụ Config, replication IAM/policy và quyền audit read-only đã nêu trong ticket.
- Mọi thao tác triển khai và kiểm thử phải dùng SSO principal cá nhân; không dùng shared account hoặc static access key.

### Phụ thuộc để đáp ứng MANDATE-04

Ticket này hoàn thành phần AWS Config của Task 2 và cung cấp evidence đầu vào cho MANDATE-04. Trước khi TF4 kết luận MANDATE-04 `PASS`, các nguồn dùng để correlation cũng phải đạt yêu cầu toàn vẹn:

1. CloudTrail phải bật `enable_log_file_validation = true` để tạo digest kiểm tra log.
2. Bucket CloudTrail phải có Object Lock `COMPLIANCE` tối thiểu 30 ngày và `force_destroy = false`.
3. Staging và WORM archive bucket phải tách quyền ghi của service/replication role khỏi quyền vận hành; operator không có `s3:Delete*`, quyền sửa replication hoặc quyền thay đổi/xóa retention.
4. EKS control-plane audit log phải bật, truy vấn được hành động Kubernetes tương ứng và được archive vào nơi lưu trữ bất biến hoặc có kiểm soát quyền xóa tách khỏi operator; CloudWatch retention đơn thuần không được xem là bằng chứng bất biến.
5. Mọi thao tác kiểm thử phải dùng SSO principal cá nhân, không dùng shared account hoặc static access key.

Terraform hiện tại của CloudTrail còn `force_destroy = true` và chưa khai báo `enable_log_file_validation`; đây là blocker của Directive #4 và phải được sửa trong cùng PR hạ tầng hoặc một ticket/PR liên kết trước nghiệm thu.

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
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadInfrastructureMetadata",
      "Effect": "Allow",
      "Action": [
        "eks:ListClusters",
        "eks:DescribeCluster",
        "eks:ListNodegroups",
        "eks:ListAddons",
        "eks:DescribeNodegroup",
        "eks:DescribeAddon",
        "ec2:DescribeInstances",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DescribeVolumes",
        "ec2:DescribeLaunchTemplates",
        "ec2:DescribeLaunchTemplateVersions",
        "ec2:DescribeVpcs",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeSubnets",
        "ec2:DescribeRouteTables",
        "ec2:DescribeNetworkAcls",
        "ec2:DescribeNatGateways",
        "ec2:DescribeInternetGateways",
        "autoscaling:DescribeAutoScalingGroups",
        "elasticloadbalancing:DescribeLoadBalancers",
        "elasticloadbalancing:DescribeListeners",
        "elasticloadbalancing:DescribeTargetGroups",
        "elasticloadbalancing:DescribeTags",
        "iam:ListRoles",
        "iam:GetRole",
        "iam:ListInstanceProfiles",
        "iam:GetInstanceProfile",
        "iam:ListPolicies",
        "iam:GetPolicy",
        "iam:GetPolicyVersion",
        "iam:ListOpenIDConnectProviders",
        "iam:GetOpenIDConnectProvider",
        "ssm:DescribeInstanceInformation",
        "ssm:ListDocuments",
        "ssm:DescribeDocument",
        "ssm:GetDocument",
        "logs:DescribeLogGroups",
        "access-analyzer:ListAnalyzers",
        "access-analyzer:GetAnalyzer",
        "kms:ListKeys",
        "kms:DescribeKey",
        "ecr:DescribeRepositories",
        "ecr:GetRepositoryPolicy",
        "dynamodb:DescribeTable",
        "cloudtrail:DescribeTrails",
        "cloudtrail:GetTrailStatus",
        "cloudtrail:GetEventSelectors",
        "cloudtrail:LookupEvents",
        "cloudwatch:GetMetricData",
        "cloudwatch:GetMetricStatistics",
        "cloudwatch:ListMetrics"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DiscoverS3Buckets",
      "Effect": "Allow",
      "Action": "s3:ListAllMyBuckets",
      "Resource": "*"
    },
    {
      "Sid": "ReadConfigBucketSettings",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetBucketLocation",
        "s3:GetBucketPolicy",
        "s3:GetBucketVersioning",
        "s3:GetReplicationConfiguration",
        "s3:GetEncryptionConfiguration",
        "s3:GetBucketPublicAccessBlock",
        "s3:GetBucketObjectLockConfiguration",
        "s3:GetLifecycleConfiguration",
        "s3:GetBucketNotification"
      ],
      "Resource": [
        "arn:aws:s3:::<config-staging-bucket>",
        "arn:aws:s3:::<config-worm-archive-bucket>"
      ]
    },
    {
      "Sid": "ReadConfigEvidenceObjects",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:GetObjectVersion",
        "s3:GetObjectAttributes"
      ],
      "Resource": [
        "arn:aws:s3:::<config-staging-bucket>/aws-config/*",
        "arn:aws:s3:::<config-worm-archive-bucket>/aws-config/*"
      ]
    },
    {
      "Sid": "ReadArchiveRetention",
      "Effect": "Allow",
      "Action": [
        "s3:GetObjectRetention",
        "s3:GetObjectLegalHold"
      ],
      "Resource": "arn:aws:s3:::<config-worm-archive-bucket>/aws-config/*"
    }
  ]
}
```

CDO08 thay hai placeholder bucket bằng ARN Terraform output thực tế. Không mở rộng object ARN ra ngoài prefix `aws-config/`.

Không cấp `config:Put*`, `config:Delete*`, `config:Start*`, `config:Stop*`, `s3:Delete*`, `s3:PutReplicationConfiguration` hoặc quyền sửa Object Lock/retention cho CDO07. WORM archive bucket phải dùng Object Lock `COMPLIANCE`; quyền `s3:BypassGovernanceRetention` không được xem là biện pháp bảo vệ vì chỉ có tác dụng với chế độ `GOVERNANCE`.

## 6. Nghiệm thu Task 2 và evidence MANDATE-04

### 6.1. Bài kiểm thử bắt buộc của Task 2

Sau khi deploy, CDO08 dùng DeployOperator SSO cá nhân thêm tag `audit-drill=task-2` vào EC2 bastion đã duyệt. CDO08 cung cấp cửa sổ thời gian và Jira/PR liên quan nhưng không cung cấp trước kết quả CloudTrail.

CDO07 phải độc lập:

1. Tìm bastion theo instance ID trong AWS Config.
2. Lấy Resource Timeline trước/sau thay đổi tag và xác nhận instance vẫn private, đúng SG, subnet, volume và instance profile.
3. Theo quan hệ Config, nối instance profile với IAM role có quyền SSM tại thời điểm sự kiện.
4. Đối chiếu timestamp thay đổi với CloudTrail `CreateTags` và xác định principal, source IP, request parameters.
5. Kiểm tra object history/snapshot tại staging có replication status `COMPLETED`; object tương ứng tại WORM archive có status `REPLICA`, mode `COMPLIANCE` và retain-until-date tối thiểu 30 ngày.
6. Ghi Pass/Fail, nguyên nhân và link evidence vào `AUDIT_CHECKLIST.md`.

### 6.2. Evidence đóng góp cho bài forensic MANDATE-04

Sau khi Task 2 pass, một người dùng SSO cá nhân thực hiện phiên SSM `StartSession` vào đúng bastion. CDO07 lưu mẫu correlation để TF4 đưa vào runbook forensic:

1. Tìm CloudTrail `StartSession` và xác định SSO principal, event time, source IP, document name, session ID.
2. Xác nhận `requestParameters.target` trùng instance ID có Resource Timeline trong AWS Config.
3. Ghép timeline `CreateTags` -> trạng thái Config trước/sau -> `StartSession` mà không dùng thông tin được chuẩn bị sẵn ngoài log/trace.
4. Lưu link evidence và thời gian truy vết; mục tiêu hoàn thành toàn bộ chuỗi correlation trong tối đa 10 phút.

Mốc 10 phút áp dụng cho việc truy vấn AWS Config Resource Timeline và CloudTrail. S3 delivery/replication là bất đồng bộ nên được nghiệm thu riêng bằng replication status và Object Lock metadata, không dùng làm điều kiện chờ trong bài correlation tại chỗ.

CloudTrail log file validation, EKS audit log, IAM/RBAC separation và identity inventory được nghiệm thu trong phạm vi MANDATE-04. Ticket này chỉ ghi nhận chúng là dependency, không coi việc hoàn thành Task 2 đồng nghĩa toàn bộ MANDATE-04 đã `PASS`.

AWS Config không thay thế CloudTrail: Config cung cấp trạng thái và quan hệ resource trước/sau; CloudTrail cung cấp danh tính và API call. Session Manager không ghi nội dung của phiên port forwarding, vì vậy evidence chỉ được kết luận tới hành động mở/đóng session, target bastion và tham số tunnel, không được tuyên bố đã thấy thao tác HTTP bên trong Grafana/Jaeger.

## 7. Definition of Done

### 7.1. Task 2 Done

- [ ] Terraform PR tạo recorder, recorder status, delivery channel, retention, staging bucket, WORM archive bucket, replication và failure notification đã merge/apply thành công.
- [ ] Configuration recorder có `recording=true`.
- [ ] Delivery channel không có delivery error.
- [ ] `totalDiscoveredResources > 0` và có đủ resource lõi trong scope.
- [ ] Resource Timeline của `AWS::EC2::Instance` hiển thị bastion và thay đổi tag thử nghiệm.
- [ ] CDO07 chạy được Resource Timeline/Advanced Query bằng profile Audit mà không gặp `AccessDenied`.
- [ ] CDO07 nối được Config timeline với CloudTrail `CreateTags`, truy ra người, thời gian và nội dung thay đổi.
- [ ] Staging bucket dùng SSE-S3, `BucketOwnerEnforced`, versioning, prefix `aws-config/`, không có default Object Lock retention, `force_destroy = false`; operator không có quyền xóa/sửa replication.
- [ ] Object AWS Config mẫu có replication status `COMPLETED` tại staging và object tương ứng có status `REPLICA` tại WORM archive.
- [ ] WORM archive bucket dùng SSE-S3, `BucketOwnerEnforced`, versioning, Object Lock `COMPLIANCE` tối thiểu 30 ngày, `force_destroy = false`; object mẫu có mode và retain-until-date đúng yêu cầu.
- [ ] Replication metrics và `OperationFailedReplication` notification đã bật; thời điểm nghiệm thu không có object ở trạng thái `FAILED`.
- [ ] Terraform outputs cung cấp staging/archive bucket ARN và evidence prefix để áp dụng audit policy đúng phạm vi.
- [ ] `docs/audit/AUDIT_CHECKLIST.md` được cập nhật Pass/Fail và link evidence.
- [ ] Chi phí sau deploy được theo dõi và không vượt budget guardrail trong [`AWS_CONFIG_COST_ESTIMATE.md`](../AWS_CONFIG_COST_ESTIMATE.md).

### 7.2. Evidence đóng góp cho MANDATE-04

- [ ] Link Terraform PR, cost, Config Resource Timeline và CloudTrail `CreateTags` đã được lưu làm evidence.
- [ ] Có mẫu correlation SSM `StartSession` -> bastion Config timeline.
- [ ] Permission gap và yêu cầu separation of duties đã được ghi nhận.
- [ ] SSO principal/session ID của mẫu forensic map được về danh tính cá nhân.
- [ ] Chuỗi correlation mẫu hoàn thành trong tối đa 10 phút và đã lưu thời gian thực tế.
- [ ] Không có thay đổi tới `flagd` hoặc trạng thái public/private của storefront và cổng vận hành.
- [ ] Task 2 không được dùng để tuyên bố toàn bộ MANDATE-04 `PASS` khi các dependency khác chưa hoàn thành.

## 8. Chi phí dự kiến

Scope mở rộng dùng giả định kế hoạch 150 resource lõi để bao phủ bastion/SSM, EKS audit Log Group, đường public của storefront và đường lưu evidence. Continuous recording, bốn rules tùy chọn, hai bản sao S3, Same-Region Replication và replication metrics được ước tính khoảng `$2.53-$8.23/tháng`, tương đương `$0.58-$1.89/tuần`. Đề nghị phê duyệt guardrail AWS Config tối đa `$10/tháng` (`~$2.30/tuần`). Guardrail này không bao gồm chi phí remediation/archival của CloudTrail và EKS audit log. Công thức và giả định chi tiết nằm tại [`AWS_CONFIG_COST_ESTIMATE.md`](../AWS_CONFIG_COST_ESTIMATE.md).
