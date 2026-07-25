# CDO08-REL-28 - MSK Orders Archive Research & Trade-Off

**Owner:** Hoàng Nam
**Team:** CDO08
**Task:** CDO08-REL-28
**Ngày ghi nhận:** 2026-07-25
**Người gửi review:** Hoàng Nam / CDO08
**Người nhận review:** Tech Lead, PM
**Review scope:** Research phương án thay thế AWS MSK Connect S3 Sink cho archive topic `orders` ra S3
**Trạng thái:** Research/decision, chưa implement

## 1. Bối Cảnh

CDO08-REL-22 subtask 3 ban đầu dùng AWS MSK Connect để chạy S3 Sink Connector managed bởi AWS. Hướng này bị block ở bước `CreateConnector`.

Evidence đã có:

- `kafkaconnect:CreateConnector`, `kafkaconnect:TagResource` và `iam:PassRole` đều `allowed` khi simulate với Terraform apply role.
- Service-linked role `AWSServiceRoleForKafkaConnect` đã tồn tại.
- CloudTrail ghi nhận `CreateConnector` fail `AccessDenied` với cả GitHub Actions apply role và Admin/BreakGlass.
- CDO04 đã liên hệ AWS Support nhưng chưa có ETA gỡ restriction.
- Terraform đã gate connector bằng `msk_connect_connector_enabled=false` để CD apply xanh và giữ lại các foundation resources.

Vì restriction nằm ngoài quyền kiểm soát trực tiếp của team, REL-28 được tạo để research các phương án thay thế trước khi tạo task implementation riêng.

Mục tiêu research:

- Archive MSK topic `orders` ra S3.
- RPO mục tiêu <= 15 phút.
- Không làm thay đổi app request path khi chưa được duyệt.
- Không implement trước khi Tech Lead/PM chốt hướng bằng văn bản.

## 2. Phạm Vi Research

Ba phương án cần so sánh:

1. Kinesis Data Firehose với MSK làm nguồn trực tiếp, native, không qua Lambda.
2. Self-managed Kafka Connect chạy trên EKS với Confluent S3 Sink Connector.
3. Custom consumer tự code để đọc `orders` và ghi S3.

Docs này không mặc định chọn trước phương án. Kết luận cuối cần dựa trên evidence verify được và quyết định của Tech Lead/PM.

## 3. Option 1 - Kinesis Data Firehose Native MSK Source

### 3.1. Ý Tưởng

Tạo Firehose delivery stream dùng MSK cluster/topic `orders` làm source và S3 archive bucket làm destination.

Ưu điểm cần verify:

- Managed service, không tạo thêm Kafka Connect pod trong EKS.
- Ít vận hành runtime hơn self-managed Kafka Connect.
- Cost theo GB có thể thấp nếu traffic `orders` nhỏ.
- Phù hợp mục tiêu archive liên tục ra S3 nếu source/destination format đáp ứng replay.

### 3.2. Điều Kiện Firehose Cần

Theo AWS docs, Firehose đọc MSK private bootstrap brokers cần các điều kiện chính:

- MSK cluster ở trạng thái `ACTIVE`.
- MSK cluster có IAM là một access control method.
- Multi-VPC private connectivity được bật cho IAM access method.
- MSK cluster resource policy cho phép Firehose service principal gọi `kafka:CreateVpcConnection`.

Nếu dùng public bootstrap brokers thì MSK phải public accessible. Hướng public brokers không phù hợp với baseline hiện tại vì data layer đang private.

### 3.3. Kết Quả Verify Runtime Hiện Tại

Command verify đã chạy:

```powershell
aws kafka describe-cluster-v2 `
  --region us-east-1 `
  --profile tf4 `
  --cluster-arn <MSK_CLUSTER_ARN> `
  --query 'ClusterInfo.{State:State,ClientAuthentication:Provisioned.ClientAuthentication,ConnectivityInfo:Provisioned.ConnectivityInfo,CurrentVersion:Provisioned.CurrentVersion}' `
  --output json
