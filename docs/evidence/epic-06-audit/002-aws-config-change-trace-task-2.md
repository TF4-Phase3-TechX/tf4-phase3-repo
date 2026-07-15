# Evidence Task 2: Soát xét thay đổi cấu hình hạ tầng qua AWS Config

## 1. Kiểm soát tài liệu

| Thuộc tính | Giá trị |
| --- | --- |
| Evidence ID | `TF4-CDO07-TASK2-20260715` |
| Trạng thái | **PASS - Ready for Review** |
| Người thực hiện | Bá Huân - CDO07 Auditability |
| Thời điểm thu thập | 15/07/2026 17:06, múi giờ `Asia/Saigon` |
| Account / Region | `511825856493` / `us-east-1` |
| Permission Set | `TF4-AuditReadOnlyAndAnalyze` |
| Profile | `cdo07-tf4-auditreadonly` |
| Checklist | [`AUDIT_CHECKLIST.md`](../../audit/AUDIT_CHECKLIST.md) |

## 2. Mục tiêu

Xác minh AWS Config đang ghi nhận hạ tầng lõi của TF4, profile Audit đọc được Resource Timeline, và một thay đổi cấu hình mẫu có đủ trạng thái trước/sau để đối chiếu với yêu cầu an toàn trong checklist.

## 3. Phạm vi

Evidence này bao gồm:

- Trạng thái configuration recorder và delivery channel.
- Recording strategy, recording frequency và danh sách resource types.
- Resource inventory đại diện cho VPC, IAM, EKS và EC2.
- Resource Timeline của EC2 bastion `i-072084d1cf0b2f1c9`.
- Đối chiếu các thuộc tính private network, security group, volume và instance profile.

Evidence này không kết luận về tag drill, CloudTrail identity correlation, S3 WORM, chi phí AWS Config, EKS audit log hoặc toàn bộ MANDATE-04. Các nội dung đó thuộc nghiệm thu mở rộng và không nằm trong Definition of Done gốc của Task 2.

## 4. Phương pháp

1. Đăng nhập bằng SSO principal cá nhân và xác nhận caller identity.
2. Dùng AWS CLI read-only để lấy recorder status, delivery status và recorder configuration.
3. Đếm các resource lõi đã được AWS Config discover.
4. Đọc trạng thái hiện tại và Configuration Items của bastion.
5. So sánh các Configuration Items tại thời điểm `stopping` và `running`.
6. Ghi kết quả vào JSON snapshot và đối chiếu với [`AUDIT_CHECKLIST.md`](../../audit/AUDIT_CHECKLIST.md).

Không có API ghi, xóa hoặc remediation nào được gọi trong quá trình thu thập.

## 5. Evidence index

| Evidence | Nội dung | Link |
| --- | --- | --- |
| `E-T2-01` | Runtime snapshot từ AWS CLI read-only | [`002-aws-config-task-2-runtime-evidence.json`](002-aws-config-task-2-runtime-evidence.json) |
| `E-T2-02` | Terraform recorder/delivery/retention | [`aws-config.tf`](../../../infra/terraform/aws-config.tf) |
| `E-T2-03` | Ticket triển khai AWS Config | [`AUDIT-009`](../../audit/tickets/AUDIT-009-enable-aws-config-change-trail.md) |
| `E-T2-04` | Checklist và kết luận Pass/Fail | [`AUDIT_CHECKLIST.md`](../../audit/AUDIT_CHECKLIST.md) |
| `E-T2-05` | Ticket quyền đọc evidence | [`AUDIT-013`](../../audit/tickets/AUDIT-013-request-task2-mandate04-evidence-read-permissions.md) |

## 6. Kết quả kiểm tra

| Control | Kết quả quan sát | Đánh giá | Evidence |
| --- | --- | --- | --- |
| Recorder hoạt động | `tf4-aws-config-recorder`, `recording=true`, `lastStatus=SUCCESS`, không có error code | **PASS** | `E-T2-01` |
| Delivery hoạt động | Snapshot và history delivery đều `SUCCESS`, không có error code | **PASS** | `E-T2-01` |
| Scope được giới hạn | `INCLUSION_BY_RESOURCE_TYPES`, `allSupported=false`, 32 resource types | **PASS** | `E-T2-01`, `E-T2-02` |
| Hạ tầng lõi được discover | 1 VPC, 42 IAM roles, 1 EKS cluster, 1 node group, 5 add-ons và 4 EC2 instances | **PASS** | `E-T2-01` |
| Timeline truy cập được | Bastion có 6 Configuration Items, gồm `ResourceDiscovered` và các trạng thái `OK` | **PASS** | `E-T2-01` |
| Bastion vẫn private | `publicIp=null`, private IP `10.0.10.55` | **PASS** | `E-T2-01` |
| Quan hệ hạ tầng ổn định | VPC, subnet, SG, volume và instance profile không đổi trong mẫu được review | **PASS** | `E-T2-01` |
| ADR mapping | Mẫu chỉ là state transition, không làm thay đổi kiến trúc | **PASS (N/A ADR)** | `E-T2-01`, `E-T2-04` |

## 7. Configuration change được review

| Thuộc tính | Trước | Sau |
| --- | --- | --- |
| Capture time | 15/07/2026 10:46:30 | 15/07/2026 10:48:43 |
| EC2 state | `stopping` | `running` |
| Public IP | `null` | `null` |
| VPC | `vpc-0a4e2abe9fbb70451` | Không đổi |
| Subnet | `subnet-0280b36e2249f33d8` | Không đổi |
| Security group | `sg-024a16eb3e916f47a` | Không đổi |
| Volume | `vol-0169fd931357644bf` | Không đổi |
| Instance profile | `tf4-portal-bastion-instance-profile` | Không đổi |

Kết quả cho thấy AWS Config ghi nhận được state transition và các quan hệ hạ tầng cần thiết. Không phát hiện thay đổi làm bastion có public IP hoặc làm thay đổi VPC, subnet, security group, volume hay instance profile.

## 8. Kết luận

Task 2 **PASS** trong phạm vi Definition of Done gốc:

- Truy cập được AWS Config Resource Timeline bằng profile Audit.
- AWS Config bao phủ các resource lõi VPC, IAM, EKS và EC2.
- Có Configuration Items thể hiện trạng thái trước/sau của resource mẫu.
- Hiện trạng đã được đối chiếu với checklist và không phát hiện drift làm suy giảm yêu cầu private access của bastion.
- Thay đổi được review là vận hành, không phải quyết định kiến trúc nên không yêu cầu ADR.

## 9. Giới hạn và thời hạn hiệu lực

- Đây là point-in-time evidence tại thời điểm `capturedAt` trong `E-T2-01`.
- Kết luận phải được chạy lại nếu recorder scope, Permission Set hoặc hạ tầng lõi thay đổi.
- `PASS` của Task 2 không đồng nghĩa MANDATE-04 đã hoàn thành.
- Runtime JSON là dữ liệu đã chuẩn hóa từ output AWS CLI. Git commit và Pull Request chứa artifact này là change trail của evidence trong repository.

## 10. Lệnh tái kiểm tra

```powershell
aws configservice describe-configuration-recorder-status `
  --region us-east-1 `
  --profile cdo07-tf4-auditreadonly

aws configservice describe-delivery-channel-status `
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

## 11. Phê duyệt

| Vai trò | Người xác nhận | Trạng thái | Ngày |
| --- | --- | --- | --- |
| Người lập evidence - CDO07 | Bá Huân | Hoàn thành | 15/07/2026 |
| Reviewer Task 2 | Chờ reviewer trên Jira/PR | Pending | - |
