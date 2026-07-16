# [AUDIT-013] Yêu cầu quyền đọc evidence cho Task 2 và MANDATE-04

**Trạng thái**: TO DO  
**Ngày xác minh runtime**: 15/07/2026  
**Deadline**: 16/07/2026  
**Reporter**: Bá Huân - CDO07 Auditability  
**Assignee**: CDO08 - Security/SSO/IAM  
**Priority**: P0 - blocker nghiệm thu Task 2 và bài forensic MANDATE-04  
**Account/Region**: `511825856493` / `us-east-1`  
**Permission Set**: `TF4-AuditReadOnlyAndAnalyze`  
**Profile nghiệm thu**: `cdo07-tf4-auditreadonly`

## 1. Mục đích

Bổ sung đúng các quyền read-only còn thiếu để CDO07:

1. Hoàn thành Task 2: kiểm tra AWS Config Resource Timeline, đối chiếu hạ tầng hiện tại, xác minh replication sang WORM archive và ghi Pass/Fail vào [`AUDIT_CHECKLIST.md`](../AUDIT_CHECKLIST.md).
2. Hoàn thành phần evidence của [`MANDATE-04`](../../requirements/mandates/MANDATE-04-auditability-tf4.md): dựng lại timeline ai-làm-gì-khi-nào, chứng minh object audit log có retention bất biến và map sự kiện về danh tính cá nhân.
3. Cung cấp số liệu kỹ thuật để CDO04 đối chiếu billed cost trong [`AWS_CONFIG_COST_ESTIMATE.md`](../AWS_CONFIG_COST_ESTIMATE.md).

Ticket này là **permission delta cuối cùng** dựa trên kiểm tra runtime ngày 15/07/2026. Không yêu cầu cấp lại các quyền đã hoạt động và không yêu cầu quyền thay đổi/xóa hạ tầng.

## 2. Hiện trạng đã xác minh

### 2.1. Quyền đã hoạt động, không cần bổ sung

- AWS Config: `config:Describe*`, `config:Get*`, `config:List*`, `config:SelectResourceConfig`.
- CloudTrail: xem trail/status/event selectors, `LookupEvents`, `ListPublicKeys`, `GetInsightSelectors`.
- CloudWatch Logs: tìm và đọc EKS control-plane audit log; `FilterLogEvents` hoạt động.
- CloudWatch: đọc metric AWS Config và `DescribeAlarms`.
- EKS: `eks:DescribeCluster`, `eks:ListNodegroups`; audit logging `api`, `audit`, `authenticator` đã được xác minh là enabled.
- EC2: `ec2:DescribeInstances`.
- SSM: `DescribeSessions`, `GetConnectionStatus`, `DescribeInstanceInformation`.
- CloudTrail S3 bucket: list/read object, đọc bucket policy, versioning, encryption, public access block và Object Lock configuration.
- AWS Config S3 buckets: đọc versioning, encryption, public access block và Object Lock configuration.

### 2.2. API đang bị `AccessDenied`

```text
s3:ListBucket                         # AWS Config staging
s3:GetBucketPolicy                   # AWS Config staging
s3:GetReplicationConfiguration       # AWS Config staging
s3:GetLifecycleConfiguration         # AWS Config staging
s3:GetBucketOwnershipControls        # AWS Config staging
s3:GetObjectRetention                # CloudTrail object
ec2:DescribeSecurityGroups
eks:ListClusters
sso:ListInstances
```

Do không có `s3:ListBucket` trên AWS Config buckets, CDO07 chưa lấy được object key để xác minh `ReplicationStatus=COMPLETED/REPLICA` và retention của object archive.

## 3. Yêu cầu CDO08 triển khai

CDO08 cập nhật Permission Set `TF4-AuditReadOnlyAndAnalyze` bằng Terraform với policy delta dưới đây.

```json
{
  "Version": "2012-10-17",
  "Statement": [
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
    }
  ]
}
```

## 4. Ranh giới least privilege

Không cấp cho CDO07 các quyền sau:

