# Audit & Evidence Checklist

Danh sách kiểm toán định kỳ dành riêng cho nhóm CDO07 Auditability.

## 1. IAM & Access Analyzer (Audit)

- [x] Truy xuất Access Analyzer và đối chiếu role có quyền rộng với usage quan sát được.
- [x] Kiểm tra lịch sử truy cập Root account trong 30 ngày qua.
- [ ] Xác minh runtime đầy đủ các quyền Temporary Bootstrap Access đang active.

### 1.1. Kết quả kiểm tra IAM

| Control | Kết quả quan sát | Đánh giá |
| --- | --- | --- |
| Access Analyzer | Analyzer `tf4-iam-analyzer` đang `ACTIVE`, loại `ACCOUNT`, có 16 finding `ACTIVE` về external/federated access | **REVIEW REQUIRED** |
| Role có quyền rộng | `tf4-github-actions-terraform-apply` gắn `IAMFullAccess` và `PowerUserAccess`; CloudTrail quan sát 3.419 API calls thuộc 12 dịch vụ | **FAIL - chưa least privilege** |
| Phân tích quyền không dùng | Profile Audit bị từ chối `iam:GenerateServiceLastAccessedDetails`; analyzer loại `ACCOUNT` không tự đánh giá unused access | **PARTIAL** |
| Root account trong 30 ngày | Xác nhận `userIdentity.type=Root`; ít nhất 1.074 event tại 5 Region có log, gồm `CreateSecret` và `UpdatePassword` | **FAIL - CRITICAL** |
| Root security posture | `AccountMFAEnabled=1`, nhưng `AccountAccessKeysPresent=1` và root access key đã xuất hiện trong CLI events | **FAIL - CRITICAL** |
| Temporary Bootstrap Access | Terraform khai báo 5 principal cluster-admin; CloudTrail còn cho thấy `cdo04-an` được cấp cluster-admin ngày 14/07 mà chưa thấy event gỡ/xóa | **FAIL / BLOCKED DIRECT CHECK** |

### 1.2. Quyền EKS admin/Bootstrap đang được khai báo

| Principal | Quyền khai báo | Phân loại |
| --- | --- | --- |
| `tf4-github-actions-eks-deploy` | `AmazonEKSClusterAdminPolicy`, cluster scope | Temporary bootstrap đã ghi trong ADR-003 |
| `tf4-github-actions-terraform-apply` | `AmazonEKSClusterAdminPolicy`, cluster scope | CI admin, cần owner xác nhận thời hạn |
| `TF4-Admin-BreakGlass` | `AmazonEKSClusterAdminPolicy`, cluster scope | Break-glass admin |
| `TF4-DeployOperator` | `AmazonEKSClusterAdminPolicy`, cluster scope | Operator admin |
| `TF4-SecurityIAMSSOManager` | `AmazonEKSClusterAdminPolicy`, cluster scope | Security/IAM admin |
| `cdo04-an` | Association cluster-admin thành công ngày 14/07/2026 | Không nằm trong Terraform, chưa thấy event gỡ/xóa |

CloudTrail có event `ListAssociatedAccessPolicies` thành công cho 5 principal Terraform vào ngày 15/07. Root account và `cdo04-vinh` từng có EKS cluster-admin nhưng đã có event disassociate/delete; riêng `cdo04-an` chưa thấy event cleanup sau lần cấp quyền gần nhất.

Không đánh dấu hoàn thành control Bootstrap cho đến khi profile Audit đọc được `eks:ListAccessEntries`, `eks:DescribeAccessEntry` và `eks:ListAssociatedAccessPolicies`. CloudTrail reconstruction là evidence gián tiếp và không thay thế runtime inventory độc lập.

### 1.3. Kết luận IAM

IAM control **FAIL** và cần remediation. Root account đã được dùng trong kỳ kiểm tra, root access key vẫn tồn tại, đồng thời CI Terraform role đang có quyền AWS rất rộng. Cần ưu tiên vô hiệu hóa/xoay vòng root access key theo quy trình break-glass, điều tra owner của các Root events và downscope các CI/EKS admin roles.

Evidence: [`004-iam-cloudtrail-controls-audit.md`](../evidence/epic-06-audit/004-iam-cloudtrail-controls-audit.md) và [`004-iam-cloudtrail-controls-runtime-evidence.json`](../evidence/epic-06-audit/004-iam-cloudtrail-controls-runtime-evidence.json).

