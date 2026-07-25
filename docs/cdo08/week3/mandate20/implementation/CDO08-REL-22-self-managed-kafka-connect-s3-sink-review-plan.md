# CDO08-REL-22 - MSK Orders Archive Alternative Review Plan

**Owner:** Hoàng Nam
**Team:** CDO08
**Task:** CDO08-REL-22
**Subtask:** Deploy MSK Connect S3 Sink Connector for orders
**Ngày ghi nhận:** 2026-07-25
**Người gửi review:** Hoàng Nam / CDO08
**Người nhận review:** Tech Lead, PM
**Review scope:** Firehose-first production alternative, with self-managed Kafka Connect fallback, after AWS MSK Connect `CreateConnector` is blocked at account/service side

## 1. Bối Cảnh

Plan ban đầu của subtask 3 là dùng AWS MSK Connect để chạy S3 Sink Connector managed bởi AWS. Hướng này vẫn là managed path đúng với ý tưởng ban đầu, nhưng runtime hiện tại đang bị block ở bước `CreateConnector`.

Evidence đã có:

- `kafkaconnect:CreateConnector`, `kafkaconnect:TagResource` và `iam:PassRole` đều `allowed` khi simulate với Terraform apply role.
- Service-linked role `AWSServiceRoleForKafkaConnect` đã tồn tại.
- CloudTrail ghi nhận `CreateConnector` fail `AccessDenied` với cả GitHub Actions apply role và Admin/BreakGlass.
- Terraform hiện đã gate connector bằng `msk_connect_connector_enabled=false` để CD apply xanh và giữ lại các foundation resources.

Vì vậy, nếu không xin/gỡ được AWS Support restriction trong thời gian phù hợp, cần chọn một hướng archive MSK khác để vẫn đạt mục tiêu Mandate 20: archive topic `orders` ra S3 với RPO <= 15 phút.

Xem xét Kinesis Data Firehose. Vì Firehose là managed service và phù hợp hơn về vận hành nếu đáp ứng điều kiện, docs này chuyển sang hướng **Firehose-first** để review, đồng thời giữ self-managed Kafka Connect như fallback nếu Firehose không khả thi.

## 2. Quyết Định Đề Xuất

Hướng đề xuất cho review:

1. **Preferred production alternative:** Kinesis Data Firehose MSK source -> S3, nếu các điều kiện ở mục 3.2 được xử lý và không tạo thay đổi rủi ro lên app traffic path.
2. **Fallback production path:** self-managed Kafka Connect trên EKS + Confluent S3 Sink Connector, nếu Firehose không đáp ứng điều kiện sau review.
3. **Last resort:** custom consumer tự code, chỉ chọn nếu cả Firehose và self-managed Kafka Connect đều không khả thi.

Lý do ưu tiên Firehose nếu verify được:

- Managed service, không cần vận hành Kafka Connect worker pod trong cluster.
- Cost theo GB có thể thấp hơn MSK Connect/Kafka Connect worker nếu traffic `orders` nhỏ.
- Ít thành phần runtime mới trong EKS hơn, giảm rủi ro pod resource/probe/image/plugin.
- Vẫn đạt mục tiêu chính của REL-22: archive `orders` từ MSK sang S3 để có recovery object cho REL-25.

## 3. Firehose Managed Alternative

### 3.1. Điều Kiện Firehose Cần

Theo AWS docs, Firehose đọc MSK private bootstrap brokers cần các điều kiện chính:

- MSK cluster ở trạng thái `ACTIVE`.
- MSK cluster có IAM là một access control method.
- Multi-VPC private connectivity được bật cho IAM access method.
- MSK cluster resource policy cho phép Firehose service principal gọi `kafka:CreateVpcConnection`.

Nếu dùng public bootstrap brokers thì MSK phải public accessible, nhưng hướng này không phù hợp với baseline hiện tại vì data layer đang private.

### 3.2. Kết Quả Verify Runtime

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