```

Output ghi nhận:

```json
{
    "State": "ACTIVE",
    "ClientAuthentication": {
        "Sasl": {
            "Scram": {
                "Enabled": true
            },
            "Iam": {
                "Enabled": false
            }
        },
        "Unauthenticated": {
            "Enabled": false
        }
    },
    "ConnectivityInfo": null,
    "CurrentVersion": null
}
```

Diễn giải:

- `State=ACTIVE`: đạt điều kiện cluster active.
- `Sasl.Scram.Enabled=true`: MSK hiện đang phục vụ app bằng SCRAM.
- `Sasl.Iam.Enabled=false`: chưa đạt điều kiện IAM access control của Firehose private MSK source.
- `ConnectivityInfo=null`: chưa thấy Multi-VPC private connectivity cho IAM.

Kết luận tạm thời: Firehose là managed option đáng ưu tiên về mặt vận hành, nhưng runtime MSK hiện tại chưa đủ prerequisite để dùng ngay. Nếu muốn chọn Firehose, cần review riêng việc bật IAM auth, bật Multi-VPC private connectivity cho IAM và thêm cluster resource policy cho Firehose.

### 3.4. Rủi Ro / Blocker Cần Tech Lead/PM Review

- Bật IAM auth và Multi-VPC private connectivity có thể là thay đổi trên MSK runtime.
- Cần verify từ AWS docs/plan xem update connectivity có rolling broker update không và có ảnh hưởng producer/consumer hiện tại không.
- Cần đảm bảo app hiện tại tiếp tục dùng SCRAM bình thường, không đổi app config.
- Cần đảm bảo Firehose không yêu cầu public brokers.
- Cần đảm bảo IAM/resource policy không mở rộng quyền quá mức cần thiết.
- Cần kiểm tra format S3 output của Firehose có đủ replay cho REL-25 không.

### 3.5. Cost Ước Tính

Firehose MSK source được tính theo GB ingest/delivery. Theo pricing public hiện tại, tier đầu khoảng `0.055 USD/GB`.

Ví dụ tham khảo:

- 1 GB/ngày: khoảng `30 * 0.055 = 1.65 USD/tháng`, chưa gồm S3 storage/lifecycle/request/log.
- 10 GB/ngày: khoảng `300 * 0.055 = 16.5 USD/tháng`, chưa gồm S3 storage/lifecycle/request/log.

Cost thực tế cần tính lại theo traffic `orders` runtime khi có metric chính xác.

## 4. Option 2 - Self-Managed Kafka Connect Trên EKS

### 4.1. Ý Tưởng

Chạy Kafka Connect worker trong EKS và dùng Confluent S3 Sink Connector để đọc topic `orders`, ghi object xuống S3 archive bucket.

Hướng này tận dụng lại nhiều phần từ plan AWS MSK Connect cũ:

- S3 archive bucket `tf4-msk-orders-archive-511825856493-us-east-1`.
- Prefix `orders/`.
- Partition convention `orders/topic=orders/year=YYYY/month=MM/day=DD/hour=HH/`.
- Confluent S3 Sink Connector version đã pin.
- Flush/rotate <= 15 phút.
- DLQ/error handling.
- Verify object trong S3 và parse/readability ở subtask validate sau.

### 4.2. Workload Cần Tạo

Hướng này cần tạo thêm workload/pod trong EKS, ví dụ:

- `Deployment` hoặc `StatefulSet` Kafka Connect worker.
- `ServiceAccount` riêng.
- IRSA hoặc IAM path được duyệt để ghi S3.
- ConfigMap chứa worker properties và connector config.
- Secret reference từ External Secrets, không hardcode secret thật.
- PodDisruptionBudget nếu cần.
- Probes, requests/limits, security context.

Runtime flow:

```text
MSK topic orders  ->  Kafka Connect worker pod on EKS  ->  S3 archive bucket orders/
```

### 4.3. Ảnh Hưởng Runtime Cần Verify

Ảnh hưởng trực tiếp:

- Không đổi app config.
- Không đổi checkout/accounting request path.
- Không cần public MSK.
- Pod mới chỉ đọc topic `orders` từ MSK và ghi object xuống S3.

Ảnh hưởng gián tiếp:

- Thêm consumer đọc từ MSK nên có thêm network/CPU nhỏ trên broker.
- Thêm pod tiêu thụ CPU/memory trong EKS.
- Nếu sizing sai, pod có thể OOM/restart hoặc tạo log/error nhiều.
- Nếu connector config sai, archive có thể delay nhưng không nên làm app fail trực tiếp.

Sizing khởi điểm cần review:

- `replicas=1`.
- `tasks.max=1`.
- CPU request/limit conservative, ví dụ bắt đầu quanh `100m-250m` request và `500m` limit nếu cluster còn capacity.
- Memory request/limit cần test theo connector image thực tế, có thể bắt đầu `256Mi-512Mi` request và `1Gi` limit rồi right-size theo runtime.

### 4.4. Rủi Ro / Blocker

- Team phải vận hành Kafka Connect runtime trong EKS.
- Cần build/pin/sign image hoặc cơ chế plugin artifact phù hợp Kyverno/Cosign.
- Cần quản lý Kafka Connect internal topics: config/offset/status.
- Cần quan sát consumer lag, connector status, restart behavior.
- Nếu worker bị mất lâu hơn 15 phút, archive có thể vi phạm RPO cho đến khi catch-up.

### 4.5. Cost Ước Tính

Nếu dùng được EKS capacity hiện có, marginal cost chủ yếu là CPU/memory/logs/S3 request.

Nếu workload làm cluster phải scale thêm node, ví dụ thêm một node cỡ `t3.medium`, cost khoảng `30 USD/tháng` chưa gồm EBS/log/S3. Con số này chỉ là sizing tham khảo, cần verify lại với node family thực tế của cluster.

## 5. Option 3 - Custom Consumer

### 5.1. Ý Tưởng

Tự viết một service đọc topic `orders` từ MSK và ghi object xuống S3 theo format replay do team định nghĩa.

Ưu điểm cần verify:

- Linh hoạt nhất về format object, partition path và metadata replay.
- Có thể tối ưu đúng use case `orders`.
- Không phụ thuộc AWS MSK Connect hoặc Confluent S3 Sink.

### 5.2. Effort Và Rủi Ro Thực Tế

Các phần phải tự xử lý:

- Consumer group và offset commit.
- Retry khi S3/Kafka/network lỗi.
- DLQ hoặc error store cho record lỗi.
- Duplicate handling/idempotency.
- Ordering expectation theo partition.
- Batch/flush cadence để đạt RPO <= 15 phút.
- Schema/versioning nếu payload thay đổi.
- Multipart upload nếu object lớn.
- Replay parser/tooling cho REL-25.
- Observability: lag, delivery latency, failure rate, S3 write errors.
- Restart behavior để không mất dữ liệu ngoài RPO.

Rủi ro chính:

- Dễ tạo bug mất/duplicate record hơn Kafka Connect/Firehose.
- Cần nhiều test hơn trước khi xem là backup/archive đáng tin.
- Engineering cost cao hơn so với dùng managed service hoặc connector chuẩn.

### 5.3. Cost Ước Tính

Infra cost có thể thấp nếu service nhỏ và dùng EKS capacity hiện có. Tuy nhiên engineering/maintenance cost là cao nhất vì team phải tự đảm bảo behavior production của backup path.

Custom consumer chỉ nên là last resort nếu Firehose và self-managed Kafka Connect đều không khả thi.

## 6. Bảng So Sánh

| Phương án                           | Ưu điểm                                                                                                                    | Rủi ro / blocker                                                                                                                                       | Cost ước tính                                                                                                          |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| Firehose native MSK source          | Managed service, không tạo pod trong EKS, ít vận hành runtime, cost theo GB thấp nếu traffic nhỏ                           | Runtime MSK hiện chưa đủ prerequisite ở mục 3.3; cần review IAM auth, Multi-VPC private connectivity, cluster policy và khả năng rolling broker update | Khoảng `0.055 USD/GB` tier đầu. 1 GB/ngày khoảng `1.65 USD/tháng`, 10 GB/ngày khoảng `16.5 USD/tháng`, chưa gồm S3/log |
| Self-managed Kafka Connect trên EKS | Dùng connector chuẩn, tương thích SCRAM hiện tại, tận dụng được plan S3 Sink cũ, không cần chờ AWS MSK Connect restriction | Tạo thêm pod/workload trong EKS, phải vận hành image/plugin/resources/probes/internal topics/consumer lag                                              | Nếu dùng capacity hiện có thì marginal thấp; nếu scale thêm node cỡ `t3.medium` khoảng `30 USD/tháng`                  |
| Custom consumer                     | Linh hoạt nhất, không phụ thuộc connector/service restriction                                                              | Engineering/ops risk cao nhất: offset, retry, DLQ, duplicate, schema, replay, observability đều phải tự làm                                            | Infra có thể thấp nhưng engineering/maintenance cost cao                                                               |

## 7. Kết Luận Research Tạm Thời

Kết luận chưa phải quyết định implement cuối cùng:

- Firehose là candidate managed tốt nhất nếu Tech Lead/PM duyệt và các prerequisite MSK có thể bật an toàn.
- Self-managed Kafka Connect là fallback production khả thi hơn custom consumer nếu Firehose không được duyệt hoặc không đáp ứng điều kiện.
- Custom consumer không nên chọn trước vì rủi ro tự xử lý offset/retry/replay cao nhất.

Quyết định cần Tech Lead/PM chốt bằng văn bản trước khi tạo task implementation.

## 8. Open Questions Cho Tech Lead/PM

- Có duyệt bật IAM auth trên MSK production để thử Firehose native MSK source không?
- Có duyệt bật Multi-VPC private connectivity cho IAM access method không?
- Update MSK auth/connectivity có rolling broker update không, và nếu có thì có được chấp nhận trong thời điểm này không?
- Có yêu cầu giữ SCRAM app path hiện tại hoàn toàn không đổi không?
- Nếu chọn Firehose, S3 output format/prefix nào được chốt để REL-25 replay được?
- Nếu Firehose không khả thi, có chấp nhận tạo pod self-managed Kafka Connect trong EKS không?
- Nếu self-managed Kafka Connect được chọn, namespace nào được duyệt: `techx-tf4` hay namespace platform riêng?
- Nếu self-managed Kafka Connect được chọn, dùng IRSA riêng hay IAM path nào?
- Có cần tạo internal topics và DLQ topic bằng Terraform/script trước khi bật worker không?

## 9. Output Cần Có Sau Review

- Tech Lead/PM chọn một hướng: Firehose, self-managed Kafka Connect, hoặc custom consumer.
- Các prerequisite/open questions được trả lời bằng văn bản.
- Task implementation riêng được tạo dựa trên hướng đã chọn.
- Không implement trong REL-28 trước khi có quyết định.

## 10. References

- AWS Firehose MSK source documentation: https://docs.aws.amazon.com/firehose/latest/dev/writing-with-msk.html
- AWS Firehose access control for private MSK: https://docs.aws.amazon.com/firehose/latest/dev/controlling-access.html
- AWS MSK Multi-VPC private connectivity: https://docs.aws.amazon.com/msk/latest/developerguide/aws-access-mult-vpc.html
- AWS Firehose pricing: https://aws.amazon.com/firehose/pricing/
- AWS MSK pricing: https://aws.amazon.com/msk/pricing/
