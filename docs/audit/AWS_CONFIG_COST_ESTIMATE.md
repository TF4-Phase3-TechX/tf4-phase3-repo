# AWS Config Cost Estimate - TF4 Task 2

**Ngày lập**: 14/07/2026
**Account/Region**: `511825856493` / `us-east-1`
**Owner**: CDO07 Auditability
**Ticket triển khai**: [`AUDIT-009-enable-aws-config-change-trail.md`](tickets/AUDIT-009-enable-aws-config-change-trail.md)

## 1. Mục tiêu

Ước tính chi phí bật AWS Config cho Task 2 và Directive #4 trong ngân sách khoảng `$300/tuần/TF`. Phương án ưu tiên khả năng forensic nhưng giới hạn recorder vào resource hạ tầng lõi, không bật toàn bộ resource types và không dùng Conformance Pack trong giai đoạn đầu.

## 2. Đơn giá sử dụng

Theo [AWS Config Pricing](https://aws.amazon.com/config/pricing/) tại thời điểm 14/07/2026:

| Hạng mục | Đơn giá tham chiếu |
| --- | ---: |
| Continuous configuration item | `$0.003` / CI |
| Periodic configuration item | `$0.012` / CI |
| Config Rule evaluation, 100.000 lượt đầu | `$0.001` / evaluation |
| Conformance Pack evaluation, 100.000 lượt đầu | `$0.001` / evaluation |

S3 delivery channel tính theo [Amazon S3 Pricing](https://aws.amazon.com/s3/pricing/). Estimate này dùng `$0.023/GB-tháng` cho S3 Standard tại `us-east-1`; request cost được làm tròn vào phần dự phòng.

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
| **Tổng** | **65** |

Danh sách loại resource được kiểm tra theo [Supported Resource Types for AWS Config](https://docs.aws.amazon.com/config/latest/developerguide/resource-config-reference.html). `AWS::Logs::LogGroup` không được hỗ trợ nên không tính vào recorder scope; AWS Config hiện chỉ liệt kê `AWS::Logs::Destination` cho CloudWatch Logs.

## 4. Chi phí recorder

### Khởi tạo lần đầu

Khi bật recorder, AWS Config tạo baseline CI cho resource được phát hiện:

```text
65 resources x $0.003 = $0.195
```

Làm tròn: **$0.20 chi phí khởi tạo**. Số thực tế có thể cao hơn nhẹ nếu resource thay đổi trong lúc initial discovery.

### Kịch bản theo số thay đổi

| Kịch bản | CI thay đổi/tháng | Recorder cost | Mô tả |
| --- | ---: | ---: | --- |
| Ít thay đổi | 100 | `$0.30` | Lab ổn định, ít Terraform apply |
| Dự kiến | 500 | `$1.50` | Nhiều PR/deploy và một số thay đổi IAM/network |
| Cao | 2.000 | `$6.00` | Rehearsal, remediation và thay đổi hạ tầng dày |

Phương án `CONTINUOUS` được chọn vì Directive #4 cần timeline chi tiết. Nếu mọi resource tạo một periodic CI mỗi ngày, upper-bound của daily recording là:

```text
65 resources x 30 days x $0.012 = $23.40/month
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

Conservative estimate nếu đánh giá mỗi ngày trên 1 CloudTrail/account check, 5 S3 buckets cho mỗi S3 rule và 1 VPC:

```text
(1 + 5 + 5 + 1) evaluations/day x 30 x $0.001
= 360 evaluations x $0.001
= $0.36/month
```

Actual cost có thể thấp hơn với change-triggered evaluation. Nếu rules bị defer thì trừ `$0.36/tháng` khỏi tổng estimate.

## 6. Chi phí S3

Configuration history/snapshot của scope 65 resource được giả định nhỏ hơn 1 GB/tháng:

```text
1 GB x $0.023/GB-month = $0.023/month
```

Làm tròn storage và request cost: **$0.03/tháng**. Versioning và Object Lock `COMPLIANCE` 30 ngày có thể tăng storage do giữ các version trong suốt thời hạn khóa, nhưng với JSON history nhỏ thì vẫn không đáng kể so với budget TF4.

## 7. Tổng chi phí tháng đầu

Tổng dưới đây gồm `$0.195` initial discovery, bốn Config Rules `$0.36` và S3 `$0.03`:

| Kịch bản | Tổng/tháng đầu | Quy đổi/tuần |
| --- | ---: | ---: |
| Ít thay đổi, 100 CI | **$0.89** | **$0.21** |
| Dự kiến, 500 CI | **$2.09** | **$0.48** |
| Cao, 2.000 CI | **$6.59** | **$1.52** |

Các tháng sau không còn khoản initial discovery `$0.195` nếu resource count không biến động lớn.

## 8. Cost guardrail đề xuất

- Phê duyệt budget AWS Config tối đa: **$10/tháng**, tương đương khoảng **$2.30/tuần**.
- Mức này dưới 1% ngân sách `$300/tuần` của TF4.
- Chỉ record 13 resource types đã liệt kê; không bật `all_supported` trong ticket đầu tiên.
- Chưa triển khai Conformance Pack.
- Review `GetDiscoveredResourceCounts` và Cost Explorer sau 24-48 giờ đầu.
- Nếu forecast vượt `$10/tháng`, CDO07 và CDO04 review số CI/rule evaluations trước khi mở rộng scope.

## 9. Giới hạn của estimate

- Giá và resource count có thể thay đổi sau ngày 14/07/2026.
- Chi phí thực tế phụ thuộc số lần resource thay đổi, không chỉ số resource hiện tại.
- Estimate chưa gồm thuế và data transfer bất thường.
- AWS Config không thay thế CloudTrail: Config cung cấp trạng thái trước/sau; CloudTrail cung cấp principal, API call, source IP và request parameters để dựng timeline ai-làm-gì-khi-nào.