Kết luận: Firehose là hướng managed tốt hơn về mặt vận hành, nhưng **chưa đủ điều kiện để dùng ngay với MSK hiện tại**. Để đi theo Firehose cần review thêm việc bật IAM auth, Multi-VPC private connectivity cho IAM và cluster resource policy cho Firehose.

### 3.3. Thay Đổi Cần Có Nếu Chọn Firehose

Nếu Tech Lead/PM chọn Firehose, cần thêm một implementation plan/PR riêng cho các phần sau:

- Bật IAM access control trên MSK nếu được phê duyệt.
- Bật Multi-VPC private connectivity cho IAM access method.
- Thêm MSK cluster resource policy cho Firehose `kafka:CreateVpcConnection`.
- Tạo Firehose delivery stream source MSK topic `orders`, destination S3 archive bucket.
- Tạo Firehose service role least-privilege.
- Cấu hình S3 prefix replay-friendly tương đương convention hiện tại.
- Cấu hình buffer/flush để delivery latency <= 15 phút.
- Verify S3 object, data freshness, CloudWatch delivery errors và SLO.

Rủi ro cần review:

- Update MSK connectivity/auth có thể tạo rolling broker update theo AWS docs.
- Cần đảm bảo app hiện tại vẫn tiếp tục dùng SCRAM bình thường, không đổi app config.
- Cần đảm bảo Firehose không yêu cầu public brokers.
- Cần đảm bảo IAM/resource policy không mở rộng quyền quá mức cần thiết.

### 3.4. Firehose Verification Gate

Trước khi merge PR tạo Firehose delivery stream, cần có gate:

- MSK cluster vẫn `ACTIVE`.
- IAM auth đã enabled nếu chọn Firehose.
- Multi-VPC private connectivity cho IAM đã enabled.
- Cluster resource policy cho Firehose đã được review.
- Firehose delivery stream plan không thay đổi app services.
- S3 destination là bucket archive đã có encryption/versioning/lifecycle.
- Buffering/data freshness <= 15 phút.
- Có rollback plan: disable/delete Firehose stream bằng Terraform revert, không xoá archive object đã ghi.

## 4. Trade-Off Và Cost Ước Tính

| Hướng                                  | Điểm mạnh                                                                               | Rủi ro / blocker                                                                              | Cost ước tính                                                                                                    |
| -------------------------------------- | --------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| AWS MSK Connect S3 Sink                | Managed Kafka Connect, đúng plan ban đầu, ít vận hành hơn self-managed                  | Đang bị account/service-side restriction ở `CreateConnector`                                  | Khoảng 730 giờ/tháng _ 1 MCU _ 0.11 USD/giờ = khoảng 80 USD/tháng, chưa gồm S3/logs                              |
| Kinesis Data Firehose MSK source -> S3 | Managed hơn, không tạo pod trong EKS, cost theo GB thấp nếu traffic nhỏ                 | Cần xử lý prerequisite ở mục 3.2 trước khi triển khai                                         | Firehose MSK source khoảng 0.055 USD/GB ở tier đầu. Ví dụ 1 GB/ngày khoảng 1.65 USD/tháng, chưa gồm S3/lifecycle |
| Self-managed Kafka Connect trên EKS    | Dùng được SCRAM hiện tại, không cần đổi MSK auth path, vẫn dùng Confluent S3 Sink chuẩn | Cần tạo pod/workload mới trong EKS; phải vận hành image/plugin/resources/probes/offset topics | Nếu dùng capacity EKS hiện có thì marginal cost thấp; nếu cần thêm node cỡ t3.medium khoảng 30 USD/tháng         |
| Custom consumer                        | Linh hoạt nhất, có thể tối ưu sát use case                                              | Tự xử lý offset, retry, DLQ, duplicate, schema, multipart upload, replay; rủi ro bug cao nhất | Infra có thể thấp nhưng engineering/ops cost cao                                                                 |

Decision cho review:

- Nếu có thể bật Firehose mà không ảnh hưởng app path và không tạo rolling risk không được chấp nhận, Firehose là hướng production nên ưu tiên.
- Nếu Firehose chưa qua được prerequisite/review trong thời gian mandate, self-managed Kafka Connect là fallback tốt hơn custom consumer.
- Custom consumer không nên là lựa chọn đầu tiên vì backup/archive cần tin cậy về offset, retry, duplicate và replay.