```text
config:Put*
config:Delete*
config:Start*
config:Stop*
s3:Put*
s3:Delete*
s3:BypassGovernanceRetention
cloudtrail:StartLogging
cloudtrail:StopLogging
cloudtrail:UpdateTrail
iam:Create*
iam:Update*
iam:Delete*
eks:Update*
ec2:Modify*
```

Các quyền S3 chỉ áp dụng cho đúng ba evidence buckets và prefix AWS Config. Không mở quyền đọc object cho bucket ứng dụng khác.

Không cấp `identitystore:ListUsers`; CDO07 chỉ được `DescribeUser` đối với user ID xuất hiện trong event cần điều tra. `sso:ListInstances` chỉ dùng để lấy Identity Store ID.

Không cấp `ce:GetCostAndUsage` trong ticket này vì quyền đó cho phép đọc cost ở phạm vi account/billing view và không ép được caller chỉ truy vấn dịch vụ AWS Config. CDO04 cung cấp Cost Explorer output đã lọc `SERVICE = AWS Config`, có timestamp và người xác nhận.

CDO08 cấu hình Permission Set cho danh tính SSO cá nhân, yêu cầu MFA, session duration tối đa 1 giờ và review gỡ policy delta sau khi Task 2/MANDATE-04 nghiệm thu xong. Không dùng shared account hoặc static access key.

`cloudtrail:ValidateLogs` **không phải IAM action hợp lệ** và không được thêm vào policy. Lệnh CLI `aws cloudtrail validate-logs` sử dụng `cloudtrail:ListPublicKeys` cùng `s3:ListBucket`, `s3:GetObject`, `s3:GetBucketLocation`; các quyền này trên CloudTrail bucket hiện đã hoạt động.

Ticket này không yêu cầu Config Rules, Conformance Pack, quyền remediation hay quyền sửa `flagd`.

### 4.1. Review permission hiện hữu ngoài phạm vi delta

Để Permission Set thực sự phù hợp vai trò Audit, CDO08 cần review riêng các quyền hiện có sau; không mở rộng chúng trong PR của AUDIT-013:

- `kms:Decrypt` hiện đang scope toàn bộ `arn:aws:kms:us-east-1:511825856493:key/*`; nên giới hạn vào KMS key của evidence/CloudTrail.
- `access-analyzer:StartPolicyGeneration` là action tạo tác vụ; chỉ giữ nếu CDO07 còn ownership policy generation.
- `ssm:StartSession`, `ResumeSession`, `TerminateSession` là ngoại lệ có chủ đích cho private portal; phải tiếp tục giới hạn vào bastion, approved document và session của chính người dùng.

## 5. Lệnh nghiệm thu sau khi apply

CDO07 đăng nhập lại SSO để nhận policy mới:

```powershell
aws sso login --profile cdo07-tf4-auditreadonly
aws sts get-caller-identity --profile cdo07-tf4-auditreadonly
```

### 5.1. AWS Config S3 evidence

```powershell
aws s3api get-bucket-replication `
  --bucket tf4-aws-config-staging-511825856493-us-east-1 `
  --profile cdo07-tf4-auditreadonly

aws s3api list-objects-v2 `
  --bucket tf4-aws-config-staging-511825856493-us-east-1 `
  --prefix aws-config/ `
  --max-items 10 `
  --profile cdo07-tf4-auditreadonly
```

Với `<object-key>` lấy từ lệnh trên:

```powershell
aws s3api head-object `
  --bucket tf4-aws-config-staging-511825856493-us-east-1 `
  --key "<object-key>" `
  --profile cdo07-tf4-auditreadonly

aws s3api head-object `
  --bucket tf4-aws-config-worm-archive-511825856493-us-east-1 `
  --key "<object-key>" `
  --profile cdo07-tf4-auditreadonly

aws s3api get-object-retention `
  --bucket tf4-aws-config-worm-archive-511825856493-us-east-1 `
  --key "<object-key>" `
  --profile cdo07-tf4-auditreadonly