## 2. CloudTrail & Immutability

- [x] CloudTrail có đang hoạt động ở tất cả các Region trong phạm vi TF4 không? **PASS**
- [x] Bucket S3 lưu trữ CloudTrail có bật Versioning không? **PASS**
- [x] Quyền truy cập bucket CloudTrail có được giới hạn theo vai trò và nguyên tắc least privilege không? **FAIL**

### 2.1. Kết quả kiểm tra CloudTrail

| Control | Kết quả quan sát | Đánh giá |
| --- | --- | --- |
| Trail status | `tf4-general-cloudtrail`, `IsLogging=true`, không có lỗi giao S3/CloudWatch gần nhất | **PASS** |
| Region coverage | `IsMultiRegionTrail=true`, `IncludeGlobalServiceEvents=true` | **PASS** |
| Log integrity | `LogFileValidationEnabled=true`, mã hóa bằng KMS CMK | **PASS** |
| Event coverage | Ghi toàn bộ management events; chưa cấu hình data event selector | **PASS trong phạm vi management plane** |
| S3 Versioning | Bucket `tf4-cloudtrail-logs-bucket-511825856493` có `Status=Enabled` | **PASS** |
| S3 immutability | Object Lock `COMPLIANCE` 90 ngày, Public Access Block bật đủ 4 control, policy không public | **PASS** |
| CloudTrail service grant | Chỉ cho `cloudtrail.amazonaws.com` dùng `GetBucketAcl` và `PutObject` đúng account prefix, có `AWS:SourceArn` | **PASS** |
| Quyền operator | `tf4-github-actions-terraform-apply` có `PowerUserAccess` và được ngoại lệ khỏi `DenyNonAdminDeleteObject` | **FAIL - chưa least privilege** |

Object Lock `COMPLIANCE` ngăn xóa các object version trong 90 ngày kể cả khi principal có quyền S3. Tuy nhiên, kiểm soát retention không thay thế yêu cầu least privilege; Terraform apply role vẫn cần được loại bỏ ngoại lệ delete hoặc scope policy vào đúng tài nguyên cần quản lý.

Evidence chi tiết: [`004-iam-cloudtrail-controls-audit.md`](../evidence/epic-06-audit/004-iam-cloudtrail-controls-audit.md).

## 3. AWS Config & Change Trace - Task 2

### 3.1. Thông tin kiểm tra

| Thuộc tính | Giá trị |
| --- | --- |
| Task | Task 2 - Soát xét thay đổi cấu hình hạ tầng qua AWS Config |
| Account / Region | `511825856493` / `us-east-1` |
| Profile kiểm toán | `cdo07-tf4-auditreadonly` |
| Permission Set | `TF4-AuditReadOnlyAndAnalyze` |
| Thời điểm kiểm tra | 15/07/2026, múi giờ `Asia/Saigon` |
| Recorder | `tf4-aws-config-recorder` |
| Delivery channel | `tf4-aws-config-delivery` |
| Kết quả Task 2 | **PASS** |
| Trạng thái tài liệu | **Ready for Review** |
| Evidence report | [`002-aws-config-change-trace-task-2.md`](../evidence/epic-06-audit/002-aws-config-change-trace-task-2.md) |
| Runtime evidence | [`002-aws-config-task-2-runtime-evidence.json`](../evidence/epic-06-audit/002-aws-config-task-2-runtime-evidence.json) |

Phạm vi kết luận trong mục này chỉ áp dụng cho Definition of Done của Task 2 trong [`JIRA_TASKS.md`](JIRA_TASKS.md): truy cập Resource Timeline, đối chiếu hạ tầng lõi với checklist và ghi nhận Pass/Fail. Tag drill, CloudTrail identity correlation, S3 WORM evidence, cost validation và forensic drill thuộc các bước nghiệm thu mở rộng của [`AUDIT-009`](tickets/AUDIT-009-enable-aws-config-change-trail.md) hoặc MANDATE-04, không phải điều kiện để kết luận Task 2 tại thời điểm này.

### 3.2. Kết quả đối chiếu