## 5. Self-Managed Kafka Connect Fallback

Self-managed Kafka Connect không phải hướng preferred nếu Firehose pass review, nhưng là fallback khả thi nhất nếu Firehose chưa qua được prerequisite/review trong thời gian mandate.

### 5.1. Thay Đổi So Với Plan AWS MSK Connect Cũ

Những phần giữ lại:

- S3 archive bucket `tf4-msk-orders-archive-511825856493-us-east-1`.
- Prefix `orders/`.
- Partition convention `orders/topic=orders/year=YYYY/month=MM/day=DD/hour=HH/`.
- Confluent S3 Sink Connector version đã pin.
- Flush/rotate <= 15 phút.
- DLQ/error handling.
- Không hardcode credential trong manifest/evidence.
- Verify object trong S3 và parse/readability ở subtask 4.

Những phần thay đổi:

- Không dùng resource `aws_mskconnect_connector` khi account còn bị block.
- Không dùng AWS MSK Connect worker capacity.
- Tạo thêm Kubernetes workload chạy Kafka Connect worker.
- Workload có thể là `Deployment` hoặc `StatefulSet`, chạy trong namespace `techx-tf4` hoặc namespace platform được duyệt.
- Plugin được đóng gói vào image hoặc initContainer tải từ artifact bucket theo cách đã review.
- Credential lấy từ Kubernetes Secret đã sync từ AWS Secrets Manager qua External Secrets.
- Offset/status/config topics cần được tạo/quản lý trên MSK để Kafka Connect hoạt động bền vững.

### 5.2. Ảnh Hưởng Runtime Của Self-Managed Kafka Connect

Hướng này sẽ tạo thêm pod mới trong cluster, ví dụ `orders-s3-connect` hoặc `kafka-connect-orders-s3`.

Ảnh hưởng trực tiếp:

- Không đổi app config.
- Không đổi checkout/accounting request path.
- Không cần public MSK.
- Pod mới chỉ đọc topic `orders` từ MSK và ghi object xuống S3.

Ảnh hưởng gián tiếp cần quan sát:

- Thêm consumer đọc từ MSK nên có thêm network/CPU nhỏ trên broker.
- Thêm pod tiêu thụ CPU/memory trong EKS.
- Nếu sizing sai, pod có thể bị OOM/restart hoặc tạo log/error nhiều.
- Nếu connector config sai, archive có thể delay nhưng không nên làm app fail trực tiếp.

Guardrail cần có:

- `replicas=1`, `tasks.max=1` khi bắt đầu.
- Requests/limits rõ ràng, conservative.
- Probes và log monitoring.
- PodDisruptionBudget nếu cần availability.
- Image pinned, không dùng `latest`.
- SecurityContext non-root, drop capabilities.
- Rollback bằng scale worker về `0` hoặc revert GitOps PR.

## 6. Self-Managed Kafka Connect Runtime Design

### 6.1. Worker

Worker cần các config cơ bản:

```properties
bootstrap.servers=<MSK_SASL_SCRAM_BOOTSTRAP>
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_USERNAME}" password="${KAFKA_PASSWORD}";

group.id=orders-s3-archive-connect
config.storage.topic=orders-s3-archive-connect-config
offset.storage.topic=orders-s3-archive-connect-offsets
status.storage.topic=orders-s3-archive-connect-status

key.converter=org.apache.kafka.connect.storage.StringConverter
value.converter=org.apache.kafka.connect.json.JsonConverter
value.converter.schemas.enable=false
offset.flush.interval.ms=60000
```

Internal topics:

```properties
config.storage.replication.factor=2
offset.storage.replication.factor=2
status.storage.replication.factor=2
```

Với MSK baseline 2 broker, replication factor 2 phù hợp hơn replication factor 3.

### 6.2. S3 Sink Connector

Connector config giữ tương đương plan cũ:

```properties
name=orders-s3-sink
connector.class=io.confluent.connect.s3.S3SinkConnector
tasks.max=1
topics=orders

s3.region=us-east-1
s3.bucket.name=tf4-msk-orders-archive-511825856493-us-east-1
topics.dir=orders
storage.class=io.confluent.connect.s3.storage.S3Storage
format.class=io.confluent.connect.s3.format.json.JsonFormat
schema.compatibility=NONE

partitioner.class=io.confluent.connect.storage.partitioner.TimeBasedPartitioner
path.format='topic'=orders/'year'=YYYY/'month'=MM/'day'=dd/'hour'=HH
partition.duration.ms=3600000
locale=en
timezone=UTC
timestamp.extractor=Record

rotate.schedule.interval.ms=600000
flush.size=100
s3.part.size=5242880

errors.tolerance=all
errors.deadletterqueue.topic.name=orders-archive-dlq
errors.deadletterqueue.context.headers.enable=true
errors.log.enable=true
errors.log.include.messages=false
```

`rotate.schedule.interval.ms=600000` tương đương 10 phút, nằm dưới RPO 15 phút.

## 7. Security Và IAM

Firehose path:

- Firehose service role chỉ đủ quyền đọc MSK và ghi S3 archive.
- MSK cluster resource policy chỉ cho Firehose service principal các action cần thiết.
- S3 destination dùng archive bucket đã có encryption/versioning/lifecycle.
- Không cấp delete object/version cho normal operator.

Self-managed Kafka Connect path:

- Workload IAM/S3 chỉ nên có `s3:PutObject` vào `orders/*`, multipart upload actions cần thiết, `s3:GetBucketLocation` và `s3:ListBucket` trong prefix `orders/`.
- Không cấp `s3:DeleteObject`, `s3:DeleteObjectVersion`, hoặc quyền thay lifecycle/versioning/encryption bucket.
- Credential Kafka lấy từ External Secrets, không đưa secret thật vào Git.
- Nếu dùng IRSA, service account chỉ có quyền S3 archive cần thiết.

Container security cho self-managed path:

- `runAsNonRoot`.
- `allowPrivilegeEscalation=false`.
- `capabilities.drop=["ALL"]`.
- `seccompProfile=RuntimeDefault`.
- Image tag pinned.
- Requests/limits đầy đủ.

## 8. Triển Khai Theo PR

### PR-A - Design Review

Mục tiêu:

- Thêm docs review plan này.
- Chưa deploy workload/runtime mới.
- Xin review Tech Lead/PM về Firehose-first path và fallback self-managed Kafka Connect.

Output:

- Review decision: Firehose PoC / self-managed Kafka Connect fallback / hold cho AWS Support MSK Connect.

### PR-B1 - Firehose Prerequisite Review

Mục tiêu:

- Xác nhận có được phép bật IAM auth và Multi-VPC private connectivity trên MSK hay không.
- Xác nhận rolling broker update risk.
- Xác nhận cluster policy cho Firehose.
- Chưa tạo Firehose stream nếu prerequisite chưa được duyệt.

### PR-B2 - Firehose Delivery Stream

Mục tiêu:

- Tạo Firehose delivery stream đọc MSK topic `orders` và ghi S3 archive.
- Cấu hình IAM/SG/resource policy least-privilege.
- Cấu hình buffering/data freshness <= 15 phút.
- Monitor Firehose delivery errors và S3 object.

### PR-C - Self-Managed Kafka Connect Fallback Nếu Firehose Không Khả Thi

Mục tiêu:

- Build image Kafka Connect có Confluent S3 Sink plugin pin version.
- Thêm Kubernetes manifests/Helm values, có gate `enabled=false` nếu cần.
- Thêm IAM/IRSA policy least-privilege.
- Thêm ConfigMap/Secret reference, không chứa secret thật.
- Enable worker có kiểm soát sau khi review.

### PR-D - Evidence

Mục tiêu:

- Ghi evidence stream/connector running.
- Ghi S3 object path thật.
- Ghi latency <= 15 phút.
- Ghi log/metric không có delivery error nghiêm trọng.
- Chuẩn bị input cho subtask 4 parse/compare marker.