```

Kết quả yêu cầu:

- Staging object: `ReplicationStatus=COMPLETED`.
- Archive object: `ReplicationStatus=REPLICA`.
- Archive retention: `Mode=COMPLIANCE`, retain-until-date tối thiểu 30 ngày từ thời điểm tạo object.

### 5.2. Đối chiếu hạ tầng

```powershell
aws ec2 describe-security-groups `
  --group-ids sg-024a16eb3e916f47a `
  --region us-east-1 `
  --profile cdo07-tf4-auditreadonly

aws eks list-clusters `
  --region us-east-1 `
  --profile cdo07-tf4-auditreadonly
```

### 5.3. CloudTrail log integrity

```powershell
aws s3api get-object-retention `
  --bucket tf4-cloudtrail-logs-bucket-511825856493 `
  --key "<cloudtrail-object-key>" `
  --profile cdo07-tf4-auditreadonly

aws cloudtrail validate-logs `
  --trail-arn arn:aws:cloudtrail:us-east-1:511825856493:trail/tf4-general-cloudtrail `
  --start-time 2026-07-15T00:00:00Z `
  --end-time 2026-07-15T01:00:00Z `
  --profile cdo07-tf4-auditreadonly
```

### 5.4. Identity mapping

```powershell
$identityStoreId = aws sso-admin list-instances `
  --region us-east-1 `
  --profile cdo07-tf4-auditreadonly `
  --query "Instances[0].IdentityStoreId" `
  --output text

aws identitystore describe-user `
  --identity-store-id $identityStoreId `
  --user-id "<user-id-from-cloudtrail-onBehalfOf>" `
  --region us-east-1 `
  --profile cdo07-tf4-auditreadonly
```

### 5.5. Cost evidence từ CDO04

CDO04 cung cấp Cost Explorer output đã lọc `SERVICE = AWS Config` cho cửa sổ sau deploy. CDO07 đối chiếu số billed cost đó với `ConfigurationItemsRecorded`, resource count và forecast trong `AWS_CONFIG_COST_ESTIMATE.md`; CDO07 không cần quyền đọc toàn bộ billing account.

## 6. Acceptance Criteria / Definition of Done

- [ ] CDO08 cập nhật Permission Set bằng Terraform và cung cấp link PR/apply evidence.
- [ ] CDO07 đăng nhập lại SSO và toàn bộ lệnh mục 5.1-5.4 chạy không còn `AccessDenied`.
- [ ] CDO07 đọc được replication configuration và object metadata của hai AWS Config buckets.
- [ ] Một object AWS Config thật có trạng thái `COMPLETED` tại staging và `REPLICA` tại archive.
- [ ] Object archive có retention `COMPLIANCE` tối thiểu 30 ngày.
- [ ] Một CloudTrail object thật đọc được retention metadata và chạy được `validate-logs`.
- [ ] CDO07 đối chiếu được bastion với SG, subnet, VPC, volume và network interface hiện tại.
- [ ] CDO07 map được CloudTrail/SSO event về danh tính cá nhân bằng Identity Store.
- [ ] CDO04 cung cấp AWS Config billed usage/cost đã lọc, có thời điểm và người xác nhận; CDO07 đối chiếu với metric CI và cost estimate.
- [ ] Policy delta của AUDIT-013 không bổ sung quyền ghi, xóa, remediation hoặc bypass retention cho CDO07.
- [ ] Task 2 có đủ evidence để cập nhật Pass/Fail trong `AUDIT_CHECKLIST.md`.
- [ ] CDO07 có đủ quyền đọc để chạy forensic drill và chứng minh log integrity cho MANDATE-04.

## 7. Ownership

- **CDO08**: cập nhật SSO Permission Set/IAM policy bằng Terraform và apply.
- **CDO07**: chạy nghiệm thu read-only, lưu evidence, cập nhật checklist và forensic runbook.
- **CDO04**: cung cấp Cost Explorer evidence đã lọc riêng chi phí AWS Config cho CDO07.