| # | Hạng mục kiểm tra | Tiêu chí đạt | Kết quả quan sát | Đánh giá | Evidence |
| ---: | --- | --- | --- | --- | --- |
| 1 | Configuration recorder | Recorder tồn tại, đang ghi liên tục và không có lỗi gần nhất | `recording=true`, `lastStatus=SUCCESS`, `lastErrorCode=None`, chế độ `CONTINUOUS` | **PASS** | `E-T2-01`, `E-T2-02` |
| 2 | Delivery channel | Kênh phân phối tồn tại và không có lỗi history/snapshot | History và snapshot đều có `lastStatus=SUCCESS`, không có error code | **PASS** | `E-T2-01` |
| 3 | Phạm vi ghi nhận | Recorder dùng danh sách resource cụ thể và bao phủ VPC, IAM, EKS | `INCLUSION_BY_RESOURCE_TYPES`, `allSupported=false`, gồm 32 resource types | **PASS** | `E-T2-01`, `E-T2-02` |
| 4 | Resource inventory lõi | AWS Config đã discover resource VPC, IAM và EKS trong account | 1 VPC, 42 IAM roles, 1 EKS cluster, 1 node group, 5 add-ons và 4 EC2 instances | **PASS** | `E-T2-01` |
| 5 | Resource Timeline | Profile Audit mở được lịch sử của resource lõi mà không gặp `AccessDenied` | Bastion `i-072084d1cf0b2f1c9` có 6 Configuration Items, từ `ResourceDiscovered` đến các trạng thái `OK` | **PASS** | `E-T2-01` |
| 6 | Thay đổi được ghi nhận | Timeline thể hiện rõ trạng thái trước/sau và thời điểm ghi nhận | Sự kiện ngày 15/07/2026 thể hiện EC2 chuyển từ `stopping` sang `running`; Config ghi nhận lúc `10:48:43` giờ Việt Nam | **PASS** | `E-T2-01` |
| 7 | Trạng thái an toàn của bastion | Bastion vẫn private và giữ đúng quan hệ hạ tầng lõi | `PublicIp=null`, private IP `10.0.10.55`, VPC `vpc-0a4e2abe9fbb70451`, subnet `subnet-0280b36e2249f33d8`, SG `sg-024a16eb3e916f47a`, volume `vol-0169fd931357644bf` | **PASS** | `E-T2-01` |
| 8 | IAM/SSM relationship | Bastion tiếp tục gắn instance profile được quản lý | Instance profile: `tf4-portal-bastion-instance-profile` | **PASS** | `E-T2-01` |
| 9 | ADR/change mapping | Thay đổi kiến trúc phải có ADR; thay đổi vận hành không làm đổi kiến trúc được ghi `N/A` và nêu lý do | Mẫu được review là state transition của EC2; không phát hiện thay đổi VPC, subnet, SG, volume hoặc instance profile nên không yêu cầu ADR | **PASS (N/A ADR)** | `E-T2-01`, `E-T2-04` |

### 3.3. Resource inventory đã xác minh

| Resource type | Số lượng AWS Config đã discover |
| --- | ---: |
| `AWS::EC2::VPC` | 1 |
| `AWS::IAM::Role` | 42 |
| `AWS::EKS::Cluster` | 1 |
| `AWS::EKS::Nodegroup` | 1 |
| `AWS::EKS::Addon` | 5 |
| `AWS::EC2::Instance` | 4 |
| **Tổng các loại được đối chiếu trong Task 2** | **54** |

### 3.4. Resource Timeline mẫu

| Thuộc tính | Giá trị |
| --- | --- |
| Resource type | `AWS::EC2::Instance` |
| Resource ID | `i-072084d1cf0b2f1c9` |
| Trạng thái hiện tại | `running` |
| Số Configuration Items đọc được | 6 |
| Configuration Item đầu tiên | `ResourceDiscovered` lúc 15/07/2026 00:16:49 |
| Configuration change được review | `stopping` -> `running` |
| Thời điểm Config ghi trạng thái mới | 15/07/2026 10:48:43 |
| Thay đổi kiến trúc phát hiện trong mẫu | Không |

### 3.5. Kết luận Task 2