## 9. Verification

Firehose prerequisite:

```powershell
aws kafka describe-cluster-v2 `
  --region us-east-1 `
  --profile tf4 `
  --cluster-arn <MSK_CLUSTER_ARN> `
  --query 'ClusterInfo.{State:State,ClientAuthentication:Provisioned.ClientAuthentication,ConnectivityInfo:Provisioned.ConnectivityInfo}' `
  --output json
```

Firehose stream:

```powershell
aws firehose describe-delivery-stream `
  --region us-east-1 `
  --profile tf4 `
  --delivery-stream-name <DELIVERY_STREAM_NAME> `
  --query 'DeliveryStreamDescription.{Status:DeliveryStreamStatus,Source:Source,Destination:Destinations[0].S3DestinationDescription}' `
  --output json
```

S3 object:

```powershell
aws s3 ls s3://tf4-msk-orders-archive-511825856493-us-east-1/orders/ `
  --recursive `
  --summarize `
  --region us-east-1 `
  --profile tf4
```

Self-managed Kafka Connect pod, nếu dùng fallback:

```powershell
kubectl -n techx-tf4 get deploy,pod | Select-String "kafka-connect|orders-s3"
kubectl -n techx-tf4 logs deploy/<connect-deployment> --since=10m --tail=200
```

SLO:

- Checkout success không tụt dưới SLO đã duyệt.
- Storefront p95 không tăng bất thường.
- MSK broker metrics không có CPU/network/disk spike bất thường.
- Firehose/Kafka Connect archive latency <= 15 phút.

## 10. Rollback

Firehose rollback:

- Revert PR tạo Firehose delivery stream.
- Terraform destroy Firehose stream/resource policy nếu cần.
- Không xoá S3 archive object đã ghi.
- Không đổi app config.

Self-managed Kafka Connect rollback:

- Scale worker về `0`.
- Revert PR enable worker.
- Không xoá S3 archive object.
- Giữ log/config để điều tra.

Không rollback bằng cách:

- Xoá bucket archive.
- Xoá object đã ghi.
- Xoá MSK topic app đang dùng.

## 11. Acceptance Mapping

Acceptance của subtask 3:

- Connector/stream RUNNING: Firehose delivery stream `ACTIVE` hoặc self-managed Kafka Connect connector `RUNNING`.
- Orders xuất hiện trong S3: object có dưới `orders/`.
- Độ trễ archive <= 15 phút: đo bằng marker timestamp và S3 object LastModified/data freshness.
- Payload giữ order ID/timestamp/dữ liệu replay: validate ở subtask 4 bằng parser độc lập.
- Restart/temporary failure không mất dữ liệu vượt RPO: verify delivery resume và không thiếu marker ngoài cửa sổ 15 phút.

## 12. Open Questions Cho Review

- Có được phép bật IAM auth và Multi-VPC private connectivity cho MSK để dùng Firehose không?
- Rolling broker update khi update MSK connectivity có được chấp nhận trong thời điểm này không?
- Nếu Firehose được chọn, partition/path format nào sẽ được dùng để replay tốt nhất?
- Nếu Firehose bị block, có chấp nhận tạo pod self-managed Kafka Connect trong EKS không?
- Namespace/self-managed workload sẽ nằm ở `techx-tf4` hay namespace platform riêng?
- Dùng IRSA riêng hay node role hiện tại đã đủ và được duyệt?
- Có cần tạo internal topics và DLQ topic bằng Terraform/script trước khi bật self-managed worker không?

## 13. References

- AWS Firehose MSK source documentation: https://docs.aws.amazon.com/firehose/latest/dev/writing-with-msk.html
- AWS Firehose access control for private MSK: https://docs.aws.amazon.com/firehose/latest/dev/controlling-access.html
- AWS MSK Multi-VPC private connectivity: https://docs.aws.amazon.com/msk/latest/developerguide/aws-access-mult-vpc.html
- AWS Firehose pricing: https://aws.amazon.com/firehose/pricing/
- AWS MSK pricing: https://aws.amazon.com/msk/pricing/
