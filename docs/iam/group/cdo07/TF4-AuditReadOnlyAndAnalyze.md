# Permission Set: TF4-AuditReadOnlyAndAnalyze

Tài liệu này chi tiết hóa quyền hạn của Permission Set `TF4-AuditReadOnlyAndAnalyze`. Đây là tập hợp quyền chuyên sâu phục vụ cho việc kiểm toán cấu hình, giám sát vết hoạt động (audit trail), xác minh chính sách bảo mật và truy xuất bằng chứng trong dự án TF4.

## 📄 Nội dung Policy (JSON)

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AuditTrailsAndLogsReadOnly",
            "Effect": "Allow",
            "Action": [
                "cloudtrail:LookupEvents",
                "cloudtrail:DescribeTrails",
                "cloudtrail:GetTrail",
                "cloudtrail:GetTrailStatus",
                "cloudtrail:GetEventSelectors",
                "cloudtrail:ListTrails",
                "cloudtrail:ListTags",
                "logs:Describe*",
                "logs:Get*",
                "logs:FilterLogEvents",
                "logs:StartQuery",
                "logs:StopQuery",
                "logs:GetQueryResults"
            ],
            "Resource": "*"
        },
        {
            "Sid": "IdentityAuditAndPolicyGeneration",
            "Effect": "Allow",
            "Action": [
                "iam:Get*",
                "iam:List*",
                "access-analyzer:Get*",
                "access-analyzer:List*",
                "access-analyzer:ValidatePolicy",
                "access-analyzer:StartPolicyGeneration",
                "access-analyzer:GetGeneratedPolicy"
            ],
            "Resource": "*"
        },
        {
            "Sid": "ConfigAuditAndSQLQuery",
            "Effect": "Allow",
            "Action": [
                "config:Describe*",
                "config:Get*",
                "config:List*",
                "config:SelectResourceConfig",
                "config:SelectAggregateResourceConfig"
            ],
            "Resource": "*"
        },
        {
            "Sid": "EvidenceBucketReadOnly",
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::tf4-evidence-log-bucket",
                "arn:aws:s3:::tf4-evidence-log-bucket/*",
                "arn:aws:s3:::tf4-cloudtrail-logs-bucket-*",
                "arn:aws:s3:::tf4-cloudtrail-logs-bucket-*/*"
            ]
        },
        {
            "Sid": "S3MetadataAudit",
            "Effect": "Allow",
            "Action": [
                "s3:GetBucketVersioning",
                "s3:GetBucketObjectLockConfiguration",
                "s3:ListAllMyBuckets",
                "s3:GetBucketLocation",
                "s3:GetEncryptionConfiguration",
                "s3:GetBucketPublicAccessBlock"
            ],
            "Resource": "*"
        },
        {
            "Sid": "OpenSearchAuditReadOnly",
            "Effect": "Allow",
            "Action": [
                "es:ListDomainNames",
                "es:DescribeElasticsearchDomain",
                "es:DescribeDomains"
            ],
            "Resource": "*"
        },
        {
            "Sid": "KMSAuditAndDecrypt",
            "Effect": "Allow",
            "Action": [
                "kms:Decrypt",
                "kms:DescribeKey",
                "kms:GetKeyPolicy",
                "kms:GetKeyRotationStatus"
            ],
            "Resource": "arn:aws:kms:us-east-1:511825856493:key/*"
        },
        {
            "Sid": "ExtendedAuditReadOnly",
            "Effect": "Allow",
            "Action": [
                "budgets:ViewBudget",
                "eks:DescribeCluster",
                "eks:ListNodegroups",
                "eks:DescribeNodegroup",
                "rds:DescribeDBInstances",
                "guardduty:ListDetectors",
                "securityhub:DescribeHub",
                "cloudwatch:GetMetricData",
                "cloudwatch:GetMetricStatistics",
                "cloudwatch:ListMetrics",
                "cloudwatch:DescribeAlarms",
                "elasticloadbalancing:DescribeLoadBalancers",
                "elasticloadbalancing:DescribeTargetGroups",
                "elasticloadbalancing:DescribeTargetHealth",
                "elasticloadbalancing:DescribeListeners",
                "elasticloadbalancing:DescribeRules"
            ],
            "Resource": "*"
        },
        {
            "Sid": "SSMAndEC2AuditReadOnly",
            "Effect": "Allow",
            "Action": [
                "ssm:DescribeSessions",
                "ssm:GetConnectionStatus",
                "ssm:DescribeInstanceInformation",
                "ec2:DescribeInstances"
            ],
            "Resource": "*"
        },
        {
            "Sid": "Mandate04CloudTrailLogBucketAuditRead",
            "Effect": "Allow",
            "Action": [
                "s3:GetBucketPolicyStatus",
                "s3:GetBucketPolicy",
                "s3:GetLifecycleConfiguration",
                "s3:GetBucketLogging"
            ],
            "Resource": [
                "arn:aws:s3:::tf4-cloudtrail-logs-bucket-*",
                "arn:aws:s3:::tf4-cloudtrail-logs-bucket-*/*"
            ]
        },
        {
            "Sid": "Mandate04CloudTrailIntegrityRead",
            "Effect": "Allow",
            "Action": [
                "cloudtrail:ListPublicKeys",
                "cloudtrail:GetInsightSelectors",
                "cloudtrail:ValidateLogs"
            ],
            "Resource": "*"
        },
        {
            "Sid": "Mandate04CloudWatchAlarmRead",
            "Effect": "Allow",
            "Action": [
                "cloudwatch:DescribeAlarms"
            ],
            "Resource": "*"
        },
        {
            "Sid": "Mandate04IdentityStoreUserRead",
            "Effect": "Allow",
            "Action": [
                "identitystore:DescribeUser",
                "identitystore:ListUsers"
            ],
            "Resource": "*"
        },
        {
            "Sid": "ListAWSConfigEvidenceObjects",
            "Effect": "Allow",
            "Action": [
                "s3:ListBucket",
                "s3:ListBucketVersions"
            ],
            "Resource": [
                "arn:aws:s3:::tf4-aws-config-staging-511825856493-us-east-1",
                "arn:aws:s3:::tf4-aws-config-worm-archive-511825856493-us-east-1"
            ],
            "Condition": {
                "StringLike": {
                    "s3:prefix": [
                        "aws-config",
                        "aws-config/",
                        "aws-config/*"
                    ]
                }
            }
        },
        {
            "Sid": "ReadAWSConfigBucketControls",
            "Effect": "Allow",
            "Action": [
                "s3:GetBucketPolicy",
                "s3:GetBucketPolicyStatus",
                "s3:GetBucketOwnershipControls",
                "s3:GetLifecycleConfiguration"
            ],
            "Resource": [
                "arn:aws:s3:::tf4-aws-config-staging-511825856493-us-east-1",
                "arn:aws:s3:::tf4-aws-config-worm-archive-511825856493-us-east-1"
            ]
        },
        {
            "Sid": "ReadAWSConfigReplication",
            "Effect": "Allow",
            "Action": "s3:GetReplicationConfiguration",
            "Resource": "arn:aws:s3:::tf4-aws-config-staging-511825856493-us-east-1"
        },
        {
            "Sid": "ReadAWSConfigEvidenceObjectMetadata",
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:GetObjectVersion",
                "s3:GetObjectAttributes",
                "s3:GetObjectVersionAttributes"
            ],
            "Resource": [
                "arn:aws:s3:::tf4-aws-config-staging-511825856493-us-east-1/aws-config/*",
                "arn:aws:s3:::tf4-aws-config-worm-archive-511825856493-us-east-1/aws-config/*"
            ]
        },
        {
            "Sid": "ReadAWSConfigArchiveRetention",
            "Effect": "Allow",
            "Action": [
                "s3:GetObjectRetention",
                "s3:GetObjectLegalHold"
            ],
            "Resource": "arn:aws:s3:::tf4-aws-config-worm-archive-511825856493-us-east-1/aws-config/*"
        },
        {
            "Sid": "ReadCloudTrailObjectRetention",
            "Effect": "Allow",
            "Action": [
                "s3:GetObjectRetention",
                "s3:GetObjectLegalHold"
            ],
            "Resource": "arn:aws:s3:::tf4-cloudtrail-logs-bucket-511825856493/*"
        },
        {
            "Sid": "ReadCoreInfrastructureForCorrelation",
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeSecurityGroups",
                "ec2:DescribeSubnets",
                "ec2:DescribeVpcs",
                "ec2:DescribeVolumes",
                "ec2:DescribeNetworkInterfaces",
                "ec2:DescribeRouteTables",
                "ec2:DescribeNetworkAcls",
                "ec2:DescribeNatGateways",
                "ec2:DescribeInternetGateways",
                "eks:ListClusters"
            ],
            "Resource": "*",
            "Condition": {
                "StringEquals": {
                    "aws:RequestedRegion": "us-east-1"
                }
            }
        },
        {
            "Sid": "ReadIdentityCenterForAccountability",
            "Effect": "Allow",
            "Action": [
                "sso:ListInstances",
                "identitystore:DescribeUser"
            ],
            "Resource": "*"
        },
        {
            "Sid": "AllowPortForwardingToApprovedBastion",
            "Effect": "Allow",
            "Action": [
                "ssm:StartSession",
                "ssm:GetDocument",
                "ssm:DescribeDocument"
            ],
            "Resource": [
                "arn:aws:ec2:us-east-1:511825856493:instance/i-072084d1cf0b2f1c9",
                "arn:aws:ssm:us-east-1::document/AWS-StartPortForwardingSession"
            ]
        },
        {
            "Sid": "AllowSessionDataChannelForOwnSessions",
            "Effect": "Allow",
            "Action": [
                "ssmmessages:OpenDataChannel"
            ],
            "Resource": [
                "arn:aws:ssm:us-east-1:511825856493:session/${aws:userid}-*"
            ]
        },
        {
            "Sid": "AllowManageOwnSessions",
            "Effect": "Allow",
            "Action": [
                "ssm:ResumeSession",
                "ssm:TerminateSession"
            ],
            "Resource": [
                "arn:aws:ssm:us-east-1:511825856493:session/${aws:userid}-*"
            ]
        }
    ]
}
```

---

## 🔍 Giải thích chi tiết Quyền hạn

Policy này được cấu thành từ 21 Statements phục vụ mục đích kiểm toán toàn diện hệ thống:

### 1. `AuditTrailsAndLogsReadOnly` (Nhật ký Audit & CloudTrail)
* **Hành động**: Các hàm liên quan đến CloudTrail và CloudWatch Logs.
* **Mô tả**: Cho phép kiểm tra trạng thái hoạt động của CloudTrail (`DescribeTrails`, `GetTrailStatus`), xem vết sự kiện thao tác API của tài khoản AWS (`LookupEvents`), và thực hiện truy vấn chuyên sâu log bằng CloudWatch Logs Insights.
* **Mục đích**: Truy tìm nguyên nhân sự cố hoặc hoạt động bất thường từ bất kỳ tài khoản/người dùng nào.

### 2. `IdentityAuditAndPolicyGeneration` (Kiểm toán định danh & Phân tích Policy)
* **Hành động**: IAM read APIs và IAM Access Analyzer.
* **Mô tả**: Quyền xem thông tin cấu hình IAM (người dùng, nhóm, vai trò). Đồng thời cho phép sử dụng AWS Access Analyzer để chạy các công cụ kiểm tra chính sách bảo mật (`ValidatePolicy`), bắt đầu tạo chính sách tối ưu hóa dựa trên lịch sử truy cập thực tế (`StartPolicyGeneration`, `GetGeneratedPolicy`).
* **Mục đích**: Thực thi quy tắc "đặc quyền tối thiểu" bằng cách phát hiện các policy quá rộng và tinh chỉnh chúng.

### 3. `ConfigAuditAndSQLQuery` (Lịch sử cấu hình tài nguyên)
* **Hành động**: AWS Config read/select APIs.
* **Mô tả**: Cho phép truy vấn cơ sở dữ liệu cấu hình tài nguyên của hệ thống qua AWS Config (`SelectResourceConfig`, `SelectAggregateResourceConfig`) sử dụng các câu lệnh SQL nâng cao.
* **Mục đích**: Theo dõi lịch sử thay đổi cấu hình hạ tầng theo thời gian và đánh giá mức độ tuân thủ quy chuẩn bảo mật.

### 4. `EvidenceBucketReadOnly` (Truy xuất bằng chứng lưu trữ)
* **Hành động**: `s3:GetObject`, `s3:ListBucket`
* **Tài nguyên**: S3 bucket `tf4-evidence-log-bucket` và toàn bộ các tệp tin con.
* **Mô tả**: Cho phép liệt kê và tải xuống các tệp tin lưu trữ bằng chứng kiểm toán nằm trong bucket chuyên dụng của dự án.
* **Mục đích**: Trích xuất báo cáo, snapshot cấu hình hoặc log được lưu trữ dài hạn phục vụ đoàn kiểm toán độc lập.

### 5. `S3MetadataAudit` (Kiểm tra an toàn cấu hình S3)
* **Hành động**: `s3:GetBucketVersioning`, `s3:GetBucketObjectLockConfiguration`, `s3:ListAllMyBuckets`, `s3:GetBucketLocation`, `s3:GetEncryptionConfiguration`, `s3:GetBucketPublicAccessBlock`
* **Mô tả**: Xem trạng thái kích hoạt quản lý phiên bản (Versioning) và khóa bảo mật dữ liệu không cho phép xóa/ghi đè (Object Lock) trên toàn bộ S3.
* **Mục đích**: Đảm bảo các bucket lưu trữ quan trọng không bị mất mát dữ liệu hoặc giả mạo.

### 6. `OpenSearchAuditReadOnly` (Đọc cấu hình OpenSearch)
* **Hành động**: `es:ListDomainNames`, `es:DescribeElasticsearchDomain`, `es:DescribeDomains`
* **Mô tả**: Cho phép xem danh sách cấu hình và trạng thái của cụm Amazon OpenSearch / Elasticsearch.
* **Mục đích**: Xác định trạng thái của hệ thống tìm kiếm log tập trung.

### 7. `KMSAuditAndDecrypt` (Giải mã & Kiểm toán Khóa mã hóa)
* **Hành động**: `kms:Decrypt`, `kms:DescribeKey`, `kms:GetKeyPolicy`, `kms:GetKeyRotationStatus`
* **Tài nguyên**: Giới hạn trong các KMS Key thuộc tài khoản `511825856493` tại vùng `us-east-1` (`arn:aws:kms:us-east-1:511825856493:key/*`).
* **Mô tả**: Cho phép kiểm tra chính sách của khóa (Key Policy), trạng thái tự động xoay vòng khóa (Key Rotation). Đặc biệt cho phép hành động `kms:Decrypt` (Giải mã) nhằm cho phép các kiểm toán viên giải mã các tệp tin bằng chứng được mã hóa bằng các KMS Key này.
* **Mục đích**: Cho phép đọc các log hoặc tài liệu nén đã được mã hóa ở mức lưu trữ (Rest Encryption) khi tiến hành audit.

### 8. `ExtendedAuditReadOnly` (Kiểm toán Bổ sung & Giám sát Incident)
* **Hành động**: Đọc EKS NodeGroups, metric CloudWatch, và mô tả ALB/Target Group.
* **Mô tả**: Cho phép kiểm tra cấu hình node group, query metric hiệu năng của ALB/EKS/Application, kiểm tra target health để phục vụ việc truy vết các sự cố (như lỗi checkout/payment) và nghiệm thu độ sẵn sàng của hạ tầng.
* **Mục đích**: Hỗ trợ đắc lực việc kiểm toán các incident phát sinh và nghiệm thu SLO/SLI.

### 9. `SSMAndEC2AuditReadOnly` (Đọc trạng thái SSM và EC2)
* **Hành động**: `ssm:DescribeSessions`, `ssm:GetConnectionStatus`, `ssm:DescribeInstanceInformation`, `ec2:DescribeInstances`
* **Mô tả**: Xem thông tin các phiên SSM Session Manager đang hoạt động và xem danh sách máy chủ EC2 bao gồm Bastion Host.

### 10. `Mandate04CloudTrailLogBucketAuditRead` & `Mandate04CloudTrailIntegrityRead` (Forensic CloudTrail & Log Integrity)
* **Mô tả**: Đọc chi tiết chính sách, lifecycle, log logging của CloudTrail Log Bucket. Cho phép validate CloudTrail logs để xác thực log không bị thay đổi.
* **Mục đích**: Đáp ứng yêu cầu log integrity kiểm toán của Mandate #4.

### 11. `Mandate04CloudWatchAlarmRead` & `Mandate04IdentityStoreUserRead` (Giám sát cảnh báo & Tra cứu danh tính)
* **Mô tả**: Đọc cấu hình các alarm để kiểm chứng độ phủ cảnh báo. Cho phép mô tả và tra cứu User trong AWS Identity Store.
* **Mục đích**: Map danh tính người dùng chịu trách nhiệm thực thi các hoạt động bảo mật.

### 12. `ListAWSConfigEvidenceObjects` (Liệt kê Object bằng chứng AWS Config)
* **Hành động**: `s3:ListBucket`, `s3:ListBucketVersions`
* **Mô tả**: Liệt kê các file/object cấu hình AWS Config trên staging và worm-archive buckets.

### 13. `ReadAWSConfigBucketControls` (Đọc cấu hình Bucket AWS Config)
* **Hành động**: `s3:GetBucketPolicy`, `s3:GetBucketPolicyStatus`, `s3:GetBucketOwnershipControls`, `s3:GetLifecycleConfiguration`
* **Mô tả**: Đọc cấu hình bảo mật và vòng đời (lifecycle) của các bucket AWS Config.

### 14. `ReadAWSConfigReplication` (Đọc cấu hình Replication của AWS Config Staging)
* **Hành động**: `s3:GetReplicationConfiguration`
* **Mô tả**: Xác minh cấu hình đồng bộ dữ liệu (replication) từ staging sang WORM archive.

### 15. `ReadAWSConfigEvidenceObjectMetadata` (Đọc metadata Object của AWS Config)
* **Hành động**: `s3:GetObject`, `s3:GetObjectVersion`, `s3:GetObjectAttributes`, `s3:GetObjectVersionAttributes`
* **Mô tả**: Đọc metadata chi tiết của cấu hình AWS Config để xác minh ReplicationStatus.

### 16. `ReadAWSConfigArchiveRetention` (Đọc cấu hình Retention của AWS Config Archive)
* **Hành động**: `s3:GetObjectRetention`, `s3:GetObjectLegalHold`
* **Mô tả**: Đọc cấu hình lưu trữ immutable (Object Lock Compliance mode) của AWS Config Archive.

### 17. `ReadCloudTrailObjectRetention` (Đọc cấu hình Retention của CloudTrail logs)
* **Hành động**: `s3:GetObjectRetention`, `s3:GetObjectLegalHold`
* **Mô tả**: Đọc thông tin Object Lock và thời gian lưu trữ tối thiểu của log CloudTrail.

### 18. `ReadCoreInfrastructureForCorrelation` (Đọc hạ tầng lõi phục vụ Correlation)
* **Hành động**: Describe Security Groups, Subnets, VPCs, Volumes, Network Interfaces, Route Tables, NACLs, NAT Gateways, Internet Gateways, và List EKS Clusters.
* **Mô tả**: Xem thông tin hạ tầng để đối chiếu mạng, bảo mật và cluster EKS tại vùng `us-east-1`.

### 19. `ReadIdentityCenterForAccountability` (Đọc thông tin định danh & SSO)
* **Hành động**: `sso:ListInstances`, `identitystore:DescribeUser`
* **Mô tả**: Tra cứu các instance SSO và thông tin chi tiết người dùng để đối chiếu danh tính.

### 20. `AllowPortForwardingToApprovedBastion` (Mở SSM Tunnel tới Bastion)
* **Hành động**: `ssm:StartSession`, `ssm:GetDocument`, `ssm:DescribeDocument`
* **Tài nguyên**: Bastion `i-072084d1cf0b2f1c9` và document `AWS-StartPortForwardingSession`.
* **Mô tả**: Cho phép thiết lập tunnel port forwarding về localhost cá nhân để truy cập các portal private (Grafana, Jaeger, OpenSearch).

### 21. `AllowSessionDataChannelForOwnSessions` & `AllowManageOwnSessions` (Quản lý SSM Session cá nhân)
* **Mô tả**: Cho phép thiết lập kênh truyền dữ liệu bảo mật và quản lý (Resume/Terminate) phiên làm việc của cá nhân.

---
[⬅️ Quay lại nhóm CDO07](README.md) | [🏡 Quay lại trang chủ IAM Docs](../../README.md)