- [x] Truy cập AWS Config và kiểm tra Resource Timeline của hạ tầng lõi.
- [x] Xác nhận recorder bao phủ VPC, IAM, EKS và EC2 trong phạm vi được cấu hình.
- [x] So sánh trạng thái hiện tại với yêu cầu an toàn của checklist.
- [x] Đánh giá Pass/Fail và ghi chú nguyên nhân.
- [x] Ghi nhận quy tắc map ADR: chỉ yêu cầu ADR khi thay đổi ảnh hưởng kiến trúc; state transition mẫu là thay đổi vận hành nên được đánh giá `N/A ADR`.

**Kết luận:** Task 2 **PASS**. AWS Config đang ghi nhận hạ tầng lõi bằng chế độ continuous, Resource Timeline truy cập được bằng profile Audit, và mẫu thay đổi được review không làm bastion mất trạng thái private hoặc thay đổi các quan hệ VPC, subnet, security group, volume và instance profile.

Evidence chi tiết và dữ liệu runtime được lưu tại [`002-aws-config-change-trace-task-2.md`](../evidence/epic-06-audit/002-aws-config-change-trace-task-2.md). Kết luận đang ở trạng thái **Ready for Review** cho đến khi reviewer xác nhận trên Jira hoặc Pull Request.

### 3.6. Lệnh tái kiểm tra

```powershell
aws configservice describe-configuration-recorder-status `
  --region us-east-1 `
  --profile cdo07-tf4-auditreadonly

aws configservice get-discovered-resource-counts `
  --resource-types AWS::EC2::Instance AWS::EC2::VPC AWS::IAM::Role AWS::EKS::Cluster AWS::EKS::Nodegroup AWS::EKS::Addon `
  --region us-east-1 `
  --profile cdo07-tf4-auditreadonly

aws configservice get-resource-config-history `
  --resource-type AWS::EC2::Instance `
  --resource-id i-072084d1cf0b2f1c9 `
  --chronological-order Reverse `
  --limit 10 `
  --region us-east-1 `
  --profile cdo07-tf4-auditreadonly
```

## 4. Control Plane Audit (EKS)

- [x] Kiểm tra một hành động `kubectl` có được ghi vết trong CloudWatch EKS Audit Logs hay không.

### 4.1. Kết quả kiểm tra

| Thuộc tính | Giá trị |
| --- | --- |
| Cluster | `techx-tf4-cluster` |
| Kubernetes context | `techx-tf4-cdo07` |
| CloudWatch log group | `/aws/eks/techx-tf4-cluster/cluster` |
| Control plane logs đang bật | `api`, `audit`, `authenticator` |
| Hành động kiểm tra | `kubectl get namespace default -o json --request-timeout=30s` |
| Thời điểm audit nhận request | `2026-07-15T10:16:04.940063Z` |
| Identity | `huan.huynh` qua Permission Set `TF4-AuditReadOnlyAndAnalyze` |
| Verb / Resource | `get` / `namespaces/default` |
| Source IP | `14.236.16.56` |
| User agent | `kubectl.exe/v1.34.1 (windows/amd64)` |
| Kết quả API / RBAC | HTTP `200` / `allow` |
| Audit stage | `ResponseComplete` |
| Audit ID | `3dc75ebd-d27c-477b-9a30-007db785c867` |
| Mẫu kiểm tra | `1/1` hành động có audit event khớp |
| Đánh giá | **PASS** |
| Evidence report | [`003-eks-control-plane-audit.md`](../evidence/epic-06-audit/003-eks-control-plane-audit.md) |
| Runtime evidence | [`003-eks-control-plane-audit-runtime-evidence.json`](../evidence/epic-06-audit/003-eks-control-plane-audit-runtime-evidence.json) |

### 4.2. Kết luận

Hành động read-only được thực hiện bằng danh tính SSO cá nhân đã xuất hiện trong EKS Audit Logs với đủ thông tin `who`, `what`, `when`, IP nguồn, kết quả API và quyết định phân quyền. Control này **PASS** tại thời điểm kiểm tra.

Kết quả `1/1` xác nhận khả năng truy vết của mẫu đã kiểm tra, không phải cam kết thống kê rằng mọi request luôn được giao tức thời. CloudWatch Logs có cơ chế giao log bất đồng bộ. Control này cũng chưa chứng minh tính chống sửa/xóa hoặc separation of duties; các yêu cầu đó phải được nghiệm thu riêng trong MANDATE-04.
