# AWS Config Cost Estimate - TF4 Task 2

**Ngày lập**: 14/07/2026
**Account/Region**: `511825856493` / `us-east-1`
**Owner**: CDO07 Auditability
**Ticket triển khai**: [`AUDIT-009-enable-aws-config-change-trail.md`](tickets/AUDIT-009-enable-aws-config-change-trail.md)

## 1. Mục tiêu

Ước tính chi phí bật AWS Config cho Task 2 và cung cấp evidence AWS Config cho MANDATE-04 trong ngân sách khoảng `$300/tuần/TF`. Phương án ưu tiên khả năng forensic nhưng giới hạn recorder vào resource hạ tầng lõi, không bật toàn bộ resource types và không dùng Conformance Pack trong giai đoạn đầu.

## 2. Đơn giá sử dụng

Theo [AWS Config Pricing](https://aws.amazon.com/config/pricing/) tại thời điểm 14/07/2026:

| Hạng mục | Đơn giá tham chiếu |
| --- | ---: |
| Continuous configuration item | `$0.003` / CI |
| Periodic configuration item | `$0.012` / CI |
| Config Rule evaluation, 100.000 lượt đầu | `$0.001` / evaluation |
| Conformance Pack evaluation, 100.000 lượt đầu | `$0.001` / evaluation |

S3 staging, WORM archive và Same-Region Replication tính theo [Amazon S3 Pricing](https://aws.amazon.com/s3/pricing/). Estimate này dùng `$0.023/GB-tháng` cho S3 Standard tại `us-east-1`; request/replication cost được làm tròn vào phần dự phòng. Baseline dùng SSE-S3 nên không phát sinh AWS KMS request hoặc customer managed key cost.

S3 Replication metrics được tính bảo thủ như bốn CloudWatch custom metrics cho một replication rule. Estimate dùng `$0.30/metric-tháng`, chưa trừ Free Tier, theo [Amazon CloudWatch Pricing](https://aws.amazon.com/cloudwatch/pricing/).

AWS Config tính tiền theo số configuration items được tạo, không phải chỉ theo số resource đang tồn tại. Continuous recording tạo CI khi resource được tạo, thay đổi hoặc xóa. Tham chiếu: [Recording AWS Resources with AWS Config](https://docs.aws.amazon.com/config/latest/developerguide/select-resources.html).

## 3. Resource scope hiện tại

Số lượng được lấy bằng AWS CLI read-only ngày 14/07/2026. Vì Audit profile thiếu một số `ec2:Describe*` và `eks:List*`, các count tương ứng được đối chiếu tạm bằng profile BaseReadOnly; đây cũng là permission gap đã ghi trong AUDIT-009.

| Resource type | Số lượng hiện tại |
| --- | ---: |
| `AWS::EKS::Cluster` | 1 |
| `AWS::EKS::Nodegroup` | 1 |
| `AWS::EKS::Addon` | 4 |
| `AWS::IAM::Role` | 35 |
| `AWS::EC2::VPC` | 1 |
| `AWS::EC2::SecurityGroup` | 7 |
| `AWS::EC2::Subnet` | 4 |
| `AWS::EC2::RouteTable` | 3 |
| `AWS::EC2::NetworkAcl` | 1 |
| `AWS::EC2::NatGateway` | 1 |
| `AWS::EC2::InternetGateway` | 1 |
| `AWS::S3::Bucket` | 5 |
| `AWS::CloudTrail::Trail` | 1 |
| **Baseline đã đếm** | **65** |

Để đáp ứng Directive #4 và truy vết bastion/SSM, recorder bổ sung `AWS::EC2::Instance`, `AWS::EC2::NetworkInterface`, `AWS::EC2::Volume`, `AWS::EC2::LaunchTemplate`, `AWS::AutoScaling::AutoScalingGroup`, `AWS::IAM::InstanceProfile`, `AWS::IAM::Policy`, `AWS::IAM::OIDCProvider`, `AWS::SSM::Document`, `AWS::SSM::ManagedInstanceInventory`, `AWS::KMS::Key`, `AWS::ECR::Repository`, `AWS::DynamoDB::Table`, `AWS::Logs::LogGroup`, `AWS::S3::BucketPolicy`, `AWS::Config::ConfigurationRecorder`, `AWS::AccessAnalyzer::Analyzer` và ba resource ELBv2. Do Audit profile chưa đủ API để đếm toàn bộ các loại mới, estimate dùng giả định bảo thủ **150 resource** cho initial discovery. CDO07 phải thay giả định này bằng `GetDiscoveredResourceCounts` sau 24-48 giờ đầu.

Danh sách 33 loại resource được kiểm tra theo [Supported Resource Types for AWS Config](https://docs.aws.amazon.com/config/latest/developerguide/resource-config-reference.html). `AWS::Logs::LogGroup` được đưa vào scope để theo dõi retention/KMS của EKS control-plane audit log. Hai bucket mới làm số `AWS::S3::Bucket` tăng từ 5 lên 7 sau triển khai.

## 4. Chi phí recorder

### Khởi tạo lần đầu

Khi bật recorder, AWS Config tạo baseline CI cho resource được phát hiện:

```text
150 resources x $0.003 = $0.45
```

Giả định kế hoạch: **$0.45 chi phí khởi tạo**. Số thực tế được thay bằng count sau khi recorder hoàn tất initial discovery.

### Kịch bản theo số thay đổi

| Kịch bản | CI thay đổi/tháng | Recorder cost | Mô tả |
| --- | ---: | ---: | --- |
| Ít thay đổi | 100 | `$0.30` | Lab ổn định, ít Terraform apply |
| Dự kiến | 500 | `$1.50` | Nhiều PR/deploy và một số thay đổi IAM/network |
| Cao | 2.000 | `$6.00` | Rehearsal, remediation và thay đổi hạ tầng dày |

Phương án `CONTINUOUS` được chọn vì Directive #4 cần timeline chi tiết. Nếu mọi resource tạo một periodic CI mỗi ngày, upper-bound của daily recording là:

```text
150 resources x 30 days x $0.012 = $54.00/month
```

Với môi trường TF4 có số resource nhỏ và số thay đổi dự kiến dưới 2.000 CI/tháng, continuous recording vừa chi tiết hơn vừa có chi phí thấp hơn upper-bound periodic.

## 5. Chi phí Config Rules tùy chọn

Bốn managed rules đề xuất:

```text
CLOUD_TRAIL_ENABLED
S3_BUCKET_PUBLIC_READ_PROHIBITED
S3_BUCKET_PUBLIC_WRITE_PROHIBITED
VPC_DEFAULT_SECURITY_GROUP_CLOSED
```

Conservative estimate nếu đánh giá mỗi ngày trên 1 CloudTrail/account check, 7 S3 buckets sau khi thêm staging/archive cho mỗi S3 rule và 1 VPC:

```text
(1 + 7 + 7 + 1) evaluations/day x 30 x $0.001
= 480 evaluations x $0.001
= $0.48/month
```

Actual cost có thể thấp hơn với change-triggered evaluation. Nếu rules bị defer thì trừ `$0.48/tháng` khỏi tổng estimate.

## 6. Chi phí S3

AWS Config ghi history/snapshot vào staging bucket. Same-Region Replication giữ thêm một bản tại WORM archive bucket; archive áp dụng Object Lock `COMPLIANCE` 30 ngày. AWS Config không ghi trực tiếp vào archive vì delivery channel không hỗ trợ destination có default Object Lock retention.

Giả định dữ liệu AWS Config nhỏ hơn 1 GB/tháng, storage của hai bản sao là:

```text
1 GB x 2 buckets x $0.023/GB-month = $0.046/month
```

Làm tròn tổng storage, versioning, PUT/replication request và notification request thành reserve **$0.10/tháng**. Đây là conservative reserve cho tải nhỏ; CDO07 thay bằng chi phí thực tế sau 24-48 giờ. Object Lock `COMPLIANCE` có thể tăng storage do giữ các version trong suốt thời hạn khóa.

Replication metrics theo dõi `BytesPendingReplication`, `OperationsPendingReplication`, `ReplicationLatency` và `OperationsFailedReplication`:

```text
4 metrics x $0.30/metric-month = $1.20/month
```

Reserve **$1.20/tháng** chưa trừ CloudWatch Free Tier. Không bật S3 Replication Time Control; failure event `s3:Replication:OperationFailedReplication` được gửi qua S3 Event Notifications. Tham chiếu: [Receiving replication failure events](https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication-metrics-events.html).

## 7. Tổng chi phí tháng đầu

Tổng dưới đây gồm `$0.45` initial discovery, bốn Config Rules `$0.48`, S3 staging/archive/replication reserve `$0.10` và replication metrics `$1.20`:

| Kịch bản | Tổng/tháng đầu | Quy đổi/tuần |
| --- | ---: | ---: |
| Ít thay đổi, 100 CI | **$2.53** | **$0.58** |
| Dự kiến, 500 CI | **$3.73** | **$0.86** |
| Cao, 2.000 CI | **$8.23** | **$1.89** |

Các tháng sau không còn khoản initial discovery `$0.45` nếu resource count không biến động lớn.

## 8. Cost guardrail đề xuất

- Phê duyệt budget AWS Config tối đa: **$10/tháng**, tương đương khoảng **$2.30/tuần**.
- Mức này dưới 1% ngân sách `$300/tuần` của TF4.
- Chỉ record 33 resource types đã liệt kê trong AUDIT-009; không bật `all_supported` trong ticket đầu tiên.
- Chưa triển khai Conformance Pack.
- Review `GetDiscoveredResourceCounts` và Cost Explorer sau 24-48 giờ đầu.
- Nếu forecast vượt `$10/tháng`, CDO07 và CDO04 review số CI/rule evaluations trước khi mở rộng scope.

## 9. Giới hạn của estimate

- Giá và resource count có thể thay đổi sau ngày 14/07/2026.
- Chi phí thực tế phụ thuộc số lần resource thay đổi, không chỉ số resource hiện tại.
- Estimate chưa gồm thuế và data transfer bất thường.
- S3 reserve giả định Same-Region Replication và dưới 1 GB dữ liệu AWS Config mỗi tháng; phải cập nhật nếu replication volume hoặc request count cao hơn.
- Replication metrics được tính trước Free Tier; chi phí thực tế có thể thấp hơn. S3 RTC không nằm trong estimate và không được bật trong ticket này.
- Nếu chuyển baseline từ SSE-S3 sang SSE-KMS, phải bổ sung KMS key/request cost trước khi apply.
- Budget `$10/tháng` trong tài liệu này chỉ áp dụng cho AWS Config; chưa bao gồm remediation/archival của CloudTrail, EKS audit log, forensic drill hoặc các hạng mục khác của MANDATE-04.
- AWS Config không thay thế CloudTrail: Config cung cấp trạng thái trước/sau; CloudTrail cung cấp principal, API call, source IP và request parameters để dựng timeline ai-làm-gì-khi-nào.
